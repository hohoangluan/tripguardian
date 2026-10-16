import json

import pytest

from fixtures import feat, srec
from gen import records

from corpus.serving.groups import signature
from corpus.snapshot import Region, Snapshot, compile_snapshot


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    recs = records(3)
    (tmp_path / "serving").mkdir()
    (tmp_path / "serving" / "places.json").write_text(
        json.dumps({"built_at": "x", "summary": {}, "records": recs}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "intel" / "places").mkdir(parents=True)
    for r in recs:
        (tmp_path / "intel" / "places" / f"{r['id']}.json").write_text(json.dumps(
            {"place_fid": r["id"], "place_name": r["identity"]["name"], "identity": {"category": "Quán cà phê"},
             "estimates": {}, "operation": {}, "features": {}}), encoding="utf-8")
    return tmp_path, recs


def test_compile_then_open_reads_the_same_records(data_dir):
    root, recs = data_dir
    summary = compile_snapshot("dalat")
    assert summary["regions"]["dalat"]["places"] == len(recs)
    reg = Snapshot.open().region("dalat")
    assert reg.ids == [r["id"] for r in recs]
    assert reg.record(recs[0]["id"]) == json.loads(json.dumps(recs[0]))
    assert reg.record("nope") is None and "nope" not in reg.by_id
    assert len(reg.records()) == len(recs) and len(reg.intel()) == len(recs)


def test_current_switches_atomically_and_old_versions_are_pruned(data_dir):
    root, _ = data_dir
    for _ in range(4):
        compile_snapshot("dalat")
    versions = [p for p in (root / "snapshot").iterdir() if p.is_dir()]
    assert len(versions) == 3  # snapshot_keep_versions in config/serving.yaml
    assert (root / "snapshot" / "current").read_text().strip() == Snapshot.open().version


def test_open_without_snapshot_explains(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="python -m corpus snapshot"):
        Snapshot.open()
    (tmp_path / "snapshot").mkdir()
    (tmp_path / "snapshot" / "current").write_text("20000101T000000")
    with pytest.raises(FileNotFoundError, match="python -m corpus snapshot"):
        Snapshot.open()


def test_feature_column_is_aligned_with_places():
    a = srec("A", features={"scenic_view": feat("present", dist={"present": 2, "absent": 1}, status="UNCERTAIN")})
    b = srec("B")
    reg = Region.from_records([a, b])
    col = reg.feature("scenic_view")
    assert list(col.exists) == [True, False] and list(col.uncertain) == [True, False]
    assert list(col.eq("present")) == [True, False] and list(col.has("absent")) == [True, False]
    assert list(col.only("present")) == [False, False]
    assert reg.sigs["A"] == signature(a) == frozenset({("scenic_view", "present")}) and reg.sigs["B"] == frozenset()
    assert reg.stay == frozenset()
    assert reg.column("id") == ["A", "B"]
    assert reg.light[0] == {"id": "A", "identity": {"category_group": "cafe"},
                            "usable_as": ["experience", "meal", "backup"], "near_duplicate_group": None}


def test_compile_keeps_only_served_and_keeps_stays(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    ok, stay = srec("OK"), srec("H", group="stay", usable=())
    hidden = [{**srec("NR"), "status": "NEEDS_REVIEW"}, {**srec("DIS"), "status": "DISABLED"}]
    (tmp_path / "serving").mkdir()
    (tmp_path / "serving" / "places.json").write_text(
        json.dumps({"built_at": "x", "summary": {}, "records": [ok, stay, *hidden]}), encoding="utf-8")
    (tmp_path / "intel" / "places").mkdir(parents=True)
    compile_snapshot("dalat")
    reg = Snapshot.open().region("dalat")
    assert reg.ids == ["OK", "H"]
    assert reg.stay == frozenset({"H"}) and reg.record("H")["identity"]["category_group"] == "stay"


def test_serving_load_reads_the_snapshot(data_dir):
    from corpus.serving import load
    _, recs = data_dir
    compile_snapshot("dalat")
    assert [r["id"] for r in load()] == [r["id"] for r in recs if r["status"] in ("VERIFIED", "UNCERTAIN", "OUTDATED")]
