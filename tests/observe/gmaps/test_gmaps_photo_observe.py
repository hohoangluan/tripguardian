import asyncio
import json

from corpus.observe.gmaps import photos


class Stub:
    def __init__(self, fn):
        self.fn, self.prompt_hash, self.parallel = fn, "h", 4

    async def ask(self, client, model, images=(), **fields):
        return self.fn(images, fields)


def test_photo_gate_keeps_visible_values_and_checks_span_features(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    d = tmp_path / "gmaps" / "places" / "F1"
    (d / "photos").mkdir(parents=True)
    (d / "place.json").write_text(json.dumps({"fid": "F1", "name": "Đồi A", "category": "Đồi"}), encoding="utf-8")
    shots = [{"photo_id": f"P{i}", "file": f"photos/p{i}.jpg", "kind": "photo", "author_hash": "a" if i < 2 else "b",
              "owner": i == 4, "month": "2026-05"} for i in range(1, 6)]
    for s in shots:
        (d / s["file"]).write_bytes(b"jpg")
    (d / "photos.json").write_text(json.dumps({"fetched_at": "2026-10-02T00:00:00", "photos": shots}), encoding="utf-8")
    seen = []

    def observe(images, fields):
        seen.append((len(images), fields["photo_list"]))
        return {"observations": [
            {"feature": "steep_or_stairs", "value": "present", "photo": 1, "quote": "long stairs"},
            {"feature": "steep_or_stairs", "value": "absent", "photo": 2, "quote": "flat"},  # absence: not allowed
            {"feature": "kids", "value": "suitable", "photo": 2, "quote": "kids"},  # suitability: not allowed
            {"feature": "setting", "value": "outdoor", "photo": 9, "quote": "x"},  # no photo 9
            {"feature": "crowd", "value": "high", "photo": 2, "quote": "packed deck"},
            {"feature": "setting", "value": "indoor", "photo": 3, "quote": "room"},  # two values on one photo: unsure
            {"feature": "setting", "value": "outdoor", "photo": 3, "quote": "street"},
        ]} if len(images) == 4 else {"observations": [{"feature": "nature", "value": "present", "photo": 1, "quote": "pines"}]}

    monkeypatch.setattr(photos, "PHOTO_OBSERVE", Stub(observe))
    monkeypatch.setattr(photos, "PHOTO_VERIFY", Stub(lambda images, f: {"verdict": "supports", "reason": "r"}))
    monkeypatch.setattr(photos, "load_config", lambda city: ("Đà Lạt", {}))
    monkeypatch.setattr(photos, "_client", lambda: (None, "m"))
    assert asyncio.run(photos.run("dalat"))["status"] == {"done": 1}
    doc = json.loads((tmp_path / "gmaps" / "photo_observations" / "F1.json").read_text(encoding="utf-8"))
    got = [(o["feature"], o["value"], o["source_id"], o["author"], o["observed_at"]) for o in doc["observations"]]
    assert got == [("steep_or_stairs", "present", "P1", "a", "2026-05-01"), ("crowd", "high", "P2", "b", "2026-05-01"),
                   ("nature", "present", "P5", "b", "2026-05-01")]
    assert doc["stats"]["dropped"] == {"not_allowed": 2, "bad_photo": 1, "mixed_values": 2}
    assert [n for n, _ in seen] == [4, 1] and "4 = owner photo" in seen[0][1]
    assert asyncio.run(photos.run("dalat"))["status"] == {"cached": 1}
