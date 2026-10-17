"""Trip State -> the understanding panel (docs/TRIP_UNDERSTANDING.md §10). Data only; the web writes the words."""

from dataclasses import asdict

from pydantic import ValidationError
from requirements import applicable

from ..infrastructure.catalog import Catalog
from ..infrastructure.settings import Settings
from .budget import per_person_day, scope as budget_scope
from .coverage import admissible, coverage
from .card import Question
from .state import WEIGHT_SIGN, SoftKey, TripState, apply_drafts, pending_signals, unknown_fields
from .readiness import DEFAULT_REQUIRED, LABEL as REQUIRED_LABEL, TITLE as REQUIRED_TITLE, missing
from .compile import compile_search_input
from .frame import FrameDefaults
from .readback import build as build_readback
from .rental import rental_hint
from .values import jsonable

MARKED = ("inferred", "anchor", "profile")
TRIP_ROWS = ("start_date", "month", "month_part", "days", "nights", "companions", "people", "origin", "arrival_mode", "inbound", "outbound",
             "lodging_booked", "lodging", "base", "entry_point", "exit_point", "mobility", "checkin_at", "checkout_at", "day_end")


def to_taste(state: TripState):
    """-> fits(candidate): passes when the place has evidence for at least one liked soft value (any, when nothing is
    liked yet) and no evidence for an avoided one. Unknown is never against a place."""
    love, avoid = [], []
    for key, f in state.soft.items():
        if f.known and WEIGHT_SIGN.get(f.value):
            k = SoftKey.parse(key)
            intent = {"feature": k.feature, "scope": f.requirement.scope if f.requirement else None}
            (love if WEIGHT_SIGN[f.value] > 0 else avoid).append((k.feature, k.value, k.context, intent))
    def fits(c):
        rec, activity = c.requirement_record(), state.activities.get(c.id)
        likes = [(fe, v, cx) for fe, v, cx, intent in love if applicable(rec, intent, activity)]
        avoids = [(fe, v, cx) for fe, v, cx, intent in avoid if applicable(rec, intent, activity)]
        return ((not likes or any(c.value(fe, cx) == v for fe, v, cx in likes))
                and not any(c.value(fe, cx) == v for fe, v, cx in avoids))
    return fits


def matching(state: TripState, catalog: Catalog | None) -> int:
    """Places past the hard limits and to the taste so far: the "Đang hợp với bạn" count."""
    return len(fitting(state, catalog))


BOARD = 24  # places the Understand screen's board shows


def fitting(state: TripState, catalog: Catalog | None) -> list:
    """The places past the hard limits and to the taste: one pass shared by the count and the board."""
    fits = to_taste(state)
    return [c for c in (catalog.places if catalog is not None else ())
            if admissible(c, state.hard, state.activities.get(c.id)) and fits(c)]


def board(state: TripState, catalog: Catalog | None, n: int = BOARD, pool: list | None = None) -> dict:
    """The places that fit right now, for the board beside the chat: a chosen look's places first (in its order),
    then the places with most liked features, then the best documented. Ranking only: the count is `matching`,
    nothing here removes a place."""
    if catalog is None:
        return {"ids": [], "vibe": []}
    pool = list(fitting(state, catalog) if pool is None else pool)
    rank: dict[str, int] = {}
    for v in state.vibes:
        if v.status != "none":
            for i, pid in enumerate(v.places):
                rank.setdefault(pid, i)
    loves = [(k.feature, k.value, k.context) for key, f in state.soft.items()
             if f.known and WEIGHT_SIGN.get(f.value, 0) > 0 for k in (SoftKey.parse(key),)]
    pool.sort(key=lambda c: (c.id not in rank, rank.get(c.id, 0),
                             -sum(c.value(fe, cx) == val for fe, val, cx in loves), -c.weight))
    top = pool[:n]
    return {"ids": [c.id for c in top], "vibe": [c.id for c in top if c.id in rank]}


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
        f = getattr(state.frame if target in {"arrive", "leave"} else state, target)
        if not f.known:
            return None
        value = jsonable(f.value)
        if target == "base" and f.value.place_id in catalog.by_id:
            value["name"] = catalog.by_id[f.value.place_id].name
        return {"target": target, "value": value,
                "mark": f.source != "user" if target in {"arrive", "leave"} else f.source in MARKED,
                "confidence": f.confidence}

    def budget() -> dict | None:
        """The amount as said, what it covers (a guess from its size when nobody said), and per person per day."""
        r = row("budget_vnd")
        if r is None:
            return None
        sc, guessed = budget_scope(state)
        r["value"] = {"amount": r["value"], "scope": sc, "guessed": guessed, "per_person_day": per_person_day(state)}
        r["solo"] = state.people.value == 1 if state.people.known else None  # "cho 1 người", not "cả nhóm"
        r["mark"] = r["mark"] or guessed or state.budget_scope.source in MARKED
        return r

    places = catalog.places if catalog is not None else ()
    fit = fitting(state, catalog)
    hard = []
    open_policy = False
    for h in state.hard:
        cov = coverage(h, catalog.places, cfg.enough, state.activities)
        open_policy |= h.unknown_policy is None and cov.level != "enough"
        hard.append({"target": f"hard:{h.feature}", "feature": h.feature, "op": h.op, "value": h.value,
                     "unknown_policy": h.unknown_policy, "coverage": asdict(cov),
                     "requirement": {k: getattr(h, k) for k in ("meaning", "scope", "subject", "subject_count", "ambiguity")}})
    soft = []
    for key, f in sorted(state.soft.items()):
        if f.known:
            k = SoftKey.parse(key)
            like = next((e.tool[6:] for e in reversed(f.evidence) if e.tool and e.tool.startswith("place:")), None)
            soft.append({"target": f"soft:{key}", "key": key, "feature": k.feature, "value": k.value,
                         "context": dict(k.context), "weight": f.value, "mark": f.source in MARKED,
                         "like": catalog.by_id[like].name if like in catalog.by_id else None,
                         "requirement": f.requirement.model_dump() if f.requirement else None})
    missing_fields = missing(state, cfg.required if cfg else DEFAULT_REQUIRED)
    readback = None
    if not missing_fields:
        si = compile_search_input(state, cfg.arrival_buffer_min, cfg.coach_min_people,
                                  entry_min=cfg.entry_min, defaults=FrameDefaults(**cfg.frame))
        rb = build_readback(si)
        readback = {**rb.model_dump(mode="json"), "ok": state.meta.readback_digest == rb.digest}
    return {
        "purpose": row("purpose"),
        "trip": [r for r in map(row, (*TRIP_ROWS, "arrive", "leave", "driver", "care", "budget_unlimited")) if r],
        "anchors": [{"target": f"anchor:{i}", "text": a.text, "place_id": a.place_id,
                     "name": catalog.by_id[a.place_id].name if a.place_id in catalog.by_id else None,
                     "state": a.state, "priority": a.priority} for i, a in enumerate(state.anchors)],
        "hard": hard,
        "soft": soft,
        "activities": state.activities,
        "pace": row("pace"), "max_leg_min": row("max_leg_min"), "crowd_tolerance": row("crowd_tolerance"),
        "novelty": row("novelty"), "budget_vnd": budget(), "liked_groups": row("liked_groups"),
        "rental": rental_hint(state),
        "unknowns": unknown_fields(state),
        "unmapped": [{"target": f"unmapped:{i}", "phrase": u.phrase} for i, u in enumerate(state.unmapped)],
        # Next is always open: ready means no open health hint blocks the hand-off
        # (fail-closed). Other missing fields ride along as unknowns.
        "ready": not pending_signals(state),
        "missing": [{"target": k, "label": label} for k, label in missing_fields],
        "required": [{"key": key, "title": REQUIRED_TITLE[key], "label": REQUIRED_LABEL[key], "done": key not in {k for k, _ in missing_fields}}
                     for key in (cfg.required if cfg else DEFAULT_REQUIRED)],
        "readback": readback,
        "safety_pending": bool(pending_signals(state)) or open_policy,
        # How many places fit the trip right now: past the hard limits and to the taste so far (to_taste). A fact about
        # the current state, never a forecast; soft values only rank later, this count does not remove anything.
        "matching": len(fit),
        "total": len(places),
        "board": board(state, catalog, pool=fit),
        # looks the user wants (domain/vibes.py): what the ticket says about each
        "vibes": [{"target": f"vibe:{i}", "phrase": v.phrase, "status": v.status, "cues": list(v.cues),
                   "chosen": [k.label for k in v.offered if k.id in v.chosen], "image": v.image,
                   "picked": catalog.by_id[v.picked].name if v.picked and v.picked in catalog.by_id else None,
                   "places": len(v.places)} for i, v in enumerate(state.vibes)],
    }
