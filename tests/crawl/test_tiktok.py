import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from corpus.crawl import browser, files, tiktok

FIX = Path(__file__).parents[1] / "fixtures" / "tiktok"


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
    assert (v / "video.mp4").exists() and (v / "info.json").exists() and (v / "comments.json").exists()
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
            if payload is not None:  # None = the API has not answered yet
                await self.handler(_Resp(payload))

    goto = click = scroll_into_view_if_needed = wheel = _next

    async def wait_for_timeout(self, ms):
        pass

    def locator(self, sel):
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
