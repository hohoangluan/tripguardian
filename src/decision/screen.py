"""③ Constraint screen (docs/PLACE_DECISION.md §6): physical first, then each hard filter, pass | fail | unknown."""

from functools import cache
from types import SimpleNamespace

from corpus.ontology import load
from corpus.serving import check, feature

from .model import FIRM, Cand

SAFETY = {"effort", "suitability"}  # access / safety: an UNCERTAIN value is never a pass here


@cache
def _ontology():
    return load()


def hard_result(rec: dict, h) -> tuple[str, str | None]:
    """(pass | fail | unknown, warning code) for one trip.HardFilter."""
    f = feature(rec, h.feature)
    if h.op == "eq":
        if f is None or f["status"] not in FIRM:
            return "unknown", None
        if f["value"] != h.value:
            return "fail", None
        return ("pass", None) if set(f["distribution"]) <= {h.value} else ("unknown", None)
    r = check(rec, h.feature, h.value)
    if (r == "unknown" and f is not None and f["status"] == "UNCERTAIN" and f["value"] != h.value
            and h.value not in f["distribution"] and _ontology().features[h.feature].group not in SAFETY):
        return "pass", "uncertain_value"
    return r, None


def hard_check(rec: dict, hard_filter: dict) -> str:
    """Public: pass | fail | unknown for one Search Input hard filter given as a dict (fail-closed, as hard_result)."""
    return hard_result(rec, SimpleNamespace(**hard_filter))[0]


def closed_all_days(rec: dict, days) -> bool:
    """True only when the weekdays are known and VERIFIED hours open on none of them."""
    hours = rec["operation"].get("hours")
    if not hours or hours["status"] != "VERIFIED" or not hours["value"] or any(d.weekday is None for d in days):
        return False
    return all(not hours["value"].get(d.weekday) for d in days)


def screen(c: Cand, si, days, relaxed: set[tuple[str, str]]) -> None:
    checks, warnings = [], []
    hours = c.rec["operation"].get("hours")
    if not hours:
        warnings.append("hours_unknown")
    elif hours["status"] == "OUTDATED":
        warnings.append("hours_outdated")
    if closed_all_days(c.rec, days):
        checks.append({"kind": "physical", "feature": "hours", "value": None, "op": None, "result": "fail",
                       "reason": "closed_all_trip_days", "policy": None})
    for h in si.hard_filters:
        if (c.id, h.feature) in relaxed:
            continue
        r, warn = hard_result(c.rec, h)
        if warn:
            warnings.append(f"{warn}:{h.feature}")
        checks.append({"kind": "hard", "feature": h.feature, "value": h.value, "op": h.op, "result": r,
                       "reason": f"hard:{h.feature}", "policy": h.unknown_policy})
    results = {x["result"] for x in checks}
    c.checks, c.warnings = checks, warnings
    c.status = "excluded" if "fail" in results else "unverified" if "unknown" in results else "main"
