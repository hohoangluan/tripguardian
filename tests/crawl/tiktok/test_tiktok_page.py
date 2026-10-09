import asyncio

import pytest

from tiktok_helpers import FakeCtx, FakePage

from corpus.crawl.tiktok import crawl

URL = "https://www.tiktok.com/@a/video/1"
REPLY = "https://www.tiktok.com/api/comment/list/reply/?comment_id=a0"


def _comments(pages, item=None):
    item, rows, complete = asyncio.run(crawl.comments(FakeCtx(FakePage(pages, item)), URL, None))
    assert complete  # every list here ends with has_more=0
    return item, rows


def test_without_limit_reads_every_page_and_returns_page_item(no_person):
    pages = [{"comments": [{"cid": f"{p}-{i}"} for i in range(20)], "has_more": p < 9} for p in range(10)]
    item, got = _comments(pages, {"id": "1"})
    assert item == {"id": "1"} and len(got) == 200 and len({c["comment_id"] for c in got}) == 200


class _LatePage(FakePage):
    """The rehydration script is not in the DOM yet at domcontentloaded; it appears a few polls later."""

    def __init__(self, pages, item, empty_polls):
        super().__init__(pages, item)
        self.empty_polls = empty_polls

    async def evaluate(self, js):
        if self.empty_polls:
            self.empty_polls -= 1
            return None
        return self.item


def test_waits_for_page_item_that_renders_late(no_person):
    pages = [{"comments": [{"cid": "a"}], "has_more": False}]
    item, got, _ = asyncio.run(crawl.comments(FakeCtx(_LatePage(pages, {"id": "1"}, 3)), URL, None))
    assert item == {"id": "1"} and [c["comment_id"] for c in got] == ["a"]


class _ReloadingPage(FakePage):
    """TikTok reloads the video page right after it opens; evaluating mid-reload raises."""

    def __init__(self, pages, item):
        super().__init__(pages, item)
        self.reloads = 2

    async def evaluate(self, js):
        if self.reloads:
            self.reloads -= 1
            raise RuntimeError("Page.evaluate: Execution context was destroyed, most likely because of a navigation")
        return self.item


def test_page_item_read_after_self_reload(no_person):
    pages = [{"comments": [{"cid": "a"}], "has_more": False}]
    item, got, _ = asyncio.run(crawl.comments(FakeCtx(_ReloadingPage(pages, {"id": "1"})), URL, None))
    assert item == {"id": "1"} and [c["comment_id"] for c in got] == ["a"]


def test_page_item_missing_for_good_gives_none(no_person):
    item, _, _ = asyncio.run(crawl.comments(FakeCtx(_LatePage([], {"id": "1"}, 10**6)), URL, None))
    assert item is None


def test_repeated_pages_are_dropped(no_person):
    page1 = {"comments": [{"cid": f"a{i}"} for i in range(20)], "has_more": True}
    page2 = {"comments": [{"cid": f"b{i}"} for i in range(20)], "has_more": False}
    _, got = _comments([page1, page1, page2])  # TikTok re-sends a page it already served
    assert [c["comment_id"] for c in got] == [f"a{i}" for i in range(20)] + [f"b{i}" for i in range(20)]


def test_replies_are_collected_without_ending_the_list(no_person):
    _, got = _comments([
        {"comments": [{"cid": "a0", "reply_id": "0"}], "has_more": True},
        (REPLY, {"comments": [{"cid": "r1", "reply_id": "a0"}], "has_more": False}),  # must not end the list
        {"comments": [{"cid": "a1", "reply_id": "0"}], "has_more": False},
    ])
    assert [(c["comment_id"], c["parent_id"]) for c in got] == [("a0", None), ("r1", "a0"), ("a1", None)]


def test_slow_first_response_is_awaited(no_person):
    _, got = _comments([None] * 6 + [{"comments": [{"cid": "a0"}], "has_more": False}])
    assert [c["comment_id"] for c in got] == ["a0"]


def test_late_replies_are_awaited_before_closing(no_person):
    _, got = _comments([{"comments": [{"cid": "a0", "reply_id": "0"}], "has_more": False},
                        ("late", (REPLY, {"comments": [{"cid": "r1", "reply_id": "a0"}], "has_more": False}))])
    assert [c["comment_id"] for c in got] == ["a0", "r1"]


REPLY_B = "https://www.tiktok.com/api/comment/list/reply/?comment_id=b0"


def test_waits_until_every_reply_list_has_ended(no_person):
    # The top-level list ends first; the page is only left once each comment's reply list says has_more=0.
    item, got, complete = asyncio.run(crawl.comments(FakeCtx(FakePage([
        {"comments": [{"cid": "a0", "reply_id": "0", "reply_comment_total": 2},
                      {"cid": "b0", "reply_id": "0", "reply_comment_total": 1}], "has_more": False},
        None, None,  # replies not opened yet
        (REPLY, {"comments": [{"cid": "r1", "reply_id": "a0"}], "has_more": True}),
        None,
        (REPLY, {"comments": [{"cid": "r2", "reply_id": "a0"}], "has_more": False}),
        (REPLY_B, {"comments": [], "has_more": False}),  # hidden reply: TikTok serves none, but the list ended
    ], {"id": "1"})), URL, None))
    assert complete and [c["comment_id"] for c in got] == ["a0", "b0", "r1", "r2"]


def test_unfinished_reply_list_is_reported_incomplete(no_person):
    _, got, complete = asyncio.run(crawl.comments(FakeCtx(FakePage([
        {"comments": [{"cid": "a0", "reply_id": "0", "reply_comment_total": 3}], "has_more": False},
        (REPLY, {"comments": [{"cid": "r1", "reply_id": "a0"}], "has_more": True}),  # never continued
    ], {"id": "1"})), URL, None))
    assert not complete and [c["comment_id"] for c in got] == ["a0", "r1"]


def test_empty_body_means_blocked_at_once(no_person):
    with pytest.raises(RuntimeError, match="empty body"):
        asyncio.run(crawl.comments(FakeCtx(FakePage([""], {"id": "1"})), URL, None))


def test_person_solved_reports_a_captcha_that_was_cleared(monkeypatch):
    from corpus.crawl.tiktok import page as tt_page
    waited = []

    async def captcha(p):
        return True

    async def wait(p, source):
        waited.append(source)

    monkeypatch.setattr(tt_page, "is_captcha", captcha)
    monkeypatch.setattr(tt_page, "wait_for_person", wait)
    assert asyncio.run(tt_page._person_solved(object())) and waited == ["tiktok"]

    async def none(p):
        return False

    monkeypatch.setattr(tt_page, "is_captcha", none)
    monkeypatch.setattr(tt_page, "CAPTCHA_APPEAR_S", 0.5)
    assert not asyncio.run(tt_page._person_solved(object())) and waited == ["tiktok"]
