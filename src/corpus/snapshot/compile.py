"""data/serving/places.json (+ intel, TikTok place_filter) -> data/snapshot/<version>/<region>/ LanceDB tables, then
data/snapshot/current names that version (written atomically, like data/index/current). Offline only."""

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import yaml

from ..crawl.common.files import ROOT, data_dir, now
from ..ontology import load as load_ontology
from ..serving.record import SERVED, config
from .tables import tables


def _region_of(rec: dict, cities: dict, city: str) -> str:
    lat, lng = rec["identity"].get("lat"), rec["identity"].get("lng")
    if lat is not None and lng is not None:
        for key, c in cities.items():
            a = c.get("area")
            if a and a[0] <= float(lat) <= a[2] and a[1] <= float(lng) <= a[3]:
                return key
    return city


def _intel_subset(intel: dict) -> dict:
    """What trip.Catalog reads from an intel record, without evidence ids or quotes."""
    keep = ("n", "status", "needs_review", "top_value", "by_context", "distribution")
    return {"place_fid": intel["place_fid"], "place_name": intel["place_name"], "identity": intel.get("identity") or {},
            "estimates": intel.get("estimates") or {}, "operation": {"hours": (intel.get("operation") or {}).get("hours")},
            "features": {fid: {k: s[k] for k in keep if k in s} for fid, s in (intel.get("features") or {}).items()}}


def _videos(root: Path) -> dict[str, str]:
    """TikTok video id -> place id, relevance yes (the same rule trip.Catalog.load used)."""
    out = {}
    for p in sorted((root / "tiktok" / "place_filter").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        vids = d.get("videos")
        for v in vids if isinstance(vids, list) else []:  # some files store a count
            if (v.get("llm") or {}).get("relevance") == "yes":
                out[str(v["video_id"])] = d["fid"]
    return out


def compile_snapshot(city: str, root: Path | None = None, *, source_root: Path | None = None,
                     publish: bool = True) -> dict:
    import lancedb  # imported here: it takes seconds, and importing corpus.snapshot should not pay for it
    root = root or data_dir()
    doc = json.loads((root / "serving" / "places.json").read_text(encoding="utf-8"))
    recs = [r for r in doc["records"] if r["status"] in SERVED]  # never NEEDS_REVIEW / DISABLED, stays included
    served = {r["id"] for r in recs}
    intel = {}
    for p in sorted((root / "intel" / "places").glob("*.json")):
        i = json.loads(p.read_text(encoding="utf-8"))
        if i["place_fid"] in served:
            intel[i["place_fid"]] = _intel_subset(i)
    videos = _videos(source_root or root)
    cities = yaml.safe_load((ROOT / "config" / "cities.yaml").read_text(encoding="utf-8"))
    by_region: dict[str, list[dict]] = {}
    for r in recs:
        by_region.setdefault(_region_of(r, cities, city), []).append(r)
    base = root / "snapshot"
    version = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    while (base / version).exists():
        version += "x"
    out = base / version
    out.mkdir(parents=True)
    regions = {}
    for key, rs in sorted(by_region.items()):
        ids = {r["id"] for r in rs}
        t = tables(rs, [intel[i] for i in sorted(ids) if i in intel],
                   {v: p for v, p in videos.items() if p in ids})
        db = lancedb.connect(str(out / key))
        for name, table in t.items():
            db.create_table(name, table, mode="overwrite")
        regions[key] = {"places": len(rs)}
    manifest = {"version": version, "built_at": now(), "serving_built_at": doc.get("built_at"),
                "ontology_version": load_ontology().version, "regions": regions}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    if publish:
        tmp = base / "current.tmp"
        tmp.write_text(version, encoding="utf-8")
        os.replace(tmp, base / "current")
        keep = config()["snapshot_keep_versions"]
        olds = sorted(p for p in base.iterdir() if p.is_dir())[:-keep]
        for p in olds:
            if p.name != version:
                shutil.rmtree(p)
    print(f"snapshot {version}: {json.dumps(regions, ensure_ascii=False)}")
    return manifest
