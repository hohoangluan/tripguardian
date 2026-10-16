"""python -m corpus index: the per-source vectors and style observations -> data/index/<version>/, then
data/index/current names that version (written atomically). Offline only; the online Index reads it.

  photos (LanceDB table)  one row per Maps photo / TikTok frame: vector, place_id, file, source, author, owner, month
  spans  (LanceDB table)  one row per distinct observation quote: vector, place_id, observation ids, features, quote
  places.json             id -> name, category_group, styles {tag: {authors, evidence: [{file, quote}]}}
  styles.json             the style vocabulary (config/styles.yaml) the tags were read with"""

from __future__ import annotations

import collections
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from ..crawl.common.files import data_dir, safe_name
from ..observe.gmaps.styles import vocabulary
from ..review import label_key, label_verdicts
from .vectors import OUT
from .embedder import config

EVIDENCE = 3  # style evidence kept per tag


def _load_pairs(data: Path, kind: str, ids: list[str], *, strict=False, cfg=None, issues=None,
                inputs=None, dimensions=None, gate=None):
    """-> (vectors float16 (n, d), rows) over every place's file of one kind."""
    vecs, rows = [], []
    for pid in ids:
        base = data.joinpath(*OUT[kind]) / safe_name(pid)
        npy, meta = base.with_suffix(".npy"), base.with_suffix(".json")
        if not (npy.exists() and meta.exists()):
            if strict:
                issues.append({"place_id": pid, "kind": kind, "reason": "missing_vectors"})
            continue
        def issue(reason, **extra):
            if issues is not None:
                issues.append({"place_id": pid, "kind": kind, "path": meta.relative_to(data).as_posix(),
                               "reason": reason, **extra})
        try:
            if strict:
                for path in (meta, npy):
                    inputs.append({"path": path.relative_to(data).as_posix(),
                                   "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            metadata = json.loads(meta.read_text(encoding="utf-8"))
            items = metadata["items"]
            v = np.load(npy, allow_pickle=False)
            if not isinstance(items, list) or v.ndim != 2 or len(v) != len(items):
                issue("item_alignment")
                continue
            if strict:
                space = "text" if kind == "spans" else "image"
                model = cfg["embedder"][space + "_model"]
                if metadata.get("model") != model:
                    issue("incompatible_model", model=metadata.get("model"))
                    continue
                expected = cfg["embedder"].get(space + "_dimension") or {
                    "google/siglip2-so400m-patch16-384": 1152, "BAAI/bge-m3": 1024}.get(model)
                expected = expected or dimensions.get(space)
                if (not expected or v.shape[1] != expected or not np.isfinite(v).all()):
                    issue("incompatible_dimension", dimension=v.shape[1])
                    continue
                if metadata.get("place_id") != pid or not all(isinstance(i, dict) for i in items):
                    issue("item_alignment")
                    continue
                dimensions[space] = v.shape[1]
            keep, kept = [], []
            for i, item in enumerate(items):
                if strict and kind != "spans":
                    media = data / item.get("file", "")
                    if not media.resolve().is_relative_to(data.resolve()) or not media.is_file():
                        issue("missing_media", file=item.get("file"))
                        continue
                if strict and kind == "spans":
                    result = gate(pid, item)
                    if result is None:
                        issue("stale_evidence")
                        continue
                    item, served = result
                    item["served"] = served
                    if not served:
                        issue("not_backing_served_feature")
                else:
                    item = {**item, "served": True} if kind == "spans" else item
                keep.append(i)
                kept.append({**item, "place_id": pid})
            if keep:
                vecs.append(v[keep])
                rows += kept
        except (ValueError, OSError, KeyError, TypeError):
            issue("invalid_vector_payload")
    return (np.concatenate(vecs) if vecs else np.zeros((0, 0), np.float16)), rows


def place_styles(data: Path, pid: str, voc: dict, *, strict=False, issues=None, verdicts=None) -> dict:
    """A tag holds from min_authors distinct posters; a child tag's evidence also counts for its parent."""
    doc = data / "gmaps" / "style_observations" / f"{safe_name(pid)}.json"
    if not doc.exists():
        return {}
    parent = {s["id"]: s.get("parent") for s in voc["styles"]}
    authors, evidence = collections.defaultdict(set), collections.defaultdict(list)
    try:
        observations = json.loads(doc.read_text(encoding="utf-8"))["observations"]
        if not isinstance(observations, list):
            raise ValueError("style observations must be a list")
    except (OSError, ValueError, KeyError, TypeError):
        if not strict:
            raise
        issues.append({"place_id": pid, "kind": "styles", "reason": "invalid_style_payload"})
        return {}
    for o in observations:
        if strict:
            if (not isinstance(o, dict) or not all(isinstance(o.get(k), str) for k in ("id", "source_id", "feature"))
                    or not isinstance(o.get("span"), dict)
                    or not all(isinstance(o["span"].get(k), str) for k in ("field", "quote"))
                    or not isinstance(o.get("author"), (str, type(None)))):
                issues.append({"place_id": pid, "kind": "styles", "reason": "invalid_style_payload"})
                continue
            key = label_key(o["source_id"], o["feature"], o.get("value", "present"), o["span"]["quote"])
            if (verdicts or {}).get(key) in ("wrong", "unsure_again"):
                issues.append({"place_id": pid, "kind": "styles", "reason": "invalidated_style_evidence", "id": o["id"]})
                continue
            raw_file = o["span"]["field"]
            media = data / raw_file if raw_file.startswith("gmaps/") else data / "gmaps" / "places" / safe_name(pid) / raw_file
            if not media.resolve().is_relative_to(data.resolve()) or not media.is_file() or o["feature"] not in parent:
                issues.append({"place_id": pid, "kind": "styles", "reason": "missing_style_evidence", "file": raw_file})
                continue
        for tag in filter(None, (o["feature"], parent.get(o["feature"]))):
            authors[tag].add(o["author"] or o["source_id"])
            if len(evidence[tag]) < EVIDENCE:
                evidence[tag].append({"file": media.relative_to(data).as_posix() if strict else o["span"]["field"],
                                      "quote": o["span"]["quote"], "observation_id": o["id"]})
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


def _evidence_ids(value):
    if isinstance(value, dict):
        found = {i for i in value.get("evidence", []) if isinstance(i, str)} if isinstance(value.get("evidence"), list) else set()
        for v in value.values():
            found.update(_evidence_ids(v))
        return {i for i in found if isinstance(i, str)}
    if isinstance(value, list):
        return set().union(*(_evidence_ids(v) for v in value))
    return set()


def _served_feature(record, feature):
    for group in record.values():
        if isinstance(group, dict) and isinstance(group.get(feature), dict):
            return group[feature]
    return None


def _span_gate(source, output, recs, normalization_root=None, *, verdicts=None):
    verdicts = label_verdicts(root=source) if verdicts is None else verdicts
    paths, normalized = collections.defaultdict(list), False
    summary = output / "intel" / "summary.json"
    if summary.exists():
        normalization_id = json.loads(summary.read_text()).get("normalization_id")
        manifest = ((Path(normalization_root) if normalization_root is not None else
                     source / "normalization" / str(normalization_id)) / "manifest.json")
        if normalization_id:
            if not manifest.is_file():
                raise FileNotFoundError(f"normalization manifest missing: {manifest}")
            normalized = True
            manifest_data = json.loads(manifest.read_text())
            if manifest_data.get("id", normalization_id) != normalization_id:
                raise ValueError("normalization manifest ID mismatch")
            for entry in manifest_data["inputs"]:
                if not entry.get("normalized"):
                    continue
                pid = entry.get("canonical_id", entry.get("place_id"))
                paths[pid].append((manifest.parent / entry["normalized"], entry["normalized_sha256"]))
    last_pid, feature_ids, detail_ids, claims = None, {}, set(), {}

    def gate(pid, item):
        """Keep normalized claims, marking only current feature backing as served.

        Missing normalization permits only current served evidence. Invalid
        source, quote, observation ID, feature or value drops that claim.
        """
        nonlocal last_pid, feature_ids, detail_ids, claims
        if pid != last_pid:
            last_pid = pid
            feature_ids, detail_ids, claims = {}, _evidence_ids(recs[pid].get("details", {})), {}
            intel_path = output / "intel" / "places" / f"{safe_name(pid)}.json"
            intel = json.loads(intel_path.read_text()) if intel_path.exists() else {}
            for fid, signal in intel.get("features", {}).items():
                served = _served_feature(recs[pid], fid)
                if signal.get("servable") and not signal.get("needs_review") and served and served.get("status") in ("VERIFIED", "UNCERTAIN", "OUTDATED"):
                    for oid in signal.get("observation_ids", []):
                        feature_ids.setdefault(oid, set()).add(fid)
            for path, sha in paths.get(pid, []):
                payload = path.read_bytes()
                if hashlib.sha256(payload).hexdigest() != sha:
                    raise ValueError("normalized observation artifact changed")
                doc = json.loads(payload)
                for claim in (doc.get("observations") or []) + (doc.get("details") or []):
                    claims.setdefault(claim["id"], []).append(claim)
        ids = item.get("observations") or [item.get("observation_id")]
        values = item.get("features") or []
        if len(ids) != len(values) or not isinstance(item.get("quote"), str):
            return None
        kept = []
        served_claims = []
        matched_claims = {}
        for oid, value in zip(ids, values):
            if not isinstance(value, str) or "=" not in value:
                continue
            feature, _, claim_value = value.partition("=")
            current = _served_feature(recs[pid], feature)
            backed = (feature in feature_ids.get(oid, set()) and current is not None
                      and str(current.get("value")) == claim_value) or (feature.startswith("detail.") and oid in detail_ids)
            if not normalized and not backed:
                continue
            if normalized:
                candidates = claims.get(oid, [])
                matching = [c for c in candidates if c["feature"] == feature and c["value"] == claim_value
                            and c["span"]["quote"].strip()[:400] == item["quote"]
                            and c["source_type"] == item.get("source")
                            and isinstance(c.get("source_id"), str) and c["source_id"]
                            and verdicts.get(label_key(c["source_id"], c["feature"], c["value"],
                                                       c["span"]["quote"])) not in ("wrong", "unsure_again")]
                if not matching:
                    continue
                matched_claims[(oid, value)] = matching
            kept.append((oid, value))
            if backed:
                served_claims.append((oid, value))
        if kept:
            kept = served_claims or kept
            return ({**item, "observation_id": kept[0][0], "observations": [i for i, _ in kept],
                     "features": [f for _, f in kept],
                     "claims": [c for pair in kept for c in matched_claims.get(pair, [])]}, bool(served_claims))
        return None
    return gate


def run(city: str = "dalat", *, source_root=None, output_root=None, publish=True, eligible_ids=None,
        normalization_root=None) -> dict:
    import lancedb
    strict = source_root is not None or output_root is not None or eligible_ids is not None
    data = Path(source_root) if source_root is not None else data_dir()
    destination = Path(output_root) if output_root is not None else data
    records = json.loads((destination / "serving" / "places.json").read_text(encoding="utf-8"))["records"]
    statuses = ("VERIFIED", "UNCERTAIN", "OUTDATED") if strict else (None, "VERIFIED", "UNCERTAIN", "OUTDATED")
    recs = {r["id"]: r for r in records if r.get("status") in statuses}
    ids = sorted(set(recs) & set(eligible_ids)) if eligible_ids is not None else list(recs)
    recs = {pid: recs[pid] for pid in ids}
    voc = vocabulary()
    cfg, issues, inputs, dimensions = config(), [], [], {}
    if strict:
        issues.extend({"place_id": r["id"], "kind": "place", "reason": "ineligible_place"}
                      for r in records if r["id"] not in recs)
    verdicts = label_verdicts(root=data) if strict else {}
    gate = _span_gate(data, destination, recs, normalization_root, verdicts=verdicts) if strict else None
    version = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    out = destination / "index" / version
    out.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(out))

    options = dict(strict=strict, cfg=cfg, issues=issues, inputs=inputs, dimensions=dimensions, gate=gate)
    pv, prow = _load_pairs(data, "photos", ids, **options)
    fv, frow = _load_pairs(data, "frames", ids, **options)
    photo_vecs = np.concatenate([x for x in (pv, fv) if x.size]) if (pv.size or fv.size) else pv
    photo_rows = [{**r, "author": r.get("author_hash") or r.get("photo_id")} for r in prow + frow]
    n_photos = _table(db, "photos", photo_vecs, photo_rows, ["place_id", "file", "source", "author", "owner", "month"])
    sv, srow = _load_pairs(data, "spans", ids, **options)
    n_spans = _table(db, "spans", sv, srow, ["place_id", "observation_id", "observations", "features", "quote", "source", "served", "claims"])

    places = {}
    for pid in ids:
        r = recs[pid]
        style_path = data / "gmaps" / "style_observations" / f"{safe_name(pid)}.json"
        if strict and style_path.is_file():
            inputs.append({"path": style_path.relative_to(data).as_posix(),
                           "sha256": hashlib.sha256(style_path.read_bytes()).hexdigest()})
        places[pid] = {"name": r["identity"]["name"], "category_group": r["identity"].get("category_group"),
                       "styles": place_styles(data, pid, voc, strict=strict, issues=issues, verdicts=verdicts),
                       "near_duplicate_group": r.get("near_duplicate_group")}
    (out / "places.json").write_text(json.dumps(places, ensure_ascii=False), encoding="utf-8")
    (out / "styles.json").write_text(json.dumps(voc, ensure_ascii=False), encoding="utf-8")
    styled = sum(1 for p in places.values() if p["styles"])
    served_spans = sum(1 for r in srow if r.get("served", True))
    summary = {"version": version, "photos": n_photos, "spans": n_spans, "spans_served": served_spans,
               "places": len(places), "styled": styled,
               "built_at": datetime.now(UTC).isoformat(timespec="seconds")}
    if strict:
        coverage = {}
        for group in ("stay", "non_stay"):
            members = {pid for pid in ids if (recs[pid]["identity"].get("category_group") == "stay") == (group == "stay")}
            coverage[group] = {"places": len(members), "photos": sum(r["place_id"] in members for r in photo_rows),
                               "spans": sum(r["place_id"] in members for r in srow),
                               "styles": sum(bool(places[p]["styles"]) for p in members)}
            covered = {"photos": {r["place_id"] for r in photo_rows}, "spans": {r["place_id"] for r in srow},
                       "styles": {p for p in members if places[p]["styles"]}}
            coverage[group]["status"] = {kind: "unavailable" if not (available & members) else
                                        "ready" if members <= available else "partial"
                                        for kind, available in covered.items()}
        summary.update(issues=issues, inputs=inputs, dimensions=dimensions,
                       models={"image": cfg["embedder"]["image_model"], "text": cfg["embedder"]["text_model"]},
                       coverage=coverage)
    (out / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    if publish:
        tmp = destination / "index" / ("current." + uuid.uuid4().hex + ".tmp")
        tmp.write_text(version, encoding="utf-8")
        os.replace(tmp, destination / "index" / "current")
    print(f"corpus index {city}: {json.dumps(summary)}")
    return summary
