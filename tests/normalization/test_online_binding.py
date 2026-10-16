import hashlib
import json

import pytest


def release(root, name):
    path = root / "releases" / name
    path.mkdir(parents=True)
    data = b"artifact"
    (path / "serving.json").write_bytes(data)
    manifest = {"release_id": name, "city": "dalat", "eligible_ids": ["A"],
                "artifacts": [{"path": "serving.json", "sha256": hashlib.sha256(data).hexdigest()}]}
    (path / "manifest.json").write_text(json.dumps(manifest))
    return path


def test_binding_resolves_pinned_release_after_pointer_switch(tmp_path):
    from corpus.releases import bind, resolve_binding
    old = release(tmp_path, "r-old")
    release(tmp_path, "r-new")
    pointer = tmp_path / "releases/current"
    pointer.write_text("r-old")
    binding = bind(tmp_path)
    pointer.write_text("r-new")
    assert resolve_binding(tmp_path, binding) == old
    assert binding.release_id == "r-old"


@pytest.mark.parametrize("bad", ["../outside", "..", "/tmp/outside", ".staging-r-incomplete"])
def test_binding_rejects_unsafe_release_ids(bad):
    from corpus.releases import Binding
    with pytest.raises(ValueError):
        Binding(release_id=bad, region="dalat")


def test_pinned_binding_rejects_corrupt_artifact(tmp_path):
    from corpus.releases import bind, resolve_binding
    path = release(tmp_path, "r-old")
    (tmp_path / "releases/current").write_text("r-old")
    binding = bind(tmp_path)
    (path / "serving.json").write_text("corrupt")
    with pytest.raises(ValueError, match="hash"):
        resolve_binding(tmp_path, binding)


def test_legacy_binding_resolves_without_reading_active_pointer(tmp_path):
    from corpus.releases import bind, resolve_binding
    legacy = bind(tmp_path)
    assert legacy.release_id is None
    release(tmp_path, "r-next")
    (tmp_path / "releases/current").write_text("r-next")
    assert resolve_binding(tmp_path, legacy) == tmp_path


def test_legacy_snapshot_uses_its_pinned_version_after_pointer_changes(tmp_path):
    from corpus.releases import bind, resolve_binding
    from corpus.snapshot import shared
    root = tmp_path / "snapshot"
    (root / "old").mkdir(parents=True)
    (root / "new").mkdir()
    (root / "current").write_text("old")
    binding = bind(tmp_path)
    (root / "current").write_text("new")
    assert resolve_binding(tmp_path, binding) == tmp_path
    assert shared(root, version=binding.snapshot_version).version == "old"


def test_missing_legacy_version_fails_instead_of_using_current(tmp_path):
    from corpus.releases import Binding, resolve_binding
    with pytest.raises(FileNotFoundError, match="legacy snapshot old missing"):
        resolve_binding(tmp_path, Binding(region="dalat", snapshot_version="old"))


def test_binding_can_capture_named_release_without_following_active_pointer(tmp_path):
    from corpus.releases import bind, resolve_binding
    old = release(tmp_path, "r-old")
    release(tmp_path, "r-new")
    (tmp_path / "releases/current").write_text("r-new")
    binding = bind(tmp_path, release_id="r-old", region="dalat")
    assert binding.release_id == "r-old"
    assert resolve_binding(tmp_path, binding) == old
    assert (tmp_path / "releases/current").read_text() == "r-new"


def test_binding_cannot_substitute_reader_version_inside_verified_release(tmp_path):
    from corpus.releases import bind, resolve_binding
    path = release(tmp_path, "r-old")
    (path / "snapshot").mkdir()
    (path / "snapshot/current").write_text("correct")
    (tmp_path / "releases/current").write_text("r-old")
    binding = bind(tmp_path)
    with pytest.raises(ValueError, match="snapshot version"):
        resolve_binding(tmp_path, binding.model_copy(update={"snapshot_version": "other"}))
