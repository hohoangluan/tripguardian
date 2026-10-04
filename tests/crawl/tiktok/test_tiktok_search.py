import asyncio
import json

import pytest
from tiktok_helpers import fake_profile, fixture_json

from corpus.crawl.common import browser
from corpus.crawl.tiktok import search


def test_parse_search_fixture():
    items = search.parse_search(fixture_json("search.json"))
    assert items
    it = items[0]
    assert it["video_id"].isdigit() and it["url"].endswith("/video/" + it["video_id"])
    assert it["author_id"] and it["created_at"] and it["photo"] is False
    assert "raw" not in it and "play_url" not in it  # play addresses expire; the crawl phase reads a fresh one


def test_parse_search_marks_photo_post():
    payload = {"item_list": [{"id": "1", "desc": "ảnh", "createTime": 1, "author": {"uniqueId": "a"},
                              "imagePost": {}, "video": {}}]}
    assert search.parse_search(payload)[0]["photo"] is True


def _item(i):
    return {"video_id": str(i), "url": f"https://www.tiktok.com/@a/video/{i}", "author_id": "a", "desc": "d",
            "created_at": 1, "hashtags": [], "photo": False}


@pytest.fixture
def env(data, monkeypatch):
    monkeypatch.setattr(search, "load_config", lambda city: ("Đà Lạt", {"tiktok": {
        "max_videos_per_query": 5, "cooldown_s": 0, "pause_s": [0.1, 0.2],
        "queries": {"general": ["{city} có gì chơi", "{city} đi cùng gia đình"]}}}))
    calls = {"logged_in": True, "searched": [], "pauses": [], "result": lambda q: [_item(1)]}

    async def ensure_login(ctx):
        if not calls["logged_in"]:
            raise browser.LoginRequired("tiktok")

    async def fake_search(ctx, query, limit):
        calls["searched"].append(query)
        return calls["result"](query)

    async def rec(*a):
        calls["pauses"].append(a)

    monkeypatch.setattr(search, "ensure_login", ensure_login)
    monkeypatch.setattr(search, "search", fake_search)
    monkeypatch.setattr(search, "pause", rec)
    return data, calls


def test_run_writes_one_file_per_query_and_skips_searched(env):
    data, calls = env
    asyncio.run(search.run("dalat", profile=fake_profile))
    asyncio.run(search.run("dalat", profile=fake_profile))
    assert calls["searched"] == ["Đà Lạt có gì chơi", "Đà Lạt đi cùng gia đình"]
    rec = json.loads((data / "search" / "dalat" / "da-lat-co-gi-choi.jsonl").read_text(encoding="utf-8"))
    assert rec["group"] == "general" and rec["query"] == "Đà Lạt có gì chơi" and rec["items"][0]["video_id"] == "1"
    assert (0.1, 0.2) in calls["pauses"]


def test_blocked_search_is_retried_then_logged(env):
    data, calls = env
    tries = []

    def result(q):
        tries.append(q)
        if "gia đình" in q or tries.count(q) == 1:  # "gia đình" stays blocked, the other is blocked once
            raise RuntimeError("Page.goto: net::ERR_HTTP_RESPONSE_CODE_FAILURE")
        return [_item(1)]

    calls["result"] = result
    asyncio.run(search.run("dalat", profile=fake_profile))
    assert tries.count("Đà Lạt đi cùng gia đình") == 3 and tries.count("Đà Lạt có gì chơi") == 2
    assert (data / "search" / "dalat" / "da-lat-co-gi-choi.jsonl").exists()
    assert not (data / "search" / "dalat" / "da-lat-di-cung-gia-dinh.jsonl").exists()  # searched again next run
    assert '"stage": "search"' in (data / "errors.jsonl").read_text(encoding="utf-8")


def test_empty_result_is_not_saved(env):
    data, calls = env
    calls["result"] = lambda q: []
    asyncio.run(search.run("dalat", profile=fake_profile))
    assert not (data / "search").exists() and "no videos" in (data / "errors.jsonl").read_text(encoding="utf-8")


def test_not_logged_in_stops_before_writing(env):
    data, calls = env
    calls["logged_in"] = False
    with pytest.raises(browser.LoginRequired):
        asyncio.run(search.run("dalat", profile=fake_profile))
    assert not (data / "search").exists()


def test_empty_result_is_retried(env):
    # The search page sometimes reloads itself and never calls the search API; opening it again works.
    data, calls = env
    tries = []

    def result(q):
        tries.append(q)
        return [] if tries.count(q) == 1 else [_item(1)]

    calls["result"] = result
    asyncio.run(search.run("dalat", profile=fake_profile))
    assert tries.count("Đà Lạt có gì chơi") == 2
    assert (data / "search" / "dalat" / "da-lat-co-gi-choi.jsonl").exists()
