import asyncio
import json
import time
from contextlib import asynccontextmanager

import pytest

from corpus.crawl.tiktok import clips, place_filter, poi_crawl

DAY = 86400


def _item(i, author=None, saves=0, likes=0, age_days=0, duration=20, desc="", photo=False, ad=False):
    it = {"id": str(i), "desc": desc, "createTime": int(time.time() - age_days * DAY), "author": {"uniqueId": author or f"a{i}"},
          "stats": {"collectCount": saves, "shareCount": 0, "diggCount": likes}, "isAd": ad,
          "video": {"duration": duration, **({} if photo else {"playAddr": f"http://v/{i}"})}}
    return {**it, "imagePost": {}} if photo else it


def test_score_leaves_out_what_cannot_be_shown_and_favours_saved_recent_named_clips():
    keys = poi_crawl.name_keys("Tiệm cà phê Thênh Thang")
    assert poi_crawl.score(_item(1, photo=True)) is None
    assert poi_crawl.score(_item(1, ad=True, saves=9)) is None
    assert poi_crawl.score(_item(1, duration=3, saves=9)) is None and poi_crawl.score(_item(1, duration=400, saves=9)) is None
    assert poi_crawl.score(_item(1, saves=100)) == pytest.approx(100, rel=0.01)
    assert poi_crawl.score(_item(1, saves=100, age_days=365)) == pytest.approx(50, rel=0.01)  # a year halves it
    assert poi_crawl.score(_item(1, saves=100, desc="chill #thenhthang"), keys) == pytest.approx(400, rel=0.01)
    assert poi_crawl.score(_item(1, saves=100, desc="cà phê đà lạt"), keys) == pytest.approx(100, rel=0.01)  # generic words


def test_name_keys_skip_generic_pairs():
    assert poi_crawl.name_keys("Xuan Huong Lake") == {"xuanhuong", "huonglake"}
    assert "caphe" not in poi_crawl.name_keys("Tiệm cà phê Thênh Thang")


def test_pick_keeps_one_clip_per_author():
    rows = poi_crawl.parse_list({"itemList": [_item(1, "x", saves=9), _item(2, "x", saves=8), _item(3, "y", saves=1),
                                              _item(4, "z", photo=True)], "hasMore": True})[0]
    assert [r["video_id"] for r in poi_crawl.pick(rows, 5)] == ["1", "3"]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    root = tmp_path / "tiktok"
    monkeypatch.setattr(poi_crawl, "load_config", lambda city: ("Đà Lạt", {"tiktok": {
        "poi_list_items": 90, "poi_download": 2, "poi_tabs": 2, "clips_per_place": 2}}))
    (root / "place_poi").mkdir(parents=True)
    (root / "place_poi" / "dalat.json").write_text(json.dumps({"places": {
        "f:1": {"name": "Quán A", "category": "Cà phê", "address": "1 Hùng Vương",
                "poi": {"id": "p1", "name": "Quan A", "address": "1", "category": "x"}},
        "f:2": {"name": "Quán B", "category": "Cà phê", "address": None, "poi": None}}}), encoding="utf-8")
    listed, downloaded = [], []
    lists = {"p1": [_item(1, saves=9), _item(2, saves=5), _item(3, saves=1)]}

    async def list_place(ctx, poi_id, limit, keys=frozenset()):
        listed.append(poi_id)
        return poi_crawl.parse_list({"itemList": lists[poi_id]}, keys)[0]

    async def download(ctx, url, path):
        if url in fail:
            raise RuntimeError("video HTTP 403")
        downloaded.append(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"mp4")

    @asynccontextmanager
    async def sessions(headed=False):
        async def new():
            return object()
        yield new

    fail = set()
    monkeypatch.setattr(poi_crawl, "list_place", list_place)
    monkeypatch.setattr(poi_crawl, "download_video", download)
    return root, sessions, listed, downloaded, fail


def test_poi_crawl_downloads_the_best_videos_of_mapped_places_once(env):
    root, sessions, listed, downloaded, _ = env
    asyncio.run(poi_crawl.run("dalat", sessions=sessions))
    assert listed == ["p1"]  # the unmapped place is never opened
    assert sorted(downloaded) == ["http://v/1", "http://v/2"]
    doc = json.loads((root / "poi_crawl" / "f_1.json").read_text(encoding="utf-8"))
    assert [v["video_id"] for v in doc["videos"]] == ["1", "2"] and doc["listed"] == 3 and doc["poi"]["id"] == "p1"
    v = json.loads((root / "videos" / "1" / "video.json").read_text(encoding="utf-8"))
    assert v["comments_complete"] is None and v["video_path"] == "tiktok/videos/1/video.mp4"
    assert json.loads((root / "videos" / "1" / "info.json").read_text(encoding="utf-8"))["id"] == "1"
    assert {p["fid"] for p in place_filter.places_by_video("dalat")["1"]} == {"f:1"}  # asr_check / place_verify see it
    asyncio.run(poi_crawl.run("dalat", sessions=sessions))
    assert listed == ["p1"]  # done places are not listed again


def test_a_failed_download_leaves_the_place_for_the_next_run(env):
    root, sessions, listed, _, fail = env
    fail.add("http://v/2")
    asyncio.run(poi_crawl.run("dalat", sessions=sessions))
    assert not (root / "poi_crawl" / "f_1.json").exists()
    fail.clear()
    asyncio.run(poi_crawl.run("dalat", sessions=sessions))
    assert listed == ["p1", "p1"] and (root / "poi_crawl" / "f_1.json").exists()


def test_a_removed_clip_comes_back_and_keeps_its_verdicts(env):
    root, sessions, *_ = env
    d = root / "videos" / "1"
    d.mkdir(parents=True)
    (d / "video.json").write_text(json.dumps({"video_id": "1", "clip_removed": True, "places": [
        {"fid": "f:9", "verdict": "yes"}]}), encoding="utf-8")
    asyncio.run(poi_crawl.run("dalat", sessions=sessions))
    v = json.loads((d / "video.json").read_text(encoding="utf-8"))
    assert "clip_removed" not in v and v["places"] == [{"fid": "f:9", "verdict": "yes"}] and (d / "video.mp4").exists()


def test_clips_show_the_best_verified_videos_on_disk_one_per_author(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(clips, "load_config", lambda city: ("Đà Lạt", {"tiktok": {"clips_per_place": 2}}))
    lst = tmp_path / "gmaps" / "list" / "dalat.json"
    lst.parent.mkdir(parents=True)
    lst.write_text(json.dumps({"items": [{"fid": "f1", "name": "Quán Mây"}]}), encoding="utf-8")

    def video(i, author, saves, verdict="yes", mp4=True, desc=""):
        d = tmp_path / "tiktok" / "videos" / str(i)
        d.mkdir(parents=True)
        (d / "info.json").write_text(json.dumps(_item(i, author, saves=saves, desc=desc)), encoding="utf-8")
        (d / "video.json").write_text(json.dumps({"video_id": str(i), "video_url": f"u{i}", "author_id": author,
                                                  "caption": desc, "places": [{"fid": "f1", "verdict": verdict}]}),
                                      encoding="utf-8")
        if mp4:
            (d / "video.mp4").write_bytes(b"mp4")

    video(1, "x", 50)
    video(2, "x", 40)  # same author as 1
    video(3, "y", 30, verdict="no")  # not about the place
    video(4, "z", 900, mp4=False)  # clip deleted: cannot be played here
    video(5, "w", 5, desc="#quanmay")  # names the place: 5 x 4
    video(6, "v", 10)
    clips.run("dalat")
    got = json.loads((tmp_path / "tiktok" / "clips" / "dalat.json").read_text(encoding="utf-8"))["places"]["f1"]
    assert [c["video_id"] for c in got] == ["1", "5"]
    assert clips.picked("dalat") == {"1", "5"}
