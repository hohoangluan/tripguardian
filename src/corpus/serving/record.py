"""Serving record of one place (docs/PLACE_DECISION.md §2.2, docs/CORPUS.md §5-6) from its intel file.

Status per aspect: VERIFIED | UNCERTAIN | OUTDATED are served, NEEDS_REVIEW | DISABLED never appear. A feature is
VERIFIED only when its value may be served by itself (intel `servable`: authority, label gate, every author checked
by the Judge or a person) and fresh; an unmeasured, conflicting or weakly agreed value is UNCERTAIN, with the reason.
A place the Judge found closed or turned into another business (decisions kind place_status) is DISABLED; one whose
closure reports it could not settle is served UNCERTAIN (`closure_reported`). Estimates (visit time, entry fee,
category effort hint) say so and never decide a hard filter. `check` is the fail-closed test Place Decision runs.
"""

from datetime import date
from functools import cache

import yaml

from ..crawl.common.files import ROOT
from ..ontology import load

load_ontology = cache(load)  # one parse per process: build() runs once per place

PATH = ROOT / "config" / "serving.yaml"
SERVED = ("VERIFIED", "UNCERTAIN", "OUTDATED")
EVIDENCE_IDS = 5
CROWD_FEATURES = {"crowd", "wait_time", "noise"}


@cache
def config() -> dict:
    return yaml.safe_load(PATH.read_text(encoding="utf-8"))


def _window(key: str) -> int:
    w = config()["freshness_days"]
    return w.get(key, w["default"])


def feature_status(sig: dict) -> tuple[str, str | None]:
    """(status, reason) of one intel feature signal."""
    if sig.get("status") == "disabled":
        return "DISABLED", "person_disabled"
    if sig.get("needs_review"):
        return "NEEDS_REVIEW", "unchecked"  # a value that widens a choice, not yet checked
    if sig.get("status") == "uncertain":
        return "UNCERTAIN", "conflict" if sig.get("authority") is None and len(sig["distribution"]) > 1 else "low_agreement"
    if not sig.get("servable"):
        return "UNCERTAIN", "unmeasured_precision"
    return "VERIFIED", None


def _feature(fid: str, sig: dict) -> dict | None:
    status, reason = feature_status(sig)
    if status not in SERVED:
        return None
    age = sig["confidence"].get("freshness_days")
    if status == "VERIFIED" and age is not None and age > _window("crowd" if fid in CROWD_FEATURES else "default"):
        status, reason = "OUTDATED", "old_evidence"
    return {"value": sig["top_value"], "distribution": sig["distribution"], "status": status, "reason": reason,
            "n": sig["n"], "mention_rate": sig.get("mention_rate"), "confidence": sig["confidence"],
            "by_context": sig.get("by_context") or {}, "precision": (sig.get("quality") or {}).get("lower"),
            "evidence": sig["observation_ids"][:EVIDENCE_IDS]}


def _fact(value, as_of: date, built: date, key: str) -> dict | None:
    if value is None:
        return None
    return {"value": value, "status": "OUTDATED" if (built - as_of).days > _window(key) else "VERIFIED",
            "as_of": as_of.isoformat()}


def place_status(closure: str | None, judged: str | None) -> tuple[str, str | None]:
    """(status, reason) of the place: Maps' own closure, else the Judge's place_status verdict."""
    if closure:
        return "DISABLED", f"closure_{closure}"
    if judged in ("closed", "changed"):
        return "DISABLED", f"judge_{judged}"
    if judged == "unclear":
        return "UNCERTAIN", "closure_reported"
    return "VERIFIED", None


def build(intel: dict, built: date | None = None, judged: str | None = None) -> dict:
    """One serving record. Place `status` DISABLED (closed for good or for now) keeps the record out of serving;
    judged: the Judge's place_status verdict for this place, if it was reported closed."""
    ont = load_ontology()
    built = built or date.today()
    as_of = date.fromisoformat(intel["as_of"])
    ident, op, est = intel.get("identity") or {}, intel.get("operation") or {}, intel.get("estimates") or {}
    features = {fid: f for fid, sig in intel["features"].items() if fid in ont.features and (f := _feature(fid, sig))}
    groups = {g: {fid: f for fid, f in features.items() if ont.features[fid].group == g} for g in ont.groups}
    closure = op.get("closure")
    coverage = intel.get("coverage") or {}
    usable = [u for u in est.get("usable_as_default") or [] if u != "experience" or coverage.get("experience") != "NONE"]
    price = op.get("price_range")
    status, reason = place_status(closure, judged)
    return {
        "id": intel["place_fid"],
        "status": status,
        "status_reason": reason,
        "identity": {"name": intel.get("place_name"), "kind": "POI", "category": ident.get("category"),
                     "category_group": est.get("category_group"), "lat": ident.get("lat"), "lng": ident.get("lng"),
                     "address": ident.get("address"), "area": None},
        "operation": {
            "hours": _fact(op.get("hours"), as_of, built, "hours"),
            "price_per_person": _fact({k: price.get(k) for k in ("min_vnd", "max_vnd", "level") if k in price}
                                      if price else None, as_of, built, "price"),
            "entry_fee": {**est["entry_fee"], "kind": "estimate"} if est.get("entry_fee") else None,
            "visit_minutes": {**est["visit_minutes"], "kind": "estimate"} if est.get("visit_minutes") else None,
            "booking": features.get("booking_needed"),
            "crowd_by_time": op.get("crowd_by_time"),
        },
        **{g: fs for g, fs in groups.items() if g != "operation"},
        "effort_hint": {"value": est.get("effort_hint"), "kind": "estimate"},
        "usable_as": usable,
        "provenance": {"as_of": intel["as_of"], "coverage": coverage, "voices": intel.get("voices"),
                       "rating_trend": intel.get("rating_trend"), "inputs": intel.get("inputs", [])},
    }


def feature(record: dict, fid: str) -> dict | None:
    group = load_ontology().features[fid].group
    return record.get(group, {}).get(fid)


def check(record: dict, fid: str, forbidden: str) -> str:
    """pass | fail | unknown for the hard filter "fid != forbidden" (docs/PLACE_DECISION.md §6.2), fail-closed:
    pass needs a VERIFIED / OUTDATED value other than `forbidden` that nobody contradicts; fail needs `forbidden`
    VERIFIED / OUTDATED; an UNCERTAIN value, no evidence or any author saying `forbidden` is unknown."""
    f = feature(record, fid)
    if f is None:
        return "unknown"
    firm = f["status"] in ("VERIFIED", "OUTDATED")
    if f["value"] == forbidden:
        return "fail" if firm else "unknown"
    if forbidden in f["distribution"] or not firm:
        return "unknown"
    return "pass"
