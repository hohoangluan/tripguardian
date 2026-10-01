import json

import pytest

from corpus import review


def _w(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    t, g = tmp_path / "tiktok", tmp_path / "gmaps"
    _w(t / "list" / "dalat.json", {"items": [
        {"video_id": str(i), "url": f"https://www.tiktok.com/@a/video/{i}", "desc": f"caption {i}", "hashtags": [],
         "photo": False} for i in range(1, 6)]})
    for vid, rel in (("1", "yes"), ("2", "no"), ("3", "unsure")):
        _w(t / "filter" / f"{vid}.json", {"video_id": vid, "desc": f"caption {vid}", "llm": {"relevance": rel, "reason": "r"}})
    _w(t / "videos" / "4" / "video.json", {"video_id": "4", "caption": "c", "comments_complete": False, "fetched_at": "t1",
                                           "comments": [], "stats": {"commentCount": 9}})
    (t / "videos" / "4" / "video.mp4").write_bytes(b"x")
    _w(t / "videos" / "5" / "video.json", {"video_id": "5", "caption": "c", "fetched_at": "t1", "comments": [], "stats": {}})
    (t / "videos" / "5" / "video.mp4").write_bytes(b"x")  # crawled before comments_complete existed
    place = {"fid": "0x1:0x2", "name": "Quán A", "url": "https://maps/x", "category": "Quán cà phê", "address": "Đà Lạt",
             "fetched_at": "t1", "reviews_complete": False, "review_count": "50 bài đánh giá"}
    _w(g / "places" / "0x1_0x2" / "place.json", place)
    _w(g / "places" / "0x1_0x2" / "reviews.json", [])
    _w(g / "qc" / "0x1_0x2.json", {"fid": "0x1:0x2", "fetched_at": "t1", "checks": ["reviews_short:0/30"],
                                   "llm": {"verdict": "bad", "tourism_relevant": False, "relevance_reason": "pharmacy",
                                           "in_city": True, "field_issues": [], "bad_reviews": []}})
    _w(g / "qc" / "summary.json", {})
    return tmp_path


def test_queue_lists_only_items_that_need_a_person(data):
    items = review.queue("dalat")
    keys = {(i["kind"], i["id"]) for i in items}
    assert ("video_filter", "2") in keys and ("video_filter", "3") in keys and ("video_filter", "1") not in keys
    assert ("video_comments", "4") in keys and ("video_comments", "5") in keys
    assert ("place_qc", "0x1:0x2") in keys and ("place_reviews", "0x1:0x2") in keys
    f = next(i for i in items if i["id"] == "2")
    assert f["actions"] == ["keep", "drop"] and f["url"].endswith("/video/2") and "caption 2" in f["title"]


def test_decision_hides_item_and_latest_wins(data):
    review.decide("video_filter", "2", "keep", "it is a cafe")
    review.decide("video_filter", "2", "drop")
    assert review.decisions("video_filter") == {"2": "drop"}
    assert ("video_filter", "2") not in {(i["kind"], i["id"]) for i in review.queue("dalat")}
    assert ("video_filter", "2") in {(i["kind"], i["id"]) for i in review.queue("dalat", decided=True)}
    line = json.loads((data / "review" / "decisions.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert line["note"] == "it is a cafe" and line["decision"] == "keep" and line["at"]


def test_unknown_action_is_rejected(data):
    with pytest.raises(ValueError):
        review.decide("video_filter", "2", "accept")


def test_retry_decision_is_pending_until_the_item_is_fetched_again(data):
    review.decide("place_reviews", "0x1:0x2", "retry")
    assert review.retry_ids("place_reviews") == {"0x1:0x2"}


def test_person_overrides_filter_in_kept_ids(data):
    from corpus.crawl.tiktok import filter as tfilter
    assert tfilter.kept_ids("dalat") == {"1", "3"}
    review.decide("video_filter", "2", "keep")
    review.decide("video_filter", "3", "drop")
    assert tfilter.kept_ids("dalat") == {"1", "2"}


def test_retry_is_done_once_the_item_is_fetched_after_the_decision(data):
    rec = review.decide("video_comments", "4", "retry")
    assert review.retry_ids("video_comments", {"4": "2026-01-01T00:00:00+00:00"}) == {"4"}  # fetched before it
    assert review.retry_ids("video_comments", {"4": rec["at"] + "Z"}) == set()  # fetched again since


def test_server_serves_queue_and_records_decisions(data):
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer

    from corpus.review import server
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.handler("dalat"))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        assert b"Duy" in urllib.request.urlopen(base + "/").read()
        q = json.loads(urllib.request.urlopen(base + "/api/queue").read())
        assert {i["kind"] for i in q["items"]} == {"video_filter", "video_comments", "place_qc", "place_reviews"}
        req = urllib.request.Request(base + "/api/decision", method="POST", headers={"Content-Type": "application/json"},
                                     data=json.dumps({"kind": "place_qc", "id": "0x1:0x2", "decision": "disable"}).encode())
        assert json.loads(urllib.request.urlopen(req).read())["decision"] == "disable"
        bad = urllib.request.Request(base + "/api/decision", method="POST", data=b'{"kind": "place_qc", "id": "x", "decision": "keep"}')
        try:
            urllib.request.urlopen(bad)
            raise AssertionError("expected 400")
        except urllib.error.HTTPError as e:
            assert e.code == 400
    finally:
        srv.shutdown()


def test_video_place_pairs_not_verified_go_to_review_and_a_person_decides(data):
    from corpus.crawl.tiktok import place_verify

    t = data / "tiktok"
    places = [{"fid": "f1", "name": "Thác Datanla", "verdict": "yes", "reason": "sign", "evidence": []},
              {"fid": "f2", "name": "Khu du lịch Quỷ Núi", "verdict": "no", "reason": "names PiNi",
               "evidence": [{"source": "frame", "quote": "frame 1: sign 'Pini Dalat'"}]},
              {"fid": "f3", "name": "Quán B", "verdict": "unsure", "reason": "no name", "evidence": []}]
    _w(t / "videos" / "6" / "video.json", {"video_id": "6", "caption": "Khám phá Quỷ Núi", "comments_complete": True,
                                           "comments": [], "places": places, "transcript": {"text": "quần thể PiNi"}})
    (t / "videos" / "6" / "video.mp4").write_bytes(b"x")
    items = {i["id"]: i for i in review.queue("dalat") if i["kind"] == "place_verify"}
    assert set(items) == {"6@f2", "6@f3"} and items["6@f2"]["details"]["transcript"] == "quần thể PiNi"
    assert place_verify.evidence_pairs() == {("6", "f1")}
    review.decide("place_verify", "6@f2", "keep")
    review.decide("place_verify", "6@f1", "drop")
    assert place_verify.evidence_pairs() == {("6", "f2")}
    assert {i["id"] for i in review.queue("dalat") if i["kind"] == "place_verify"} == {"6@f3"}
