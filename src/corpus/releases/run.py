"""Compile saved corpus inputs in isolation; switch one pointer after artifact validation."""

import hashlib
import json
import os
import uuid
from pathlib import Path

from ..crawl.common.files import ROOT, data_dir, now, write_json


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path(base: Path, key: str) -> Path:
    if not key or Path(key).name != key or key in (".", ".."):
        raise ValueError("invalid release ID")
    path = base / key
    if not path.resolve().is_relative_to(base.resolve()):
        raise ValueError("release path escapes root")
    return path


def resolve(root: Path | None = None) -> Path:
    """Resolve the active release; a root without a release retains the standalone APIs."""
    root = root or data_dir()
    pointer = root / "releases" / "current"
    if not pointer.exists():
        return root
    release = _path(root / "releases", pointer.read_text(encoding="utf-8").strip())
    if not (release / "manifest.json").is_file():
        raise FileNotFoundError(f"missing release manifest: {release}")
    return release


def validate(release: Path) -> dict:
    """Verify every referenced artifact and the eligible set before activation."""
    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest["artifacts"]:
        path = release / item["path"]
        if not path.resolve().is_relative_to(release.resolve()) or not path.is_file() or _hash(path) != item["sha256"]:
            raise ValueError(f"release artifact hash mismatch: {item['path']}")
    from ..snapshot import Snapshot
    from ..index import Index
    snap = Snapshot.open(release / "snapshot")
    regions = json.loads((snap.root / snap.version / "manifest.json").read_text(encoding="utf-8"))["regions"]
    ids = {pid for key in regions for pid in snap.region(key).ids}
    if ids != set(manifest["eligible_ids"]):
        raise ValueError("snapshot eligibility mismatch")
    index = Index.load(data=release)
    if set(index.places) != ids:
        raise ValueError("index eligibility mismatch")
    return manifest


def publish(release_id: str, root: Path | None = None) -> dict:
    """Activate a validated immutable release, including rollback to an earlier release."""
    root = root or data_dir()
    release = _path(root / "releases", release_id)
    manifest = validate(release)
    pointer = root / "releases" / "current"
    tmp = pointer.with_name("current." + uuid.uuid4().hex + ".tmp")
    tmp.write_text(release_id, encoding="utf-8")
    os.replace(tmp, pointer)
    return manifest


def _dependencies(root: Path, normalization: dict) -> list[dict]:
    paths = {i["path"] for i in normalization["inputs"]}
    paths.update(i["path"] for i in normalization.get("source_refs", []) if i["sha256"] is not None)
    paths.update(i["path"] for i in normalization["dependencies"] if not i["path"].startswith("config/"))
    paths.update(p.relative_to(root).as_posix() for p in (root / "review").glob("*.jsonl"))
    paths.update(p.relative_to(root).as_posix() for p in (root / "gmaps" / "places").glob("*/menu.json"))
    paths.update(p.relative_to(root).as_posix() for p in (root / "tiktok" / "place_filter").glob("*.json"))
    paths.update(p.relative_to(root).as_posix() for p in (root / "tiktok" / "clips").glob("*.json"))
    paths.update(p.relative_to(root).as_posix() for p in (root / "gmaps" / "places").glob("*/place.json"))
    saved = {i["path"]: i["sha256"] for i in normalization["inputs"] + normalization.get("source_refs", [])
             + normalization["dependencies"] if not i["path"].startswith("config/") and i.get("sha256")}
    rows = [{"path": p, "sha256": saved.get(p) or _hash(root / p)} for p in sorted(paths)]
    for item in rows:
        if _hash(root / item["path"]) != item["sha256"]:
            raise ValueError(f"source changed after normalization: {item['path']}")
    return rows


def rebuild(city: str, root: Path | None = None, *, publish: bool = False, normalization=None) -> dict:
    """Rebuild only with saved inputs. Never invoke crawling, models, embeddings or pruning."""
    from ..aggregate import run as aggregate
    from ..normalize import normalize
    from ..serving import SERVED, run as serving
    from ..index import compile_index
    root = root or data_dir()
    previous = resolve(root)
    old_path = previous / "serving" / "places.json"
    old = json.loads(old_path.read_text(encoding="utf-8"))["records"] if old_path.exists() else []
    normalized = normalization or normalize(city, root)
    if normalized.manifest["city"] != city.removesuffix("_stay"):
        raise ValueError("normalization city mismatch")
    inputs = _dependencies(root, normalized.manifest)
    fingerprint_paths = sorted((ROOT / "config").glob("*.yaml")) + sorted((ROOT / "src" / "corpus").rglob("*.py"))
    fingerprint = [{"path": p.relative_to(ROOT).as_posix(), "sha256": _hash(p)} for p in fingerprint_paths]
    release_id = "r-" + normalized.id + "-" + uuid.uuid4().hex[:8]
    stage = root / "releases" / (".staging-" + release_id)
    stage.mkdir(parents=True)
    aggregated = aggregate(city, root=root, output_root=stage, normalization=normalized)
    if aggregated["normalization_id"] != normalized.id:
        raise ValueError("normalization changed during release build")
    serving_summary = serving(city, root=stage, source_root=root, publish=False)
    # Internal pointers belong to this release only; the serving pointer is untouched.
    snapshots = list((stage / "snapshot").glob("*/manifest.json"))
    snapshot = json.loads(snapshots[0].read_text(encoding="utf-8"))
    (stage / "snapshot" / "current").write_text(snapshot["version"], encoding="utf-8")
    recs = json.loads((stage / "serving" / "places.json").read_text(encoding="utf-8"))["records"]
    eligible = {r["id"] for r in recs if r["status"] in SERVED}
    index = compile_index(city, source_root=root, output_root=stage, publish=False, eligible_ids=eligible,
                          normalization_root=normalized.root)
    inputs.extend(i for i in index.get("inputs", []) if i["path"] not in {item["path"] for item in inputs})
    (stage / "index" / "current").write_text(index["version"], encoding="utf-8")
    write_json(stage / "normalization.json", normalized.manifest)
    from .projection import projection
    write_json(stage / "projection" / "serving.json", projection(release_id, city.removesuffix("_stay"), recs,
                                                               stage, root, normalized))
    old_ids = {r["id"] for r in old if r["status"] in SERVED}
    old_by_id = {r["id"]: r for r in old}
    groups = ("experience", "environment", "service", "effort", "suitability", "operation", "details", "identity")
    changes = [{"id": r["id"], "fields": [key for key in groups if r.get(key) != old_by_id[r["id"]].get(key)]}
               for r in recs if r["id"] in old_by_id]
    disabled = {r["id"]: r["reason"] for r in serving_summary.get("excluded", [])}
    quality = {"normalization": normalized.manifest["summary"], "semantic": index,
               "baseline": {"places": len(old_ids), "release": previous.name if previous != root else "legacy"},
               "served": len(eligible), "added": sorted(eligible - old_ids),
               "excluded": [{"id": pid, "reason": disabled.get(pid) or "no_eligible_normalized_document"}
                            for pid in sorted(old_ids - eligible)],
               "changed": [r for r in changes if r["fields"]], "source_hashes_unchanged": True,
               "network_calls": 0, "model_calls": 0}
    write_json(stage / "quality.json", quality)
    for item in inputs:
        if _hash(root / item["path"]) != item["sha256"]:
            raise ValueError(f"source changed during release build: {item['path']}")
    artifacts = [{"path": p.relative_to(stage).as_posix(), "sha256": _hash(p)}
                 for p in sorted(stage.rglob("*")) if p.is_file()]
    manifest = {"release_id": release_id, "built_at": now(), "city": city.removesuffix("_stay"),
                "schema_version": 1, "normalizer_version": normalized.manifest["normalizer_version"],
                "ontology_version": normalized.manifest["ontology_version"], "aggregate_rule_version": 1,
                "normalization_id": normalized.id, "eligible_ids": sorted(eligible),
                "redirects": normalized.manifest["redirects"], "inputs": inputs,
                "fingerprint": fingerprint, "artifacts": artifacts, "quality": quality}
    write_json(stage / "manifest.json", manifest)
    validate(stage)
    target = root / "releases" / release_id
    stage.rename(target)
    if publish:
        globals()["publish"](release_id, root)
    return manifest
