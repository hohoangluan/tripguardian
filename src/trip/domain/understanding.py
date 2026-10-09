"""Trip State -> the understanding panel (docs/TRIP_UNDERSTANDING.md §10). Data only; the web writes the words."""

from dataclasses import asdict

from pydantic import ValidationError

from ..infrastructure.catalog import Catalog
from ..infrastructure.settings import Settings
from .budget import per_person_day, scope as budget_scope
from .coverage import admissible, coverage
from .card import Question
from .state import WEIGHT_SIGN, SoftKey, TripState, apply_drafts, pending_signals, unknown_fields
from .readiness import DEFAULT_REQUIRED, missing
from .values import jsonable

MARKED = ("inferred", "anchor", "profile")
TRIP_ROWS = ("start_date", "month", "month_part", "days", "companions", "people", "origin", "arrival_mode", "inbound", "outbound",
             "lodging_booked", "lodging", "base", "entry_point", "exit_point", "mobility", "arrive_at", "leave_at", "day_end")


def to_taste(state: TripState):
    """-> fits(candidate): passes when the place has evidence for at least one liked soft value (any, when nothing is
    liked yet) and no evidence for an avoided one. Unknown is never against a place."""
    love, avoid = [], []
    for key, f in state.soft.items():
        if f.known and WEIGHT_SIGN.get(f.value):
            k = SoftKey.parse(key)
            (love if WEIGHT_SIGN[f.value] > 0 else avoid).append((k.feature, k.value, k.context))
    return lambda c: ((not love or any(c.value(fe, cx) == v for fe, v, cx in love))
                      and not any(c.value(fe, cx) == v for fe, v, cx in avoid))


def matching(state: TripState, catalog: Catalog | None) -> int:
    """Places past the hard limits and to the taste so far: the "Đang hợp với bạn" count."""
    fits = to_taste(state)
    return sum(1 for c in (catalog.places if catalog is not None else ()) if admissible(c, state.hard) and fits(c))


def chip_effects(state: TripState, q: Question | None, catalog: Catalog | None) -> dict[str, int]:
    """chip id -> how many places that count gains (+) or loses (−) if this chip alone is chosen now; chips that change
    nothing are left out. Computed on a copy of the state: nothing is written."""
    if q is None or catalog is None:
        return {}
    now, out = matching(state, catalog), {}
    for c in q.chips:
        if not c.drafts:
            continue
        try:
            after = apply_drafts(state, c.drafts, state.meta.turn + 1, tool=f"preview:{q.qid}")
        except (ValueError, ValidationError):
            continue
        if n := matching(after, catalog) - now:
            out[c.id] = n
    return out


def view(state: TripState, catalog: Catalog, cfg: Settings) -> dict:
    def row(target: str) -> dict | None:
        f = getattr(state, target)
        if not f.known:
            return None
        value = jsonable(f.value)
        if target == "base" and f.value.place_id in catalog.by_id:
            value["name"] = catalog.by_id[f.value.place_id].name
        return {"target": target, "value": value, "mark": f.source in MARKED, "confidence": f.confidence}

    def budget() -> dict | None:
        """The amount as said, what it covers (a guess from its size when nobody said), and per person per day."""
        r = row("budget_vnd")
        if r is None:
            return None
        sc, guessed = budget_scope(state)
        r["value"] = {"amount": r["value"], "scope": sc, "guessed": guessed, "per_person_day": per_person_day(state)}
        r["mark"] = r["mark"] or guessed or state.budget_scope.source in MARKED
        return r

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
            like = next((e.tool[6:] for e in reversed(f.evidence) if e.tool and e.tool.startswith("place:")), None)
            soft.append({"target": f"soft:{key}", "key": key, "feature": k.feature, "value": k.value,
                         "context": dict(k.context), "weight": f.value, "mark": f.source in MARKED,
                         "like": catalog.by_id[like].name if like in catalog.by_id else None})
    return {
        "purpose": row("purpose"),
        "trip": [r for r in map(row, TRIP_ROWS) if r],
        "anchors": [{"target": f"anchor:{i}", "text": a.text, "place_id": a.place_id,
                     "name": catalog.by_id[a.place_id].name if a.place_id in catalog.by_id else None,
                     "state": a.state, "priority": a.priority} for i, a in enumerate(state.anchors)],
        "hard": hard,
        "soft": soft,
        "pace": row("pace"), "max_leg_min": row("max_leg_min"), "crowd_tolerance": row("crowd_tolerance"),
        "novelty": row("novelty"), "budget_vnd": budget(), "liked_groups": row("liked_groups"),
        "unknowns": unknown_fields(state),
        "unmapped": [{"target": f"unmapped:{i}", "phrase": u.phrase} for i, u in enumerate(state.unmapped)],
        "ready": not (miss := missing(state, cfg.required if cfg else DEFAULT_REQUIRED)),
        "missing": [{"target": k, "label": label} for k, label in miss],
        "safety_pending": bool(pending_signals(state)) or open_policy,
        # How many places fit the trip right now: past the hard limits and to the taste so far (to_taste). A fact about
        # the current state, never a forecast; soft values only rank later, this count does not remove anything.
        "matching": matching(state, catalog),
        "total": len(places),
    }
