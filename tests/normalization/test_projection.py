import json
from pathlib import Path
import runpy

from test_release import inputs
from test_normalize import put


def test_projection_only_contains_served_places_and_gated_features(tmp_path):
    from corpus.releases import rebuild
    inputs(tmp_path)
    put(tmp_path, "gmaps/places/RAW/place.json", {"fid": "RAW", "name": "Raw", "lat": 11.94, "lng": 108.44})
    result = rebuild("dalat", tmp_path)
    release = tmp_path / "releases" / result["release_id"]
    projection = json.loads((release / "projection/serving.json").read_text())
    assert [p["id"] for p in projection["places"]] == result["eligible_ids"] == ["F"]
    assert projection["corpusReleaseId"] == result["release_id"]
    assert projection["places"][0]["features"][0]["status"] == "VERIFIED"
    assert projection["review"] == []


def test_pack_excludes_private_data_staging_and_inactive_releases(tmp_path):
    script = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/pack_data.py"))
    for name in ("data/normalization/a/gmaps/file.json", "data/releases/.staging-a/file.json",
                 "data/gmaps/observations_under30_backup/F.json", "data/accounts/avatars/u.png",
                 "data/trip/sessions/x.json", "data/live/gmaps/foo.json", "data/planning/sessions/x.json"):
        assert not script["keep"](Path(name), True), name
    assert script["keep"](Path("data/gmaps/places/F/photos/p.jpg"), True)
    assert not script["keep"](Path("data/gmaps/places/F/photos/p.jpg"), False)
