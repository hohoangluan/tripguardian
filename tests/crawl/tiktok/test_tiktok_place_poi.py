import asyncio
import json
from types import SimpleNamespace

import pytest

from corpus.crawl.tiktok import crawl, place_poi


def _poi(i, tiny="Quán cà phê", address=None):
    return {"id": f"p{i}", "name": f"POI {i}", "address": address or f"{i} Hùng Vương", "category": "Đồ uống",
            "ttTypeNameTiny": tiny}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(place_poi, "load_config", lambda city: ("Đà Lạt", {}))
    monkeypatch.setattr(place_poi, "_client", lambda: (None, "gemma-test"))
    calls, answers = [], {}

    async def ask(client, model, **f):
        maps, tiktok = sorted(f["pair"].split("\n"))  # "Google Maps: …" sorts before "TikTok place: …"
        key = (maps.split(": ")[1].split(" | ")[0], tiktok.split(": ")[1].split(" | ")[0])
        calls.append(key)
        a = answers.get(key, "same_place")
        if callable(a):
            a = a(f["pair"].startswith("TikTok"))
        if isinstance(a, Exception):
            raise a
        return {"relation": a, "reason": "r"}

    monkeypatch.setattr(place_poi, "PLACE_POI_MATCH", SimpleNamespace(ask=ask, prompt_hash="h1", parallel=2))
    lst = tmp_path / "gmaps" / "list" / "dalat.json"
    lst.parent.mkdir(parents=True)
    lst.write_text(json.dumps({"items": [{"fid": "f1", "name": "Quán A", "category": "Cà phê"},
                                         {"fid": "f2", "name": "Quán B", "category": "Cà phê"}]}), encoding="utf-8")

    def video(video_id, fid, poi, verdict="yes"):
        d = tmp_path / "tiktok" / "videos" / video_id
        d.mkdir(parents=True)
        (d / "info.json").write_text(json.dumps({"id": video_id, **({"poi": poi} if poi else {})}), encoding="utf-8")
        (d / "video.json").write_text(json.dumps({"video_id": video_id, "places": [
            {"fid": fid, "name": "x", "verdict": verdict}]}), encoding="utf-8")

    def result():
        return json.loads((tmp_path / "tiktok" / "place_poi" / "dalat.json").read_text(encoding="utf-8"))["places"]

    return video, calls, answers, result


def test_most_tagged_same_place_poi_maps_and_areas_or_unverified_videos_never_count(env):
    video, calls, answers, result = env
    video("1", "f1", _poi(1))
    video("2", "f1", _poi(2))
    video("3", "f1", _poi(2))
    video("4", "f1", _poi(9, tiny="Thành phố"))  # the city: never a candidate
    video("5", "f1", _poi(8), verdict="no")  # not evidence for the place
    video("6", "f2", None)  # untagged
    video("7", "fX", _poi(7))  # place outside the city list
    answers[("Quán A", "POI 2")] = "part_of"
    asyncio.run(place_poi.run("dalat"))
    places = result()
    assert set(places) == {"f1"}
    assert [(c["id"], c["videos"]) for c in places["f1"]["candidates"]] == [("p2", 2), ("p1", 1)]
    assert places["f1"]["poi"] == {"id": "p1", "name": "POI 1", "address": "1 Hùng Vương", "category": "Đồ uống"}
    assert sorted(calls) == [("Quán A", "POI 1")] * 2 + [("Quán A", "POI 2")] * 2  # each pair read in both orders


def test_branch_or_different_maps_nothing(env):
    video, _, answers, result = env
    video("1", "f1", _poi(1))
    answers[("Quán A", "POI 1")] = "branch"
    asyncio.run(place_poi.run("dalat"))
    assert result()["f1"]["poi"] is None


def test_reads_that_disagree_are_unsure_and_map_nothing(env):
    video, _, answers, result = env
    video("1", "f1", _poi(1))
    answers[("Quán A", "POI 1")] = lambda swapped: "part_of" if swapped else "same_place"
    asyncio.run(place_poi.run("dalat"))
    place = result()["f1"]
    assert place["poi"] is None and place["candidates"][0]["relation"] == "unsure"


def test_candidate_judged_once_until_its_address_changes_and_errors_retry_next_run(env):
    video, calls, answers, result = env
    video("1", "f1", _poi(1))
    video("2", "f1", _poi(2))
    answers[("Quán A", "POI 2")] = RuntimeError("model down")
    asyncio.run(place_poi.run("dalat"))
    assert [c["id"] for c in result()["f1"]["candidates"]] == ["p1"]  # the failed one is left unjudged
    calls.clear()
    answers.pop(("Quán A", "POI 2"))
    asyncio.run(place_poi.run("dalat"))
    assert calls == [("Quán A", "POI 2")] * 2
    calls.clear()
    info = json.loads((place_poi.data_dir() / "tiktok" / "videos" / "1" / "info.json").read_text(encoding="utf-8"))
    info["poi"]["address"] = "2 Trần Phú"
    (place_poi.data_dir() / "tiktok" / "videos" / "1" / "info.json").write_text(json.dumps(info), encoding="utf-8")
    asyncio.run(place_poi.run("dalat"))
    assert calls == [("Quán A", "POI 1")] * 2


def test_video_doc_keeps_the_tagged_tiktok_place():
    row = {"video_id": "7", "url": "u"}
    assert crawl.video_doc(row, {"id": "7"}, [], "p")["poi"] is None
    doc = crawl.video_doc(row, {"id": "7", "poi": {**_poi(1), "cityCode": "1"}}, [], "p")
    assert doc["poi"] == {"id": "p1", "name": "POI 1", "address": "1 Hùng Vương", "category": "Đồ uống"}


def test_a_poi_claimed_by_two_places_goes_to_the_most_tagged_and_a_tie_to_none(env):
    video, _, _, result = env
    video("1", "f1", _poi(1))
    video("2", "f1", _poi(1))
    video("3", "f2", _poi(1))  # "Cầu thang chợ đêm" also judged the night market itself
    asyncio.run(place_poi.run("dalat"))
    places = result()
    assert places["f1"]["poi"]["id"] == "p1" and "shared_with" not in places["f1"]
    assert places["f2"]["poi"] is None and places["f2"]["shared_with"] == ["f1"]
    video("4", "f2", _poi(1))
    asyncio.run(place_poi.run("dalat"))
    assert result()["f1"]["poi"] is None and result()["f2"]["poi"] is None


def test_entries_the_judge_merged_share_their_poi(env, monkeypatch):
    video, _, _, result = env
    monkeypatch.setattr(place_poi, "merges", lambda: {"f2": "f1"})  # "Hồ Xuân Hương" listed twice
    video("1", "f1", _poi(1))
    video("2", "f2", _poi(1))
    asyncio.run(place_poi.run("dalat"))
    assert result()["f1"]["poi"]["id"] == result()["f2"]["poi"]["id"] == "p1"
