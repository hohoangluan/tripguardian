"""③ Constraint screen (docs/PLACE_DECISION.md §6): physical first, then each hard filter, pass | fail | unknown."""

from requirements import hard_result

from .model import Cand


def hard_check(rec: dict, hard_filter: dict, activity=None) -> str:
    """Public: pass | fail | unknown | not_applicable for a Search Input hard filter."""
    return hard_result(rec, hard_filter, activity)[0]


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
        r, warn = hard_result(c.rec, h, si.activities.get(c.id), c.role)
        if warn:
            warnings.append(f"{warn}:{h.feature}")
        checks.append({"kind": "hard", "feature": h.feature, "value": h.value, "op": h.op, "result": r,
                       "reason": f"hard:{h.feature}", "policy": h.unknown_policy})
    results = {x["result"] for x in checks}
    c.checks, c.warnings = checks, warnings
    c.status = "excluded" if "fail" in results else "unverified" if "unknown" in results else "main"
