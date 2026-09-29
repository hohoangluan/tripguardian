import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from corpus.crawl import browser, files, tiktok

FIX = Path(__file__).parents[1] / "fixtures" / "tiktok"


@pytest.fixture(autouse=True)
def fast_rounds(monkeypatch):
    monkeypatch.setattr(tiktok, "ROUND_S", 0.01)
    monkeypatch.setattr(tiktok, "SETTLE_S", 0.2)


def test_parse_search_fixture():
    items = tiktok.parse_search(json.loads((FIX / "search.json").read_text(encoding="utf-8")))
    assert items
    it = items[0]
    assert it["video_id"].isdigit() and it["url"].endswith("/video/" + it["video_id"])
    assert it["author_id"] and it["created_at"] and "raw" in it


def test_parse_search_keeps_photo_post_without_play_url():
    payload = {"item_list": [{"id": "1", "desc": "ảnh", "createTime": 1, "author": {"uniqueId": "a"},
                              "imagePost": {}, "video": {}}]}
    assert tiktok.parse_search(payload)[0]["play_url"] is None


def test_parse_comments_fixture_hides_authors():
    raw = json.loads((FIX / "comments.json").read_text(encoding="utf-8"))
    comments, _ = tiktok.parse_comments(raw)
    assert comments and all(len(c["author_hash"]) == 16 for c in comments)
    assert raw["comments"][0]["user"]["uid"] not in json.dumps(comments)


def _item(i, play=True):
    return {"video_id": str(i), "url": f"https://www.tiktok.com/@a/video/{i}", "author_id": "a", "desc": "d",
            "created_at": 1, "hashtags": [], "play_url": "http://v" if play else None, "raw": {"id": str(i)}}


@pytest.fixture
def fake_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(tiktok, "load_config", lambda city: ("Đà Lạt", {"tiktok": {
        "max_videos_per_query": 5, "max_comments_per_video": 3, "queries": {"general": ["{city} có gì chơi"]}}}))
    monkeypatch.setattr(tiktok, "pause", lambda *a: asyncio.sleep(0))
    calls = {"download": 0, "logged_in": True, "items": [_item(1), _item(2, play=False)], "fail_comments": False}

    async def ensure_login(ctx):
        if not calls["logged_in"]:
            raise browser.LoginRequired("tiktok")

    async def search(ctx, query, limit):
        return calls["items"]

    async def comments(ctx, url, limit):
        if calls["fail_comments"]:
            raise RuntimeError("comment api down")
        return [{"comment_id": "c1"}]

    async def download(ctx, url, path):
        calls["download"] += 1
        files.write_bytes(path, b"mp4")

    for name, fn in (("ensure_login", ensure_login), ("search", search), ("comments", comments),
                     ("download_video", download)):
        monkeypatch.setattr(tiktok, name, fn)

    @asynccontextmanager
    async def profile(source, headed=False):
        yield object()

    return tmp_path / "tiktok", calls, profile


def test_run_writes_files_and_skips_done_videos(fake_env):
    root, calls, profile = fake_env
    asyncio.run(tiktok.run("dalat", profile=profile))
    asyncio.run(tiktok.run("dalat", profile=profile))
    v = root / "videos" / "1"
    assert (v / "video.mp4").exists() and (v / "info.json").exists()
    doc = json.loads((v / "video.json").read_text(encoding="utf-8"))
    assert doc["video_path"] == "tiktok/videos/1/video.mp4" and doc["video_url"].endswith("/video/1")
    assert [c["comment_id"] for c in doc["comments"]] == ["c1"]
    assert calls["download"] == 1  # second run skipped the finished video
    lines = (root / "search" / "dalat" / "da-lat-co-gi-choi.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and "play_url" not in lines[0] and "raw" not in lines[0]


def test_photo_post_is_logged_not_done(fake_env):
    root, calls, profile = fake_env
    asyncio.run(tiktok.run("dalat", profile=profile))
    assert not (root / "videos" / "2" / "video.mp4").exists()
    assert '"id": "2"' in (root / "errors.jsonl").read_text(encoding="utf-8")


def test_failed_video_is_retried_next_run(fake_env):
    root, calls, profile = fake_env
    calls["fail_comments"] = True
    asyncio.run(tiktok.run("dalat", profile=profile))
    assert not (root / "videos" / "1" / "video.mp4").exists()
    calls["fail_comments"] = False
    asyncio.run(tiktok.run("dalat", profile=profile))
    assert (root / "videos" / "1" / "video.mp4").exists()


def test_missing_comments_are_retried(fake_env, monkeypatch):
    # A blocked comment panel yields no comments; the video must not be marked done.
    root, calls, profile = fake_env
    calls["items"] = [{**_item(1), "raw": {"id": "1", "stats": {"commentCount": 5}}}]

    async def no_comments(ctx, url, limit):
        return []

    monkeypatch.setattr(tiktok, "comments", no_comments)
    asyncio.run(tiktok.run("dalat", profile=profile))
    assert not (root / "videos" / "1" / "video.mp4").exists()
    assert "no comments" in (root / "errors.jsonl").read_text(encoding="utf-8")


def test_not_logged_in_stops_before_writing(fake_env):
    root, calls, profile = fake_env
    calls["logged_in"] = False
    with pytest.raises(browser.LoginRequired):
        asyncio.run(tiktok.run("dalat", profile=profile))
    assert not (root / "search").exists()


def test_pause_comes_from_config(fake_env, monkeypatch):
    root, calls, profile = fake_env
    seen = []

    async def rec(*a):
        seen.append(a)

    monkeypatch.setattr(tiktok, "pause", rec)
    monkeypatch.setattr(tiktok, "load_config", lambda city: ("Đà Lạt", {"tiktok": {
        "max_videos_per_query": 5, "max_comments_per_video": 3, "pause_s": [0.1, 0.2],
        "queries": {"general": ["{city} có gì chơi"]}}}))
    asyncio.run(tiktok.run("dalat", profile=profile))
    assert seen and all(a == (0.1, 0.2) for a in seen)


class _Resp:
    def __init__(self, payload):
        # payload alone = a top-level comment page; (url, payload) for other APIs
        url, self.payload = payload if isinstance(payload, tuple) else ("https://www.tiktok.com/api/comment/list/?c=1", payload)
        self.url = url

    async def json(self):
        return self.payload


class _Page:
    """Serves one comment page per scroll until the pages run out."""

    def __init__(self, pages):
        self.pages, self.handler = list(pages), None
        self.mouse = self
        self.first = self.last = self

    def on(self, event, fn):
        self.handler = fn

    async def _next(self, *a, **k):
        if self.pages:
            payload = self.pages.pop(0)
            if isinstance(payload, tuple) and payload[0] == "late":  # still in flight: lands a moment later
                late = payload[1]
                asyncio.get_running_loop().call_later(0.05, lambda: asyncio.ensure_future(self.handler(_Resp(late))))
            elif payload is not None:  # None = the API has not answered yet
                await self.handler(_Resp(payload))

    async def route(self, pattern, handler):
        pass

    async def wait_for(self, **kw):
        pass

    goto = click = scroll_into_view_if_needed = wheel = _next

    async def wait_for_timeout(self, ms):
        pass

    def locator(self, sel):
        return self

    def filter(self, **kw):
        return self

    async def count(self):
        return 1

    async def close(self):
        pass


def test_comments_without_limit_reads_every_page(monkeypatch):
    async def no_captcha(page, source):
        return None

    monkeypatch.setattr(tiktok, "wait_for_person", no_captcha)
    monkeypatch.setattr(tiktok, "_expand", lambda page, sel: asyncio.sleep(0, 0))
    pages = [{"comments": [{"cid": f"{p}-{i}"} for i in range(20)], "has_more": p < 9} for p in range(10)]
    page = _Page(pages)

    class Ctx:
        async def new_page(self):
            return page

    got = asyncio.run(tiktok.comments(Ctx(), "https://www.tiktok.com/@a/video/1", None))
    assert len(got) == 200 and len({c["comment_id"] for c in got}) == 200


def test_comments_drop_repeated_pages(monkeypatch):
    async def no_captcha(page, source):
        return None

    monkeypatch.setattr(tiktok, "wait_for_person", no_captcha)
    monkeypatch.setattr(tiktok, "_expand", lambda page, sel: asyncio.sleep(0, 0))
    page1 = {"comments": [{"cid": f"a{i}"} for i in range(20)], "has_more": True}
    page2 = {"comments": [{"cid": f"b{i}"} for i in range(20)], "has_more": False}
    page = _Page([page1, page1, page2])  # TikTok re-sends a page it already served

    class Ctx:
        async def new_page(self):
            return page

    got = asyncio.run(tiktok.comments(Ctx(), "https://www.tiktok.com/@a/video/1", None))
    assert [c["comment_id"] for c in got] == [f"a{i}" for i in range(20)] + [f"b{i}" for i in range(20)]


def test_parse_replies_fixture_links_parent():
    top, _ = tiktok.parse_comments(json.loads((FIX / "comments.json").read_text(encoding="utf-8")))
    replies, more = tiktok.parse_comments(json.loads((FIX / "replies.json").read_text(encoding="utf-8")))
    assert all(c["parent_id"] is None for c in top)
    assert replies and all(r["parent_id"] and r["parent_id"] != "0" for r in replies)


def test_comments_include_replies(monkeypatch):
    async def no_captcha(page, source):
        return None

    async def no_buttons(page, selector):
        return 0

    monkeypatch.setattr(tiktok, "wait_for_person", no_captcha)
    monkeypatch.setattr(tiktok, "_expand", no_buttons)
    reply_url = "https://www.tiktok.com/api/comment/list/reply/?comment_id=a0"
    pages = [
        {"comments": [{"cid": "a0", "reply_id": "0"}], "has_more": True},
        (reply_url, {"comments": [{"cid": "r1", "reply_id": "a0"}], "has_more": False}),  # must not end the list
        {"comments": [{"cid": "a1", "reply_id": "0"}], "has_more": False},
    ]
    page = _Page(pages)

    class Ctx:
        async def new_page(self):
            return page

    got = asyncio.run(tiktok.comments(Ctx(), "https://www.tiktok.com/@a/video/1", None))
    assert [(c["comment_id"], c["parent_id"]) for c in got] == [("a0", None), ("r1", "a0"), ("a1", None)]


def test_slow_first_response_is_awaited(monkeypatch):
    monkeypatch.setattr(tiktok, "wait_for_person", lambda page, source: asyncio.sleep(0))
    monkeypatch.setattr(tiktok, "_expand", lambda page, sel: asyncio.sleep(0, 0))
    page = _Page([None] * 6 + [{"comments": [{"cid": "a0"}], "has_more": False}])

    class Ctx:
        async def new_page(self):
            return page

    got = asyncio.run(tiktok.comments(Ctx(), "https://www.tiktok.com/@a/video/1", None))
    assert [c["comment_id"] for c in got] == ["a0"]


def _cfg(**extra):
    return lambda city: ("Đà Lạt", {"tiktok": {"max_videos_per_query": 10, "max_comments_per_video": 3,
                                               "queries": {"general": ["{city} có gì chơi"]}, **extra}})


def test_videos_run_in_parallel_tabs(fake_env, monkeypatch):
    root, calls, profile = fake_env
    calls["items"] = [_item(i) for i in range(1, 8)]
    active, peak = [0], [0]

    async def slow_comments(ctx, url, limit):
        active[0] += 1
        peak[0] = max(peak[0], active[0])
        await asyncio.sleep(0.05)
        active[0] -= 1
        return [{"comment_id": "c"}]

    monkeypatch.setattr(tiktok, "comments", slow_comments)
    monkeypatch.setattr(tiktok, "load_config", _cfg(tabs=3, tabs_start=3))
    asyncio.run(tiktok.run("dalat", profile=profile))
    assert peak[0] == 3 and len(list((root / "videos").glob("*/video.mp4"))) == 7


def test_login_required_in_a_tab_stops_the_run(fake_env, monkeypatch):
    root, calls, profile = fake_env
    calls["items"] = [_item(i) for i in range(1, 5)]

    async def blocked(ctx, url, limit):
        raise browser.LoginRequired("tiktok")

    monkeypatch.setattr(tiktok, "comments", blocked)
    monkeypatch.setattr(tiktok, "load_config", _cfg(tabs=2))
    with pytest.raises(browser.LoginRequired):
        asyncio.run(tiktok.run("dalat", profile=profile))


def test_blocked_video_is_retried_after_cooldown(fake_env, monkeypatch):
    root, calls, profile = fake_env
    calls["items"] = [_item(1)]
    tries = [0]

    async def flaky(ctx, url, limit):
        tries[0] += 1
        if tries[0] == 1:
            raise RuntimeError("Page.goto: net::ERR_HTTP_RESPONSE_CODE_FAILURE at https://www.tiktok.com/@a/video/1")
        return [{"comment_id": "c"}]

    monkeypatch.setattr(tiktok, "comments", flaky)
    monkeypatch.setattr(tiktok, "load_config", _cfg(tabs=4, cooldown_s=0))
    asyncio.run(tiktok.run("dalat", profile=profile))
    assert tries[0] == 2 and (root / "videos" / "1" / "video.mp4").exists()
    assert json.loads((root / "throttle.json").read_text(encoding="utf-8"))["limit"] >= 1


def test_late_replies_are_awaited_before_closing(monkeypatch):
    monkeypatch.setattr(tiktok, "wait_for_person", lambda page, source: asyncio.sleep(0))
    monkeypatch.setattr(tiktok, "_expand", lambda page, sel: asyncio.sleep(0, 0))
    reply_url = "https://www.tiktok.com/api/comment/list/reply/?comment_id=a0"
    page = _Page([{"comments": [{"cid": "a0", "reply_id": "0"}], "has_more": False},
                  ("late", (reply_url, {"comments": [{"cid": "r1", "reply_id": "a0"}], "has_more": False}))])

    class Ctx:
        async def new_page(self):
            return page

    got = asyncio.run(tiktok.comments(Ctx(), "https://www.tiktok.com/@a/video/1", None))
    assert [c["comment_id"] for c in got] == ["a0", "r1"]


def test_tab_is_free_while_the_video_downloads(fake_env, monkeypatch):
    # One tab: the second video's comments must start while the first video is still downloading.
    root, calls, profile = fake_env
    calls["items"] = [_item(1), _item(2)]
    second_started = asyncio.Event()

    async def comments(ctx, url, limit):
        if url.endswith("/2"):
            second_started.set()
        return [{"comment_id": "c"}]

    async def download(ctx, url, path):
        if path.parent.name == "1":
            await asyncio.wait_for(second_started.wait(), 2)
        files.write_bytes(path, b"mp4")

    monkeypatch.setattr(tiktok, "comments", comments)
    monkeypatch.setattr(tiktok, "download_video", download)
    monkeypatch.setattr(tiktok, "load_config", _cfg(tabs=1, tabs_start=1))
    asyncio.run(tiktok.run("dalat", profile=profile))
    assert (root / "videos" / "1" / "video.mp4").exists() and (root / "videos" / "2" / "video.mp4").exists()


def test_blocked_search_is_retried_then_skipped(fake_env, monkeypatch):
    root, calls, profile = fake_env
    tries = []

    async def search(ctx, query, limit):
        tries.append(query)
        if "gia đình" in query:
            raise RuntimeError("Page.goto: net::ERR_HTTP_RESPONSE_CODE_FAILURE")  # stays blocked
        if len([q for q in tries if q == query]) == 1:
            raise RuntimeError("Page.goto: net::ERR_HTTP_RESPONSE_CODE_FAILURE")  # blocked once
        return [_item(1)]

    monkeypatch.setattr(tiktok, "search", search)
    monkeypatch.setattr(tiktok, "load_config", _cfg(tabs=2, cooldown_s=0, queries={"general": ["{city} có gì chơi", "{city} đi cùng gia đình"]}))
    asyncio.run(tiktok.run("dalat", profile=profile))
    assert (root / "videos" / "1" / "video.mp4").exists()
    assert tries.count("Đà Lạt đi cùng gia đình") == 3
    assert '"stage": "search"' in (root / "errors.jsonl").read_text(encoding="utf-8")


def test_video_shared_by_two_queries_is_fetched_once(fake_env, monkeypatch):
    root, calls, profile = fake_env
    calls["items"] = [_item(1)]
    monkeypatch.setattr(tiktok, "load_config", _cfg(tabs=2, queries={"general": ["{city} có gì chơi", "review {city}"]}))
    asyncio.run(tiktok.run("dalat", profile=profile))
    assert calls["download"] == 1


def test_unfinished_videos_get_a_second_pass(fake_env, monkeypatch):
    root, calls, profile = fake_env
    calls["items"] = [_item(1)]
    tries = [0]

    async def flaky(ctx, url, limit):
        tries[0] += 1
        if tries[0] == 1:
            raise RuntimeError("layout hiccup")  # not a block: logged, then retried in the second pass
        return [{"comment_id": "c"}]

    monkeypatch.setattr(tiktok, "comments", flaky)
    asyncio.run(tiktok.run("dalat", profile=profile))
    assert tries[0] == 2 and (root / "videos" / "1" / "video.mp4").exists()


def test_video_doc_nests_replies_under_their_comment():
    it = {**_item(7), "desc": "Săn mây", "hashtags": ["dalat"],
          "raw": {"id": "7", "stats": {"commentCount": 4, "playCount": 10}}}
    rows = [
        {"comment_id": "a", "author_hash": "h1", "text": "đẹp", "created_at": 1, "likes": 2, "reply_count": 1, "parent_id": None},
        {"comment_id": "r", "author_hash": "h2", "text": "ở đâu", "created_at": 2, "likes": 0, "reply_count": 0, "parent_id": "a"},
        {"comment_id": "b", "author_hash": "h3", "text": "ok", "created_at": 3, "likes": 0, "reply_count": 0, "parent_id": None},
        {"comment_id": "x", "author_hash": "h4", "text": "lạc", "created_at": 4, "likes": 0, "reply_count": 0, "parent_id": "gone"},
    ]
    doc = tiktok.video_doc(it, rows, "tiktok/videos/7/video.mp4")
    assert doc["caption"] == "Săn mây" and doc["hashtags"] == ["dalat"] and doc["stats"]["commentCount"] == 4
    assert doc["video_path"] == "tiktok/videos/7/video.mp4" and doc["fetched_at"]
    assert [c["comment_id"] for c in doc["comments"]] == ["a", "b", "x"]  # a reply whose parent is missing stays visible
    assert [r["text"] for r in doc["comments"][0]["replies"]] == ["ở đâu"]
    assert doc["comments"][2]["reply_to"] == "gone"
    assert "parent_id" not in json.dumps(doc) and "raw" not in doc
