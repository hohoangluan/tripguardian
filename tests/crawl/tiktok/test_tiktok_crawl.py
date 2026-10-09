import asyncio
import json

import pytest
from tiktok_helpers import fake_profile, fixture_json

from corpus.crawl.common import browser, files
from corpus.crawl.tiktok import crawl


def test_parse_comments_fixture_hides_authors():
    raw = fixture_json("comments.json")
    comments, _ = crawl.parse_comments(raw)
    assert comments and all(len(c["author_hash"]) == 16 for c in comments)
    assert raw["comments"][0]["user"]["uid"] not in json.dumps(comments)


def test_parse_replies_fixture_links_parent():
    top, _ = crawl.parse_comments(fixture_json("comments.json"))
    replies, _ = crawl.parse_comments(fixture_json("replies.json"))
    assert all(c["parent_id"] is None for c in top)
    assert replies and all(r["parent_id"] and r["parent_id"] != "0" for r in replies)


def _row(i, photo=False):
    return {"video_id": str(i), "url": f"https://www.tiktok.com/@a/video/{i}", "author_id": "a", "desc": "d",
            "created_at": 1, "hashtags": ["dalat"], "photo": photo, "queries": ["q"]}


def _page_item(i, comments=1):
    return {"id": str(i), "desc": "Săn mây", "createTime": 2, "stats": {"commentCount": comments, "playCount": 10},
            "video": {"playAddr": f"http://v/{i}"}}


def test_video_doc_nests_replies_under_their_comment():
    rows = [
        {"comment_id": "a", "author_hash": "h1", "text": "đẹp", "created_at": 1, "likes": 2, "reply_count": 1, "parent_id": None},
        {"comment_id": "r", "author_hash": "h2", "text": "ở đâu", "created_at": 2, "likes": 0, "reply_count": 0, "parent_id": "a"},
        {"comment_id": "b", "author_hash": "h3", "text": "ok", "created_at": 3, "likes": 0, "reply_count": 0, "parent_id": None},
        {"comment_id": "x", "author_hash": "h4", "text": "lạc", "created_at": 4, "likes": 0, "reply_count": 0, "parent_id": "gone"},
    ]
    doc = crawl.video_doc(_row(7), _page_item(7, 4), rows, "tiktok/videos/7/video.mp4")
    assert doc["caption"] == "Săn mây" and doc["hashtags"] == ["dalat"] and doc["stats"]["commentCount"] == 4
    assert doc["created_at"] == 2 and doc["queries"] == ["q"]  # fresh from the video page, plus the list's queries
    assert doc["video_path"] == "tiktok/videos/7/video.mp4" and doc["fetched_at"]
    assert [c["comment_id"] for c in doc["comments"]] == ["a", "b", "x"]  # a reply whose parent is missing stays visible
    assert [r["text"] for r in doc["comments"][0]["replies"]] == ["ở đâu"]
    assert doc["comments"][2]["reply_to"] == "gone"
    assert "parent_id" not in json.dumps(doc)


@pytest.fixture
def env(data, monkeypatch):
    cfg = {"max_comments_per_video": 3, "cooldown_s": 0, "pause_s": [0.1, 0.2], "tabs": 1, "tabs_start": 1}
    monkeypatch.setattr(crawl, "load_config", lambda city: ("Đà Lạt", {"tiktok": cfg}))
    calls = {"logged_in": True, "download": [], "pauses": [], "opened": [],
             "comments": lambda url: (_page_item(url.rsplit("/", 1)[1]), [{"comment_id": "c1"}])}

    async def ensure_login(ctx):
        if not calls["logged_in"]:
            raise browser.LoginRequired("tiktok")

    async def comments(ctx, url, limit):
        calls["opened"].append(url)
        r = calls["comments"](url)
        return r if len(r) == 3 else (*r, True)  # (item, rows[, complete])

    async def open_item(ctx, url):
        calls["opened"].append(url)
        return _page_item(url.rsplit("/", 1)[1])

    async def download(ctx, url, path):
        calls["download"].append(url)
        files.write_bytes(path, b"mp4")

    async def rec(*a):
        calls["pauses"].append(a)

    for name, fn in (("ensure_login", ensure_login), ("comments", comments), ("open_item", open_item),
                     ("download_video", download), ("pause", rec)):
        monkeypatch.setattr(crawl, name, fn)
    calls["kept"] = None  # None = every listed video kept by the filter
    monkeypatch.setattr(crawl, "kept_ids", lambda city: calls["kept"] if calls["kept"] is not None
                        else {str(i) for i in range(100)})

    def write_list(rows):
        (data / "list").mkdir(parents=True, exist_ok=True)
        (data / "list" / "dalat.json").write_text(json.dumps({"items": rows}), encoding="utf-8")

    write_list([_row(1), _row(2, photo=True)])
    return data, calls, cfg, write_list


def test_crawl_writes_files_from_list_and_skips_done(env):
    data, calls, _, _ = env
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    v = data / "videos" / "1"
    assert (v / "video.mp4").exists() and json.loads((v / "info.json").read_text(encoding="utf-8"))["id"] == "1"
    doc = json.loads((v / "video.json").read_text(encoding="utf-8"))
    assert doc["video_path"] == "tiktok/videos/1/video.mp4" and [c["comment_id"] for c in doc["comments"]] == ["c1"]
    assert calls["download"] == ["http://v/1"]  # fresh play address from the page; second run skipped the video
    assert calls["opened"] == ["https://www.tiktok.com/@a/video/1"]  # photo post never opened
    assert calls["pauses"] == [(0.1, 0.2)]


def test_failed_video_is_logged_and_retried_next_run(env):
    data, calls, _, _ = env
    ok = calls["comments"]
    calls["comments"] = lambda url: (_ for _ in ()).throw(RuntimeError("comment api down"))
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    assert not (data / "videos" / "1" / "video.mp4").exists()
    assert "comment api down" in (data / "errors.jsonl").read_text(encoding="utf-8")
    calls["comments"] = ok
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    assert (data / "videos" / "1" / "video.mp4").exists()


def test_missing_comments_are_not_done(env):
    # A blocked comment panel yields no comments; the video must not be marked done.
    data, calls, _, _ = env
    calls["comments"] = lambda url: (_page_item(1, comments=5), [])
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    assert not (data / "videos" / "1" / "video.mp4").exists()
    assert "no comments" in (data / "errors.jsonl").read_text(encoding="utf-8")


def test_photo_found_on_page_is_logged_not_done(env):
    data, calls, _, _ = env
    calls["comments"] = lambda url: ({**_page_item(1), "video": {}}, [{"comment_id": "c1"}])
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    assert not (data / "videos" / "1" / "video.mp4").exists()
    assert "photo post" in (data / "errors.jsonl").read_text(encoding="utf-8")


def test_videos_run_in_parallel_tabs(env, monkeypatch):
    data, calls, cfg, write_list = env
    cfg.update(tabs=3, tabs_start=3)
    write_list([_row(i) for i in range(1, 8)])
    active, peak = [0], [0]

    async def slow(ctx, url, limit):
        active[0] += 1
        peak[0] = max(peak[0], active[0])
        await asyncio.sleep(0.05)
        active[0] -= 1
        return _page_item(url.rsplit("/", 1)[1]), [{"comment_id": "c"}], True

    monkeypatch.setattr(crawl, "comments", slow)
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    assert peak[0] == 3 and len(list((data / "videos").glob("*/video.mp4"))) == 7


def test_blocked_video_is_retried_after_cooldown(env):
    data, calls, cfg, _ = env
    cfg.update(tabs=4)
    tries = [0]

    def flaky(url):
        tries[0] += 1
        if tries[0] == 1:
            raise RuntimeError("Page.goto: net::ERR_HTTP_RESPONSE_CODE_FAILURE at https://www.tiktok.com/@a/video/1")
        return _page_item(1), [{"comment_id": "c"}]

    calls["comments"] = flaky
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    assert tries[0] == 2 and (data / "videos" / "1" / "video.mp4").exists()
    assert json.loads((data / "throttle.json").read_text(encoding="utf-8"))["limit"] >= 1


def test_blocked_comment_api_cools_down_and_retries(env):
    # A throttled session gets empty comment API bodies: the panel shows no comments although the video has some.
    data, calls, _, _ = env
    tries = [0]

    def blocked_once(url):
        tries[0] += 1
        return _page_item(1, comments=5), ([] if tries[0] == 1 else [{"comment_id": "c"}])

    calls["comments"] = blocked_once
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    assert tries[0] == 2 and (data / "videos" / "1" / "video.mp4").exists()


def test_incomplete_comments_are_retried_then_saved_flagged(env):
    data, calls, _, _ = env
    tries = [0]

    def unfinished(url):
        tries[0] += 1
        return _page_item(1), [{"comment_id": "c"}], False

    calls["comments"] = unfinished
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    doc = json.loads((data / "videos" / "1" / "video.json").read_text(encoding="utf-8"))
    assert tries[0] == crawl.ATTEMPTS and doc["comments_complete"] is False
    assert "comments incomplete after retries" in (data / "errors.jsonl").read_text(encoding="utf-8")


def test_complete_comments_are_flagged_complete(env):
    data, _, _, _ = env
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    assert json.loads((data / "videos" / "1" / "video.json").read_text(encoding="utf-8"))["comments_complete"] is True


def test_login_required_in_a_tab_stops_the_run(env):
    data, calls, cfg, write_list = env
    cfg.update(tabs=2)
    write_list([_row(i) for i in range(1, 5)])
    calls["comments"] = lambda url: (_ for _ in ()).throw(browser.LoginRequired("tiktok"))
    with pytest.raises(browser.LoginRequired):
        asyncio.run(crawl.run("dalat", profile=fake_profile))


def test_tab_is_free_while_the_video_downloads(env, monkeypatch):
    # One tab: the second video's comments must start while the first video is still downloading.
    data, calls, _, write_list = env
    write_list([_row(1), _row(2)])
    second_started = asyncio.Event()

    async def comments(ctx, url, limit):
        if url.endswith("/2"):
            second_started.set()
        return _page_item(url.rsplit("/", 1)[1]), [{"comment_id": "c"}], True

    async def download(ctx, url, path):
        if path.parent.name == "1":
            await asyncio.wait_for(second_started.wait(), 2)
        files.write_bytes(path, b"mp4")

    monkeypatch.setattr(crawl, "comments", comments)
    monkeypatch.setattr(crawl, "download_video", download)
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    assert (data / "videos" / "1" / "video.mp4").exists() and (data / "videos" / "2" / "video.mp4").exists()


def test_only_videos_kept_by_filter_are_crawled(env):
    data, calls, _, write_list = env
    write_list([_row(1), _row(2), _row(3)])
    calls["kept"] = {"1", "3"}  # 2 judged not about travel; unjudged videos are not kept either
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    assert sorted(u.rsplit("/", 1)[1] for u in calls["opened"]) == ["1", "3"]
    assert not (data / "videos" / "2").exists()


def test_video_only_skips_comment_panel_and_defers_comments(env):
    data, calls, cfg, _ = env
    asyncio.run(crawl.crawl_videos([_row(1)], cfg, data, False, fake_profile, with_comments=False))
    doc = json.loads((data / "videos" / "1" / "video.json").read_text(encoding="utf-8"))
    assert doc["comments"] == [] and doc["comments_complete"] is None
    assert (data / "videos" / "1" / "video.mp4").exists()
    assert calls["opened"] == ["https://www.tiktok.com/@a/video/1"]  # open_item, never the comment-panel comments()


def test_crawl_comments_fills_in_a_video_only_record(env):
    data, calls, cfg, _ = env
    asyncio.run(crawl.crawl_videos([_row(1)], cfg, data, False, fake_profile, with_comments=False))
    v = data / "videos" / "1" / "video.json"
    doc = json.loads(v.read_text(encoding="utf-8"))
    doc["places"] = [{"fid": "f1", "verdict": "yes"}]  # place_verify's own write, must survive the comments update
    v.write_text(json.dumps(doc), encoding="utf-8")
    asyncio.run(crawl.crawl_comments([{"video_id": "1", "url": _row(1)["url"]}], cfg, data, False, fake_profile))
    doc = json.loads(v.read_text(encoding="utf-8"))
    assert doc["comments_complete"] is True and [c["comment_id"] for c in doc["comments"]] == ["c1"]
    assert doc["places"] == [{"fid": "f1", "verdict": "yes"}]
    assert doc["video_path"] == "tiktok/videos/1/video.mp4"  # kept from the video-only write, not rebuilt from row


def test_crawl_needs_list(data, monkeypatch):
    monkeypatch.setattr(crawl, "load_config", lambda city: ("Đà Lạt", {"tiktok": {}}))
    with pytest.raises(SystemExit, match="tiktok list"):
        asyncio.run(crawl.run("dalat", profile=fake_profile))


def test_a_run_of_empty_video_pages_is_a_block_but_a_lone_one_is_a_dead_video(tmp_path):
    t = crawl.MissWatchThrottle(tmp_path / "t.json", start=4, hi=8)
    miss = crawl.NoItemData()
    for _ in range(4):
        t.success()
    assert not crawl.throttled(miss, t)  # one dead video among clean pages
    flags = [crawl.throttled(miss, t) for _ in range(5)]
    assert flags == [False, False, False, False, True]  # 6th empty page of the last 10: throttled
    assert not crawl.throttled(miss, t)  # the window started over
    assert not crawl.throttled(miss, crawl.Throttle(tmp_path / "u.json", start=4, hi=8))  # plain throttle: never
