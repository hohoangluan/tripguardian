"""Photos older than MAX_AGE_YEARS: kept as `stale` only when a place has nothing newer, and never read as evidence."""

import json

from corpus.crawl.gmaps.photos import needs_fetch
from corpus.index.vectors import photo_inputs


def _write(path, doc):
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_empty_save_with_old_photos_is_fetched_once_more(tmp_path):
    f = tmp_path / "photos.json"
    _write(f, {"wanted": 12, "photos": [], "skipped": {"too_old": 7}})
    assert needs_fetch(f, 12, 12)
    _write(f, {"wanted": 12, "photos": [], "skipped": {"too_old": 7}, "stale_fallback": True})
    assert not needs_fetch(f, 12, 12)


def test_empty_save_without_a_reason_is_left_alone(tmp_path):
    f = tmp_path / "photos.json"
    _write(f, {"wanted": 12, "photos": [], "skipped": {}})
    assert not needs_fetch(f, 12, 12)


def test_evidence_readers_skip_stale_photos(tmp_path):
    d = tmp_path / "gmaps" / "places" / "0xa_0xb"
    (d / "photos").mkdir(parents=True)
    for n in ("fresh", "old"):
        (d / "photos" / f"{n}.jpg").write_bytes(b"x")
    _write(d / "photos.json", {"photos": [{"photo_id": "1", "file": "photos/fresh.jpg"},
                                          {"photo_id": "2", "file": "photos/old.jpg", "stale": True}]})
    assert [p["photo_id"] for p in photo_inputs(tmp_path, "0xa:0xb")] == ["1"]
