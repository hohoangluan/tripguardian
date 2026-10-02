import asyncio
import json

from corpus.observe.tiktok import extract

SEGS = [{"start_s": 0.0, "end_s": 3.0, "text": "x", "checked_text": "phải leo hơn ba trăm bậc thang", "status": "ok"},
        {"start_s": 3.0, "end_s": 6.0, "text": "x", "checked_text": "lalala", "status": "lyrics"},
        {"start_s": 6.0, "end_s": 9.0, "text": "x", "checked_text": "đi xe lên tận nơi", "status": "fixed"}]


class Stub:
    def __init__(self, fn):
        self.fn, self.prompt_hash, self.parallel = fn, "h", 4

    async def ask(self, client, model, images=(), **fields):
        return self.fn(images, fields)


def setup(tmp_path, monkeypatch, answer, verdict="supports", pairs=(("v1", "F1"),)):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "gmaps" / "list").mkdir(parents=True)
    (tmp_path / "gmaps" / "list" / "dalat.json").write_text(json.dumps({"items": [
        {"fid": "F1", "name": "Đồi A", "category": "Đồi"}, {"fid": "F2", "name": "Quán B", "category": "Quán cà phê"}]}),
        encoding="utf-8")
    for vid in {p[0] for p in pairs}:
        d = tmp_path / "tiktok" / "videos" / vid
        d.mkdir(parents=True)
        (d / "video.mp4").write_bytes(b"x")
        (d / "video.json").write_text(json.dumps({
            "video_id": vid, "caption": "Đồi A view đẹp", "hashtags": ["doia"], "author_id": "u1",
            "created_at": "1767225600", "fetched_at": "2026-09-30T00:00:00",
            "transcript": {"at": "t", "total_s": 12.0, "segments": SEGS,
                           "check": {"at": "c", "screen_text": ["ĐỒI A"], "quality": "good"}}}), encoding="utf-8")
    calls = {"observe": [], "verify": []}

    def observe(images, fields):
        calls["observe"].append((len(images), fields["others"]))
        return answer

    def verify(images, fields):
        calls["verify"].append((len(images), fields["passage"]))
        return {"verdict": verdict, "reason": "r"}

    monkeypatch.setattr(extract, "VIDEO_OBSERVE", Stub(observe))
    monkeypatch.setattr(extract, "VIDEO_VERIFY", Stub(verify))
    monkeypatch.setattr(extract, "load_config", lambda city: ("Đà Lạt", {}))
    monkeypatch.setattr(extract, "_client", lambda: (None, "m"))
    monkeypatch.setattr(extract, "frames", lambda mp4, total, out: [b"jpg"] * 4)
    monkeypatch.setattr(extract, "evidence_pairs", lambda: set(pairs))
    return calls


def o(feature, value, source, ref, quote):
    return {"feature": feature, "value": value, "source": source, "ref": ref, "quote": quote,
            "time_of_day": "unknown", "day_type": "unknown", "weather": "unknown"}


ANSWER = {"observations": [
    o("steep_or_stairs", "present", "speech", 1, "leo hơn ba trăm bậc thang"),
    o("scenic_view", "present", "caption", 0, "view đẹp"),
    o("setting", "outdoor", "frame", 2, "open hillside"),
    o("steep_or_stairs", "absent", "frame", 3, "flat path"),  # a picture cannot prove absent
    o("crowd", "low", "speech", 2, "lalala"),  # lyrics segment is not sent, so not quotable
    o("long_walk", "present", "speech", 3, "đi bộ xa"),  # not in that segment
    o("kids", "suitable", "frame", 1, "children playing"),  # suitability never from a frame
]}


def test_gate_keeps_quotes_in_their_segment_and_frames_only_for_visible_features(tmp_path, monkeypatch):
    calls = setup(tmp_path, monkeypatch, ANSWER)
    summary = asyncio.run(extract.run("dalat"))
    assert summary["status"] == {"done": 1}
    doc = json.loads((tmp_path / "tiktok" / "observations" / "F1.json").read_text(encoding="utf-8"))
    got = [(x["feature"], x["value"], x["source_type"], x["span"]["start_s"]) for x in doc["observations"]]
    assert got == [("steep_or_stairs", "present", "tiktok_segment", 0.0), ("scenic_view", "present", "tiktok_caption", None),
                   ("setting", "outdoor", "tiktok_frame", 4.5)]
    assert doc["observations"][0]["author"] == "tiktok:u1" and doc["observations"][0]["observed_at"] == "2026-01-01"
    assert doc["stats"]["dropped"] == {"frame_not_allowed": 2, "quote_not_in_segment": 2}
    assert calls["observe"] == [(4, "none")]
    assert len(calls["verify"]) == 1 and "ba trăm bậc thang" in calls["verify"][0][1]  # steep is span-checked
    assert asyncio.run(extract.run("dalat"))["status"] == {"cached": 1}


def test_shared_video_sends_no_frames_and_rejected_check_drops(tmp_path, monkeypatch):
    calls = setup(tmp_path, monkeypatch, ANSWER, verdict="insufficient", pairs=(("v1", "F1"), ("v1", "F2")))
    asyncio.run(extract.run("dalat"))
    doc = json.loads((tmp_path / "tiktok" / "observations" / "F1.json").read_text(encoding="utf-8"))
    assert [x["feature"] for x in doc["observations"]] == ["scenic_view"]
    assert (0, "Quán B") in calls["observe"]
