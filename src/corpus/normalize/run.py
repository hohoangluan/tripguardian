"""Deterministic, source-separated adapters and explicit aggregate input manifests."""

import collections
import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from ..crawl.common.files import ROOT, data_dir, safe_name, write_json
from ..ontology import load as load_ontology
from .schema import Claim, Document, Proposed, Rating

VERSION = 1
FOLDERS = (("gmaps", "observations"), ("gmaps", "photo_observations"),
           ("tiktok", "observations"), ("official", "observations"), ("reports", "observations"))


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True)
class Normalization:
    id: str
    root: Path
    manifest: dict

    def documents(self):
        for item in self.manifest["inputs"]:
            if item.get("normalized"):
                p = self.root / item["normalized"]
                payload = p.read_bytes()
                if _hash(payload) != item["normalized_sha256"]:
                    raise ValueError(f"normalized artifact changed: {p}")
                yield item["path"], json.loads(payload)


def _references(root: Path, fid: str, claim: dict) -> list[Path]:
    source, sid = claim["source_type"], claim["source_id"]
    base = root / "gmaps" / "places" / safe_name(fid)
    if source == "gmaps_attribute":
        return [base / "place.json"]
    if source in ("gmaps_review", "gmaps_details"):
        return sorted(base.glob("reviews*.json"))
    if source == "gmaps_photo":
        return [base / "photos.json", base / claim["span"]["field"]]
    if source.startswith("tiktok_"):
        video = root / "tiktok" / "videos" / sid
        if source == "tiktok_frame":
            meta = video / "video.json"
            try:
                duration = (json.loads(meta.read_bytes()).get("transcript") or {}).get("total_s")
                at = claim["span"].get("start_s")
                if not duration or at is None or not 0 <= at <= duration:
                    return []
                from ..crawl.tiktok.frames import FRAMES
                n = max(1, min(FRAMES, round(at * FRAMES / duration + 0.5)))
                return [meta, video / "frames" / f"f{n}.jpg"]
            except (OSError, ValueError, TypeError):
                return []
        return [video / "video.json"]
    if source == "official_page":
        return [root / "official" / "pages" / f"{safe_name(fid)}.json"]
    if source == "traveller_report":
        return [root / "review" / "reports.jsonl"]
    return []


def _review_rows(data) -> dict[str, dict]:
    if isinstance(data, dict):
        ids = {data["review_id"]: data} if isinstance(data.get("review_id"), str) else {}
        for value in data.values():
            if isinstance(value, (dict, list)):
                ids.update(_review_rows(value))
        return ids
    out = {}
    if isinstance(data, list):
        for item in data:
            out.update(_review_rows(item))
    return out


REANCHOR_S = 2.0  # a re-run transcript moves segment edges; a verbatim quote this close is the same words


def _span_check(claim, paths, refs) -> str | None:
    """None when the quote stands in its saved source, else the issue reason. A TikTok quote found verbatim in a
    segment within REANCHOR_S of its old times is pointed at that segment (span updated, old times kept)."""
    if claim["source_type"] == "gmaps_review":
        sid = claim["source_id"]
        if not any(((d.get(sid) or {}).get("text") or "").strip() for d in (refs[p][1] for p in paths) if isinstance(d, dict)):
            return "missing_source"
    if _span_valid(claim, paths, refs):
        return None
    if claim["source_type"] == "tiktok_segment" and _reanchor(claim, paths, refs):
        return None
    return "invalid_source_span"


def _reanchor(claim, paths, refs) -> bool:
    from ..observe.gmaps.gate import norm
    span, data = claim["span"], [refs[p][1] for p in paths]
    video = data[0] if data and isinstance(data[0], dict) else {}
    quote, start, end = norm(span["quote"]), span.get("start_s"), span.get("end_s")
    if not quote or not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
        return False
    near = [s for s in (video.get("transcript") or {}).get("segments") or []
            if isinstance(s.get("start_s"), (int, float)) and isinstance(s.get("end_s"), (int, float))
            and s["start_s"] <= end + REANCHOR_S and s["end_s"] >= start - REANCHOR_S
            and quote in norm(s.get("checked_text") or "")]
    if not near:
        return False
    best = min(near, key=lambda s: abs(s["start_s"] - start) + abs(s["end_s"] - end))
    claim["span"] = {**span, "start_s": best["start_s"], "end_s": best["end_s"],
                     "reanchored_from": {"start_s": start, "end_s": end}}
    return True


def _span_valid(claim, paths, refs) -> bool:
    from ..observe.gmaps.gate import norm
    source, sid, span = claim["source_type"], claim["source_id"], claim["span"]
    data = [refs[p][1] for p in paths]
    quote = norm(span["quote"])
    if not quote:
        return False
    if source == "gmaps_review":
        return any(quote in norm((d.get(sid) or {}).get("text") or "") for d in data if isinstance(d, dict))
    if source == "gmaps_details":
        return any(quote == norm(line) for d in data if isinstance(d, dict)
                   for line in (d.get(sid) or {}).get("details") or [] if isinstance(line, str))
    if source == "gmaps_attribute":
        doc = data[0] if data and isinstance(data[0], dict) else {}
        return sid == claim["place_fid"] and any(quote == norm(a) for a in doc.get("attributes") or [] if isinstance(a, str))
    if source in ("tiktok_segment", "tiktok_caption"):
        video = data[0] if data and isinstance(data[0], dict) else {}
        if source == "tiktok_caption":
            text = " ".join([video.get("caption") or "", *(f"#{h}" for h in video.get("hashtags") or [])])
            return quote in norm(text)
        segments = (video.get("transcript") or {}).get("segments") or []
        return any(s.get("start_s") == span.get("start_s") and s.get("end_s") == span.get("end_s")
                   and quote in norm(s.get("checked_text") or "") for s in segments)
    if source == "official_page":
        doc = data[0] if data and isinstance(data[0], dict) else {}
        return any(p.get("url") == sid and quote in norm(p.get("text") or "") for p in doc.get("pages") or [])
    if source == "traveller_report":
        return any(d.get("id") == sid and d.get("place_id") == claim["place_fid"]
                   and quote in norm(d.get("text") or "") for d in (data[0] or []))
    return True


def normalize(city: str, root: Path | None = None, canonical: dict[str, str] | None = None, *, output_root: Path | None = None) -> Normalization:
    root = root or data_dir()
    resolved_root = root.resolve()
    city = city.removesuffix("_stay")
    if not city or Path(city).name != city or city in (".", ".."):
        raise ValueError("city must be a directory key")
    if canonical is None:
        from ..judge import merges
        canonical = merges(root=root)
    ont = load_ontology()
    manifest = {"schema_version": 1, "normalizer_version": VERSION, "ontology_version": ont.version,
                "city": city, "redirects": canonical, "inventory": [], "inputs": [], "issues": [], "backups": [],
                "dependencies": []}
    issues = manifest["issues"]
    roles = collections.defaultdict(set)
    for suffix, role in (("", "experience"), ("_stay", "stay")):
        p = root / "gmaps" / "list" / f"{city}{suffix}.json"
        if p.exists():
            raw = p.read_bytes()
            manifest["dependencies"].append({"path": p.relative_to(root).as_posix(), "sha256": _hash(raw)})
            d = json.loads(raw)
            if not isinstance(d, dict) or not isinstance(d.get("items"), list):
                raise ValueError(f"invalid inventory: {p}")
            for item in d["items"]:
                fid = item.get("fid") if isinstance(item, dict) else None
                if not isinstance(fid, str) or not fid:
                    raise ValueError(f"invalid inventory ID: {p}")
                roles[canonical.get(fid, fid)].add(role)
    strict = bool(manifest["dependencies"])
    manifest["inventory_mode"] = "listed" if strict else "legacy_unlisted"
    manifest["inventory"] = [{"id": fid, "roles": sorted(role), "classification_conflict": len(role) > 1}
                             for fid, role in sorted(roles.items())]
    for item in manifest["inventory"]:
        if item["classification_conflict"]:
            issues.append({"path": "gmaps/list", "place_id": item["id"], "reason": "classification_conflict"})
    for source in ("gmaps", "tiktok", "official", "reports", "review"):
        base = root / source
        if base.exists():
            manifest["backups"] += [p.relative_to(root).as_posix() for p in sorted(base.iterdir())
                                    if "backup" in p.name or "before_" in p.name]
    for name in ("ontology.yaml", "companions.yaml"):
        p = ROOT / "config" / name
        manifest["dependencies"].append({"path": f"config/{name}", "sha256": _hash(p.read_bytes())})
    base = (output_root or root) / "normalization"
    staging = base / (".staging-" + uuid.uuid4().hex)
    staging.mkdir(parents=True)
    refs: dict[str, tuple[str | None, object]] = {}
    claim_count, legacy_count = 0, 0
    try:
        for source, folder in FOLDERS:
            for p in sorted((root / source / folder).glob("*.json")):
                rel = p.relative_to(root).as_posix()
                raw = p.read_bytes()
                entry = {"path": rel, "source": source, "sha256": _hash(raw), "bytes": len(raw),
                         "lifecycle": "quarantined", "reason": "invalid_json"}
                manifest["inputs"].append(entry)
                try:
                    payload = json.loads(raw)
                    if isinstance(payload, dict):
                        payload = {**payload, **{k: [] if payload.get(k) is None else payload[k]
                                                for k in ("observations", "details", "ratings", "proposed")}}
                        for key in ("place", "place_facts"):
                            if payload.get(key) is None:
                                payload[key] = {}
                    doc = Document.model_validate(payload).model_dump()
                except (ValueError, ValidationError) as exc:
                    reason = "invalid_json" if isinstance(exc, json.JSONDecodeError) else "invalid_document"
                    entry["reason"] = reason
                    issues.append({"path": rel, "reason": reason})
                    continue
                fid = doc["place_fid"]
                entry.update(place_id=fid, canonical_id=canonical.get(fid, fid), ontology_version=doc["ontology_version"])
                if strict and entry["canonical_id"] not in roles:
                    entry.update(lifecycle="historical", reason="outside_inventory")
                    continue
                legacy_count += doc["ontology_version"] != ont.version
                entry.update(lifecycle="active_inventory" if strict else "legacy_unlisted", reason="eligible",
                             compatibility="current" if doc["ontology_version"] == ont.version else "legacy_current_contract")
                seen, conflicts, excluded, dropped = {}, set(), set(), []
                document_refs = set()
                reference_paths = {}
                for field, schema in (("ratings", Rating), ("proposed", Proposed)):
                    rows = []
                    for value in doc[field]:
                        try:
                            rows.append(schema.model_validate(value).model_dump())
                        except (ValueError, ValidationError):
                            issues.append({"path": rel, "reason": f"invalid_{field}"})
                    doc[field] = rows
                for field in ("observations", "details"):
                    rows = []
                    for value in doc[field]:
                        if isinstance(value, dict):
                            value = dict(value)
                            if value.get("context") is None:
                                value["context"] = {}
                            observed = value.get("observed_at")
                            if observed is not None:
                                try:
                                    date.fromisoformat(observed + "-01" if len(observed) == 7 else observed)
                                except (ValueError, TypeError):
                                    value["observed_at"] = None
                                    issues.append({"path": rel, "id": value.get("id"), "reason": "invalid_observed_at"})
                        try:
                            claim = Claim.model_validate(value).model_dump()
                        except (ValueError, ValidationError):
                            excluded.add((value.get("feature") or "*") if isinstance(value, dict) else "*")
                            issues.append({"path": rel, "id": value.get("id") if isinstance(value, dict) else None, "reason": "invalid_claim"})
                            continue
                        for key in ("time_of_day", "day_type", "weather"):
                            v = claim["context"].get(key, "unknown")
                            claim["context"][key] = v if ont.valid_context(key, v) else "unknown"
                        key = (claim["source_type"], claim["id"])
                        if key in seen:
                            if seen[key] != claim:
                                conflicts.add(key)
                                excluded.add(claim["feature"])
                                issues.append({"path": rel, "id": claim["id"], "reason": "duplicate_claim_conflict"})
                            continue
                        seen[key] = claim
                        if claim["place_fid"] != fid or not (ont.valid(claim["feature"], claim["value"]) or ont.valid_detail(claim["feature"])):
                            excluded.add(claim["feature"])
                            issues.append({"path": rel, "id": claim["id"], "reason": "invalid_claim"})
                            continue
                        if strict:
                            reference_key = (("reviews",) if claim["source_type"] in ("gmaps_review", "gmaps_details") else
                                             (claim["source_type"], claim["source_id"], claim["span"]["field"], claim["span"].get("start_s")))
                            if reference_key not in reference_paths:
                                paths = _references(root, fid, claim)
                                path_keys = []
                                for ref in paths:
                                    rp = ref.relative_to(root).as_posix()
                                    path_keys.append(rp)
                                    document_refs.add(rp)
                                    if rp not in refs or (refs[rp][1] is None and refs[rp][0] is not None and ref.suffix in (".json", ".jsonl")):
                                        if not ref.resolve().is_relative_to(resolved_root):
                                            raise ValueError(f"source reference escapes data root: {ref}")
                                        content = ref.read_bytes() if ref.is_file() else None
                                        try:
                                            data = ([json.loads(line) for line in content.splitlines() if line.strip()]
                                                    if content and ref.suffix == ".jsonl" else json.loads(content)
                                                    if content and ref.suffix == ".json" else None)
                                        except ValueError:
                                            data = None
                                        if ref.name.startswith("reviews"):
                                            data = _review_rows(data)
                                        refs[rp] = (_hash(content) if content is not None else None, data)
                                reference_paths[reference_key] = path_keys
                            paths = reference_paths[reference_key]
                            valid = bool(paths) and all(refs[rp][0] is not None for rp in paths)
                            if claim["source_type"] in ("gmaps_review", "gmaps_details"):
                                valid = valid and any(claim["source_id"] in (refs[rp][1] or {}) for rp in paths)
                            # A claim whose source or span fails is dropped alone: aggregate re-judges the feature on
                            # the claims left, unless a dropped value disagreed (dropping it would inflate agreement).
                            if not valid:
                                dropped.append({"feature": claim["feature"], "value": claim["value"]})
                                issues.append({"path": rel, "id": claim["id"], "reason": "missing_source" if paths else "unsupported_source"})
                                continue
                            span_issue = _span_check(claim, paths, refs)
                            if span_issue:
                                dropped.append({"feature": claim["feature"], "value": claim["value"]})
                                issues.append({"path": rel, "id": claim["id"], "reason": span_issue})
                                continue
                            if "reanchored_from" in claim["span"]:
                                issues.append({"path": rel, "id": claim["id"], "reason": "span_reanchored"})
                        rows.append(claim)
                    doc[field] = rows
                for field in ("observations", "details"):
                    doc[field] = [c for c in doc[field] if (c["source_type"], c["id"]) not in conflicts]
                    claim_count += len(doc[field])
                doc["normalization_excluded_features"] = sorted(str(f) for f in excluded if f is not None)
                doc["normalization_dropped_claims"] = dropped
                normalized = _json_bytes(doc)
                target = staging / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(normalized)
                entry.update(normalized=rel, normalized_sha256=_hash(normalized))
                for rp in document_refs:
                    refs[rp] = (refs[rp][0], None)
        manifest["source_refs"] = [{"path": p, "sha256": v[0]} for p, v in sorted(refs.items())]
        manifest["summary"] = {"input_files": len(manifest["inputs"]), "eligible_files": sum(bool(i.get("normalized")) for i in manifest["inputs"]),
                               "claims": claim_count, "legacy_version_files": legacy_count,
                               "issues": dict(collections.Counter(i["reason"] for i in issues))}
        identity = _hash(_json_bytes(manifest))[:24]
        manifest["id"] = identity
        write_json(staging / "manifest.json", manifest)
        target = base / identity
        if target.exists():
            shutil.rmtree(staging)
        else:
            staging.rename(target)
        tmp = base / ("current." + uuid.uuid4().hex + ".tmp")
        tmp.write_text(identity, encoding="utf-8")
        os.replace(tmp, base / "current")
        return Normalization(identity, target, manifest)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
