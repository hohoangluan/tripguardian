import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "decision"))
from fixtures import feat, srec  # noqa: E402

from corpus.snapshot import Region  # noqa: E402
from trip import Catalog  # noqa: E402


def intel_of(r, n=3):
    return {"place_fid": r["id"], "place_name": r["identity"]["name"], "identity": {"category": "Quán cà phê"},
            "estimates": {"category_group": "cafe", "usable_as_default": ["experience"]},
            "operation": {"hours": None},
            "features": {"scenic_view": {"n": n, "status": "signal", "top_value": "present",
                                         "by_context": {"time_of_day": {"morning": 2}}, "distribution": {"present": n}}}}


def test_snapshot_serving_is_source_of_truth():
    rec = srec("A", name="Serving name", features={"scenic_view": feat("absent", n=4, status="OUTDATED",
        by_context={"time_of_day=morning": {"present": 4}})})
    region = Region.from_records([rec], [intel_of(rec), intel_of(srec("outside"))], {"v1": "A", "v2": "outside"})
    catalog = Catalog.from_snapshot(region, 1)
    c = catalog.by_id["A"]
    assert list(catalog.by_id) == ["A"]
    assert c.name == "Serving name"
    assert (c.lat, c.lng) == (11.94, 108.44)
    assert c.hours["mon"] == (("07:00", "22:00"),)
    assert c.value("scenic_view") == "absent"
    assert c.value("scenic_view", (("time_of_day", "morning"),)) == "present"
    assert c.known["scenic_view"].status == "OUTDATED"
    assert c.requirement_record() == region.by_id["A"]
    assert catalog.count("scenic_view=present") == 0
    assert catalog.video_place == {"v1": "A"}


@pytest.mark.parametrize("feature", [feat("present", status="UNCERTAIN"),
    feat("present", dist={"present": 3, "absent": 1}), None])
def test_snapshot_does_not_count_uncertain_conflicting_or_missing(feature):
    rec = srec("A", features={"scenic_view": feature} if feature else {})
    catalog = Catalog.from_snapshot(Region.from_records([rec], [intel_of(rec)], {}), 1)
    assert catalog.count("scenic_view=present") == 0
    assert catalog.by_id["A"].value("scenic_view") is None


def test_trip_engine_reads_the_active_release_snapshot(tmp_path, monkeypatch):
    """Trip opens the same release Decision and Planning resolve, not the legacy data/snapshot beside it."""
    import trip.api.tools as tools

    release = tmp_path / "releases" / "r-test"
    release.mkdir(parents=True)
    import hashlib
    import json
    (release / "artifact").write_bytes(b"test")
    (release / "manifest.json").write_text(json.dumps({"release_id": "r-test", "city": "dalat",
        "artifacts": [{"path": "artifact", "sha256": hashlib.sha256(b"test").hexdigest()}]}), encoding="utf-8")
    (tmp_path / "releases" / "current").write_text("r-test", encoding="utf-8")
    opened = []

    class Stop(Exception):
        pass

    def fake_shared(root, **kwargs):
        opened.append(root)
        raise Stop

    monkeypatch.setattr(tools, "shared", fake_shared)
    try:
        tools.create_engine(tmp_path)
    except Stop:
        pass
    assert opened == [release / "snapshot"]


def test_trip_engine_falls_back_to_the_legacy_snapshot_without_a_release(tmp_path, monkeypatch):
    import trip.api.tools as tools

    opened = []

    class Stop(Exception):
        pass

    def fake_shared(root, **kwargs):
        opened.append(root)
        raise Stop

    monkeypatch.setattr(tools, "shared", fake_shared)
    try:
        tools.create_engine(tmp_path)
    except Stop:
        pass
    assert opened == [tmp_path / "snapshot"]


def test_served_evidence_adapter_works_without_intel_and_preserves_unknown_hours():
    rec = srec("A", features={"scenic_view": feat("present", by_context={
        "time_of_day=night": {"present": 2, "absent": 2}})}, hours_status="UNCERTAIN")
    catalog = Catalog.from_records([], 1, evidence={"A": rec})
    assert catalog.by_id["A"].hours is None
    assert catalog.by_id["A"].value("scenic_view", (("time_of_day", "night"),)) is None
    assert catalog.by_id["A"].requirement_record()["operation"]["hours"]["status"] == "UNCERTAIN"
