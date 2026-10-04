"""Trip State -> the understanding panel (docs/TRIP_UNDERSTANDING.md §10). Data only; the web writes the words."""

from dataclasses import asdict

from .catalog import Catalog
from .coverage import admissible, coverage
from .settings import Settings
from .state import SoftKey, TripState, pending_signals, unknown_fields
from .values import jsonable

MARKED = ("inferred", "anchor", "profile")
TRIP_ROWS = ("start_date", "month", "days", "companions", "people", "base", "entry_point", "exit_point", "mobility",
             "arrive_at", "leave_at", "day_end")


def view(state: TripState, catalog: Catalog, cfg: Settings) -> dict:
    def row(target: str) -> dict | None:
        f = getattr(state, target)
        if not f.known:
            return None
        value = jsonable(f.value)
        if target == "base" and f.value.place_id in catalog.by_id:
            value["name"] = catalog.by_id[f.value.place_id].name
        return {"target": target, "value": value, "mark": f.source in MARKED, "confidence": f.confidence}

    places = catalog.places if catalog is not None else ()
    hard = []
    open_policy = False
    for h in state.hard:
        cov = coverage(h, catalog.places, cfg.enough)
        open_policy |= h.unknown_policy is None and cov.level != "enough"
        hard.append({"target": f"hard:{h.feature}", "feature": h.feature, "op": h.op, "value": h.value,
                     "unknown_policy": h.unknown_policy, "coverage": asdict(cov)})
    soft = []
    for key, f in sorted(state.soft.items()):
        if f.known:
            k = SoftKey.parse(key)
            soft.append({"target": f"soft:{key}", "key": key, "feature": k.feature, "value": k.value,
                         "context": dict(k.context), "weight": f.value, "mark": f.source in MARKED})
    return {
        "purpose": row("purpose"),
        "trip": [r for r in map(row, TRIP_ROWS) if r],
        "anchors": [{"target": f"anchor:{i}", "text": a.text, "place_id": a.place_id,
                     "name": catalog.by_id[a.place_id].name if a.place_id in catalog.by_id else None,
                     "state": a.state, "priority": a.priority} for i, a in enumerate(state.anchors)],
        "hard": hard,
        "soft": soft,
        "pace": row("pace"), "max_leg_min": row("max_leg_min"), "crowd_tolerance": row("crowd_tolerance"),
        "novelty": row("novelty"), "budget_vnd": row("budget_vnd"),
        "unknowns": unknown_fields(state),
        "unmapped": [{"target": f"unmapped:{i}", "phrase": u.phrase} for i, u in enumerate(state.unmapped)],
        "safety_pending": bool(pending_signals(state)) or open_policy,
        # How many places pass the hard limits right now: a fact about the current state, never a forecast.
        "matching": sum(1 for c in places if admissible(c, state.hard)),
        "total": len(places),
    }
