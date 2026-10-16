"""Public online identity for an immutable release and its region."""

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .run import _hash, _path, resolve


class Binding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    release_id: str | None = Field(default=None, pattern=r"^r-[A-Za-z0-9_-]+$")
    region: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    snapshot_version: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]+$")
    index_version: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]+$")


def _manifest(path: Path, binding: Binding | None = None) -> dict:
    raw = (path / "manifest.json").read_bytes()
    manifest = json.loads(raw)
    if manifest.get("release_id") != path.name:
        raise ValueError("release manifest identity mismatch")
    if binding is not None:
        if binding.region != manifest.get("city"):
            raise ValueError("release region mismatch")
        if binding.manifest_sha256 and hashlib.sha256(raw).hexdigest() != binding.manifest_sha256:
            raise ValueError("release manifest hash mismatch")
    if not manifest.get("artifacts"):
        raise ValueError("release manifest has no artifacts")
    for item in manifest["artifacts"]:
        artifact = path / item["path"]
        if not artifact.resolve().is_relative_to(path.resolve()) or not artifact.is_file() or _hash(artifact) != item["sha256"]:
            raise ValueError(f"release artifact hash mismatch: {item['path']}")
    return manifest


def _version(root: Path, name: str) -> str | None:
    pointer = root / name / "current"
    return pointer.read_text(encoding="utf-8").strip() if pointer.is_file() else None


def bind(root: Path, *, region: str | None = None, legacy: bool = False,
         release_id: str | None = None) -> Binding:
    """Capture one active release; legacy explicitly pins the standalone reader versions."""
    if release_id is not None and legacy:
        raise ValueError("a named release cannot use legacy binding")
    if release_id is not None:
        Binding(release_id=release_id, region=region or "dalat")
    path = _path(root / "releases", release_id) if release_id is not None else root if legacy else resolve(root)
    if path == root:
        if region is None:
            from ..serving.record import config
            region = config()["default_region"]
        return Binding(region=region, snapshot_version=_version(root, "snapshot"), index_version=_version(root, "index"))
    manifest = _manifest(path)
    selected = region or manifest["city"]
    if selected != manifest["city"]:
        raise ValueError("release region mismatch")
    return Binding(release_id=manifest["release_id"], region=selected,
                   manifest_sha256=_hash(path / "manifest.json"), snapshot_version=_version(path, "snapshot"),
                   index_version=_version(path, "index"))


def resolve_binding(root: Path, binding: Binding) -> Path:
    """Open only the pinned release. Never consult the active pointer or migrate selections."""
    if binding.release_id is None:
        for name, version in (("snapshot", binding.snapshot_version), ("index", binding.index_version)):
            if version is not None and not (root / name / version).is_dir():
                raise FileNotFoundError(f"legacy {name} {version} missing; explicit revalidation is required")
        return root
    path = _path(root / "releases", binding.release_id)
    _manifest(path, binding)
    for name, version in (("snapshot", binding.snapshot_version), ("index", binding.index_version)):
        if version != _version(path, name):
            raise ValueError(f"release {name} version mismatch")
    return path
