"""python -m corpus index: the per-source vectors and style observations -> data/index/<version>/, then
data/index/current names that version (written atomically). Offline only; the online Index reads it.

  photos (LanceDB table)  one row per Maps photo / TikTok frame: vector, place_id, file, source, author, owner, month
  spans  (LanceDB table)  one row per distinct observation quote: vector, place_id, observation ids, features, quote
  places.json             id -> name, category_group, styles {tag: {authors, evidence: [{file, quote}]}}
  styles.json             the style vocabulary (config/styles.yaml) the tags were read with"""

from __future__ import annotations

import collections
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from ..crawl.common.files import data_dir, safe_name
from ..observe.gmaps.styles import vocabulary
from .vectors import OUT, serving_ids

EVIDENCE = 3  # style evidence kept per tag


def _load_pairs(data: Path, kind: str, ids: list[str]):
    """-> (vectors float16 (n, d), rows) over every place's file of one kind."""
    vecs, rows = [], []
    for pid in ids:
        base = data.joinpath(*OUT[kind]) / safe_name(pid)
        npy, meta = base.with_suffix(".npy"), base.with_suffix(".json")
        if not (npy.exists() and meta.exists()):
            continue
        items = json.loads(meta.read_text(encoding="utf-8"))["items"]
        v = np.load(npy)
        if len(v) != len(items):
            continue
        vecs.append(v)
        rows += [{"place_id": pid, **it} for it in items]
    return (np.concatenate(vecs) if vecs else np.zeros((0, 0), np.float16)), rows


def place_styles(data: Path, pid: str, voc: dict) -> dict:
    """A tag holds from min_authors distinct posters; a child tag's evidence also counts for its parent."""
    doc = data / "gmaps" / "style_observations" / f"{safe_name(pid)}.json"
    if not doc.exists():
        return {}
    parent = {s["id"]: s.get("parent") for s in voc["styles"]}
    authors, evidence = collections.defaultdict(set), collections.defaultdict(list)
    for o in json.loads(doc.read_text(encoding="utf-8"))["observations"]:
        for tag in filter(None, (o["feature"], parent.get(o["feature"]))):
            authors[tag].add(o["author"] or o["source_id"])
            if len(evidence[tag]) < EVIDENCE:
                evidence[tag].append({"file": o["span"]["field"], "quote": o["span"]["quote"], "observation_id": o["id"]})
    return {t: {"authors": len(a), "evidence": evidence[t]} for t, a in authors.items() if len(a) >= voc["min_authors"]}


def _table(db, name: str, vecs: np.ndarray, rows: list[dict], cols: list[str]) -> int:
    import pyarrow as pa
    if not rows:
        return 0
    d = vecs.shape[1]
    vec = pa.FixedSizeListArray.from_arrays(pa.array(vecs.astype(np.float32).reshape(-1)), d)
    data = {"vector": vec}
    for c in cols:
        vals = [r.get(c) for r in rows]
        data[c] = pa.array([json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for v in vals])
    db.create_table(name, pa.table(data), mode="overwrite")
    return len(rows)


def run(city: str = "dalat") -> dict:
    import lancedb
    data = data_dir()
    recs = {r["id"]: r for r in json.loads((data / "serving" / "places.json").read_text(encoding="utf-8"))["records"]}
    ids = serving_ids(data)
    voc = vocabulary()
    version = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    out = data / "index" / version
    out.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(out))

    pv, prow = _load_pairs(data, "photos", ids)
    fv, frow = _load_pairs(data, "frames", ids)
    photo_vecs = np.concatenate([x for x in (pv, fv) if x.size]) if (pv.size or fv.size) else pv
    photo_rows = [{**r, "author": r.get("author_hash") or r.get("photo_id")} for r in prow + frow]
    n_photos = _table(db, "photos", photo_vecs, photo_rows, ["place_id", "file", "source", "author", "owner", "month"])
    sv, srow = _load_pairs(data, "spans", ids)
    n_spans = _table(db, "spans", sv, srow, ["place_id", "observation_id", "observations", "features", "quote", "source"])

    places = {}
    for pid in ids:
        r = recs[pid]
        places[pid] = {"name": r["identity"]["name"], "category_group": r["identity"].get("category_group"),
                       "styles": place_styles(data, pid, voc), "near_duplicate_group": r.get("near_duplicate_group")}
    (out / "places.json").write_text(json.dumps(places, ensure_ascii=False), encoding="utf-8")
    (out / "styles.json").write_text(json.dumps(voc, ensure_ascii=False), encoding="utf-8")
    styled = sum(1 for p in places.values() if p["styles"])
    summary = {"version": version, "photos": n_photos, "spans": n_spans, "places": len(places), "styled": styled,
               "built_at": datetime.now(UTC).isoformat(timespec="seconds")}
    (out / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    tmp = data / "index" / "current.tmp"
    tmp.write_text(version, encoding="utf-8")
    os.replace(tmp, data / "index" / "current")
    print(f"corpus index {city}: {json.dumps(summary)}")
    return summary
