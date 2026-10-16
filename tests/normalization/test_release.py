import json

import pytest

from test_normalize import doc, put


def inputs(root):
    put(root, "gmaps/list/dalat.json", {"items": [{"fid": "F"}]})
    d = doc(place={"name": "F", "category": "Quán cà phê", "lat": 11.94, "lng": 108.44})
    put(root, "gmaps/observations/F.json", d)
    put(root, "gmaps/places/F/place.json", {"fid": "F", "attributes": ["Outdoor seating"]})


def test_staging_snapshot_does_not_publish_or_prune(tmp_path):
    from corpus.snapshot import Snapshot, compile_snapshot
    inputs(tmp_path)
    from corpus.aggregate import run as aggregate
    from corpus.serving import run as serving
    aggregate("dalat", root=tmp_path)
    serving("dalat", root=tmp_path, publish=False)
    put(tmp_path, "snapshot/old/manifest.json", {})
    (tmp_path / "snapshot/current").write_text("old")
    result = compile_snapshot("dalat", tmp_path, publish=False)
    assert (tmp_path / "snapshot/current").read_text() == "old"
    assert (tmp_path / "snapshot/old").exists()
    assert Snapshot(tmp_path / "snapshot", result["version"]).region("dalat").ids == ["F"]


def test_rebuild_is_immutable_and_default_readers_share_release(tmp_path, monkeypatch):
    from corpus.releases import rebuild, publish, resolve
    from corpus.snapshot import Snapshot
    from corpus.index import Index
    inputs(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    put(tmp_path, "intel/places/KEEP.json", {"original": True})
    result = rebuild("dalat", tmp_path)
    assert not (tmp_path / "releases/current").exists()
    assert (tmp_path / "intel/places/KEEP.json").exists()
    release = tmp_path / "releases" / result["release_id"]
    assert json.loads((release / "serving/places.json").read_text())["records"][0]["id"] == "F"
    publish(result["release_id"], tmp_path)
    assert resolve(tmp_path) == release
    assert Snapshot.open().region("dalat").ids == ["F"]
    assert set(Index.load().places) == {"F"}
    old = (release / "intel/places/F.json").read_bytes()
    put(tmp_path, "gmaps/observations/F.json", doc(place_name="New"))
    other = rebuild("dalat", tmp_path)
    assert other["release_id"] != result["release_id"]
    assert resolve(tmp_path) == release
    assert (release / "intel/places/F.json").read_bytes() == old
    publish(other["release_id"], tmp_path)
    publish(result["release_id"], tmp_path)
    assert resolve(tmp_path) == release


def test_failed_build_or_corrupt_artifact_keeps_pointer(tmp_path, monkeypatch):
    from corpus.releases import rebuild, publish
    inputs(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    result = rebuild("dalat", tmp_path, publish=True)
    pointer = (tmp_path / "releases/current").read_bytes()
    import corpus.serving
    monkeypatch.setattr(corpus.serving, "run", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("build failed")))
    with pytest.raises(RuntimeError, match="build failed"):
        rebuild("dalat", tmp_path, publish=True)
    assert (tmp_path / "releases/current").read_bytes() == pointer
    release = tmp_path / "releases" / result["release_id"]
    (release / "serving/places.json").write_text("{}")
    with pytest.raises(ValueError, match="hash"):
        publish(result["release_id"], tmp_path)
    assert (tmp_path / "releases/current").read_bytes() == pointer


def test_release_does_not_read_labels_from_another_root(tmp_path, monkeypatch):
    from corpus.releases import rebuild
    from corpus.snapshot import Snapshot
    source = tmp_path / "source"
    inputs(source)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "wrong"))
    result = rebuild("dalat", source)
    release = source / "releases" / result["release_id"]
    assert Snapshot.open(release / "snapshot").region("dalat").ids == ["F"]
