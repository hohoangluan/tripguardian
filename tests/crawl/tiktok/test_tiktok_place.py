import asyncio
import json

import pytest
from tiktok_helpers import fake_profile

from corpus.crawl.common import browser
from corpus.crawl.tiktok import crawl, place_crawl, place_filter, place_search

FID = "0x1:0x2"


def _item(i, desc="d"):
    return {"video_id": str(i), "url": f"https://www.tiktok.com/@a/video/{i}", "author_id": "a", "desc": desc,
            "created_at": 1, "hashtags": ["dalat"], "photo": False}


def _write_gmaps_list(tmp_path, places):
    f = tmp_path / "gmaps" / "list" / "dalat.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"items": places}, ensure_ascii=False), encoding="utf-8")


def test_query_adds_the_city_unless_the_name_has_it():
    assert place_search.query_for("Thác Datanla", "Đà Lạt") == "Thác Datanla Đà Lạt"
    assert place_search.query_for("Chợ Đà Lạt", "Đà Lạt") == "Chợ Đà Lạt"
    assert place_search.query_for("Cho Da Lat", "Đà Lạt") == "Cho Da Lat"


@pytest.fixture
def search_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(place_search, "load_config", lambda city: ("Đà Lạt", {"tiktok": {
        "videos_per_place": 2, "cooldown_s": 0, "place_search_pause_s": [0.1, 0.2]}}))
    _write_gmaps_list(tmp_path, [{"fid": FID, "name": "Thác Datanla", "category": "Thác"},
                                 {"fid": "0x3:0x4", "name": "Chợ Đà Lạt", "category": "Chợ"}])
    calls = {"searched": [], "result": lambda q: ([_item(1), _item(2)], True)}

    async def ensure_login(ctx):
        pass

    async def fake_search(ctx, query, limit):
        calls["searched"].append((query, limit))
        return calls["result"](query)

    async def no_pause(*a):
        pass

    monkeypatch.setattr(place_search, "ensure_login", ensure_login)
    monkeypatch.setattr(place_search, "search_place", fake_search)
    monkeypatch.setattr(place_search, "pause", no_pause)
    return tmp_path / "tiktok", calls


def test_place_search_writes_one_file_per_place_and_skips_searched(search_env):
    root, calls = search_env
    asyncio.run(place_search.run("dalat", profile=fake_profile))
    asyncio.run(place_search.run("dalat", profile=fake_profile))
    assert sorted(calls["searched"]) == [("Chợ Đà Lạt", 2), ("Thác Datanla Đà Lạt", 2)]
    doc = json.loads((root / "place_search" / "dalat" / "0x1_0x2.json").read_text(encoding="utf-8"))
    assert doc["fid"] == FID and doc["query"] == "Thác Datanla Đà Lạt" and [i["video_id"] for i in doc["items"]] == ["1", "2"]


def test_place_search_that_never_ends_is_retried_then_logged_not_saved(search_env):
    root, calls = search_env
    calls["result"] = lambda q: ([_item(1)], False)
    asyncio.run(place_search.run("dalat", profile=fake_profile))
    assert not list((root / "place_search" / "dalat").glob("*.json"))
    assert len(calls["searched"]) == 2 * place_search.ATTEMPTS
    assert "never ended" in (root / "errors.jsonl").read_text(encoding="utf-8")


def test_empty_search_that_ended_is_saved(search_env):
    root, calls = search_env
    calls["result"] = lambda q: ([], True)
    asyncio.run(place_search.run("dalat", profile=fake_profile))
    assert json.loads((root / "place_search" / "dalat" / "0x1_0x2.json").read_text(encoding="utf-8"))["items"] == []


def test_place_search_login_required_stops(search_env, monkeypatch):
    async def logged_out(ctx):
        raise browser.LoginRequired("tiktok")

    monkeypatch.setattr(place_search, "ensure_login", logged_out)
    with pytest.raises(browser.LoginRequired):
        asyncio.run(place_search.run("dalat", profile=fake_profile))


@pytest.fixture
def filter_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(place_filter, "load_config", lambda city: ("Đà Lạt", {}))
    monkeypatch.setattr(place_filter, "_client", lambda: (None, "gemma-test"))
    root = tmp_path / "tiktok"
    calls, answers = [], {}

    async def classify(client, model, place, row, city):
        calls.append((place["name"], place["address"], row["video_id"]))
        return answers.get(row["video_id"], {"relevance": "yes", "reason": "names the place"})

    monkeypatch.setattr(place_filter, "classify", classify)

    def write_search(fid, name, items):
        f = root / "place_search" / "dalat" / f"{fid.replace(':', '_')}.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"fid": fid, "name": name, "category": "Thác", "query": f"{name} Đà Lạt",
                                 "items": items}, ensure_ascii=False), encoding="utf-8")

    return tmp_path, root, write_search, calls, answers


def test_place_filter_judges_each_video_once_and_keeps_only_yes(filter_env):
    tmp_path, root, write_search, calls, answers = filter_env
    write_search(FID, "Thác Datanla", [_item(1), _item(2), _item(3), {**_item(4), "photo": True}])
    answers["2"] = {"relevance": "no", "reason": "another waterfall"}
    answers["3"] = {"relevance": "unsure", "reason": "only hashtags"}
    summary = asyncio.run(place_filter.run("dalat"))
    asyncio.run(place_filter.run("dalat"))
    assert sorted(c[2] for c in calls) == ["1", "2", "3"]  # photo post not judged; second run reuses answers
    assert summary["relevance"] == {"yes": 1, "no": 1, "unsure": 1} and summary["kept"] == 1
    assert [r["video_id"] for r in place_filter.kept_videos("dalat")] == ["1"]


def test_place_filter_judges_again_when_caption_or_address_changes(filter_env):
    tmp_path, root, write_search, calls, _ = filter_env
    write_search(FID, "Thác Datanla", [_item(1)])
    asyncio.run(place_filter.run("dalat"))
    write_search(FID, "Thác Datanla", [_item(1, "caption mới")])
    asyncio.run(place_filter.run("dalat"))
    place = tmp_path / "gmaps" / "places" / "0x1_0x2" / "place.json"
    place.parent.mkdir(parents=True)
    place.write_text(json.dumps({"fid": FID, "address": "Đèo Prenn"}), encoding="utf-8")
    asyncio.run(place_filter.run("dalat"))
    assert calls == [("Thác Datanla", None, "1"), ("Thác Datanla", None, "1"), ("Thác Datanla", "Đèo Prenn", "1")]


def test_model_error_leaves_the_video_unjudged(filter_env, monkeypatch):
    tmp_path, root, write_search, calls, _ = filter_env
    write_search(FID, "Thác Datanla", [_item(1)])

    async def boom(*a):
        raise RuntimeError("429")

    monkeypatch.setattr(place_filter, "classify", boom)
    assert asyncio.run(place_filter.run("dalat"))["llm_errors"] == 1
    assert place_filter.kept_videos("dalat") == []


def test_video_kept_for_two_places_is_listed_once(filter_env):
    tmp_path, root, write_search, _, _ = filter_env
    write_search(FID, "Thác Datanla", [_item(1)])
    write_search("0x3:0x4", "Máng trượt Datanla", [_item(1)])
    asyncio.run(place_filter.run("dalat"))
    [row] = place_filter.kept_videos("dalat")
    assert row["places"] == [FID, "0x3:0x4"] and len(row["queries"]) == 2


def test_cap_per_place_keeps_each_place_own_first_n_yes_videos(filter_env):
    tmp_path, root, write_search, _, _ = filter_env
    write_search(FID, "Thác Datanla", [_item(1), _item(2), _item(3)])
    asyncio.run(place_filter.run("dalat"))
    assert [r["video_id"] for r in place_filter.kept_videos("dalat", cap_per_place=2)] == ["1", "2"]
    assert [r["video_id"] for r in place_filter.kept_videos("dalat")] == ["1", "2", "3"]  # no cap: unchanged


def test_cap_per_place_keeps_a_video_shared_by_an_uncapped_place(filter_env):
    tmp_path, root, write_search, _, _ = filter_env
    write_search(FID, "Thác Datanla", [_item(1), _item(2)])  # video 2 would be cut by this place's own cap=1
    write_search("0x3:0x4", "Máng trượt Datanla", [_item(2)])  # but this place still has room for it
    asyncio.run(place_filter.run("dalat"))
    assert sorted(r["video_id"] for r in place_filter.kept_videos("dalat", cap_per_place=1)) == ["1", "2"]


def test_prompt_shows_place_and_caption():
    msg = place_filter.PLACE_VIDEO_FILTER.render(city="Đà Lạt", name="Thác Datanla", category="Thác", address="Đèo Prenn",
                                                 desc="Máng trượt siêu phê", hashtags="#datanla")
    assert all(s in msg for s in ("Thác Datanla", "Đèo Prenn", "Máng trượt siêu phê", "#datanla"))


def test_place_crawl_opens_only_kept_videos_not_yet_saved(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(place_crawl, "load_config", lambda city: ("Đà Lạt", {"tiktok": {"tabs": 1}}))
    monkeypatch.setattr(place_crawl, "kept_videos", lambda city, cap_per_place=None: [_item(1), _item(2)])
    done = tmp_path / "tiktok" / "videos" / "2" / "video.mp4"
    done.parent.mkdir(parents=True)
    done.write_bytes(b"mp4")
    got = []

    async def fake_crawl(todo, c, root, headed, profile, profile_name=None, with_comments=True):
        got.extend(r["video_id"] for r in todo)

    monkeypatch.setattr(crawl, "crawl_videos", fake_crawl)
    asyncio.run(place_crawl.run("dalat", profile=fake_profile))
    assert got == ["1"]


def test_place_search_again_only_when_the_saved_list_was_cut_by_a_smaller_cap(tmp_path):
    f = tmp_path / "p.json"
    assert place_search.needs_search(f, 20)  # no file
    f.write_text(json.dumps({"items": [{}] * 10}), encoding="utf-8")  # legacy file, cap 10, full: maybe more
    assert place_search.needs_search(f, 20) and not place_search.needs_search(f, 10)
    f.write_text(json.dumps({"items": [{}] * 6}), encoding="utf-8")  # legacy file the list ended in
    assert not place_search.needs_search(f, 20)
    f.write_text(json.dumps({"cap": 20, "items": [{}] * 20}), encoding="utf-8")
    assert not place_search.needs_search(f, 20) and place_search.needs_search(f, 30)
