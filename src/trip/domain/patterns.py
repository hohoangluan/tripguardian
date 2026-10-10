"""Long-term pattern learning (docs/P2_TRIP_UNDERSTANDING.md §17): which explicit choices a user keeps making.

A vote is one explicit choice made in one session. Silence is no vote (unknown is not "dislike"), a visited place is no
vote (visited is not "liked"), a value the user only confirmed from a stored pattern is no vote (no feedback loop), and
signals about health or the body, hard limits and trip facts are never voted on. Pure functions; storage is profile.py.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from typing import Literal

from pydantic import ValidationError

from ..infrastructure.catalog import Catalog
from ..infrastructure.settings import PatternSettings
from . import values
from .state import Base, Evidence, Frozen, TripState, Update, apply, with_meta

# What a user keeps choosing the same way becomes a prior, so later trips ask less: the tastes, and how they arrive
# (vehicle, mode, home city), what they spend and the hours they want. origin is voted as JSON of its Base.
VOTE_SCALARS = ("purpose", "pace", "crowd_tolerance", "novelty", "mobility", "arrival_mode", "origin", "budget_vnd",
                "checkin_at", "checkout_at")


class Summary(Frozen):
    """What one finished session voted for: key -> choice. Keys: a scalar field name, soft:<feature=value>, place:<id>."""
    sid: str
    day: date
    votes: dict[str, str]


class Pattern(Frozen):
    key: str
    value: str
    sessions: int
    confidence: Literal["medium", "high"]
    last: date


def _fresh(f) -> bool:
    """Said or chosen in this session, not a stored pattern the user only kept."""
    return f.source == "user" and not any((e.tool or "").startswith("chip:prior") for e in f.evidence)


def votes_from_state(state: TripState) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in VOTE_SCALARS:
        f = getattr(state, name)
        if f.known and _fresh(f):
            out[name] = _ballot(f.value)
    for key, f in state.soft.items():
        if f.value in ("love", "avoid") and _fresh(f):
            out[f"soft:{key}"] = f.value
    offered = set(state.meta.prior)
    for a in state.anchors:
        if a.state == "matched" and a.place_id and f"place:{a.place_id}" not in offered:
            out[f"place:{a.place_id}"] = "love"
    return out


def _ballot(value) -> str:
    if isinstance(value, Base):
        return json.dumps({k: v for k, v in value.model_dump().items() if k in ("text", "lat", "lng", "province") and v is not None},
                          ensure_ascii=False, sort_keys=True)
    return str(value)


def _prior(key: str, raw: str, catalog: Catalog):
    """The value of a stored vote, as the state field takes it."""
    return Base(**json.loads(raw)) if key == "origin" else values.parse(key, raw, catalog)


def detect(history: list[Summary], cfg: PatternSettings, today: date) -> list[Pattern]:
    """A key becomes a pattern when its latest votes agree: the same choice in at least min_sessions distinct
    sessions, at least `agreement` of the window, and the most recent vote is still that choice."""
    by_key: dict[str, list[tuple[date, str]]] = {}
    for s in sorted(history, key=lambda s: (s.day, s.sid)):
        for key, value in s.votes.items():
            by_key.setdefault(key, []).append((s.day, value))
    found = []
    for key, votes in by_key.items():
        votes = votes[-cfg.window:]
        last_day, last_value = votes[-1]
        if (today - last_day).days > cfg.stale_days:
            continue
        n = Counter(v for _, v in votes)[last_value]
        if n >= cfg.min_sessions and n / len(votes) >= cfg.agreement:
            found.append(Pattern(key=key, value=last_value, sessions=n, last=last_day,
                                 confidence="high" if n >= 2 * cfg.min_sessions else "medium"))
    return sorted(found, key=lambda p: (-p.sessions, p.key))


def seed(state: TripState, found: list[Pattern], catalog: Catalog, cfg: PatternSettings) -> TripState:
    """Patterns become priors: source "profile", shown with ✎, and replaced by anything the current trip says.
    meta.prior lists what was put in the state or offered, for the one-touch confirm card."""
    keys: list[str] = []
    places = 0
    for p in found:
        ev = Evidence(turn=0, tool=f"profile:{p.key}")
        try:
            if p.key in VOTE_SCALARS:
                state = apply(state, Update(field=p.key, value=_prior(p.key, p.value, catalog), source="profile",
                                            confidence=p.confidence, evidence=ev))
            elif p.key.startswith("soft:"):
                state = apply(state, Update(field="soft", op="add", value=(p.key[5:], p.value), source="profile",
                                            confidence=p.confidence, evidence=ev))
            elif p.key.startswith("place:") and p.value == "love" and p.key[6:] in catalog.by_id \
                    and places < cfg.max_places:
                places += 1  # offered on the card only: a stored place is never put in the trip unasked
            else:
                continue
        except (ValueError, TypeError, ValidationError):  # a value the ontology (or a field) no longer knows
            continue
        keys.append(p.key)
    return with_meta(state, prior=tuple(keys))


def seed_profile(state: TripState, profile: dict) -> TripState:
    """Account profile fields (docs/ACCOUNTS.md) as priors: source "profile", replaced by anything this trip says.
    Only values Trip knows are used; anything else in the profile is ignored."""
    ev = Evidence(turn=0, tool="profile:account")
    for field, value, op in (("mobility", profile.get("usual_mobility"), "set"),
                             ("companions", profile.get("usual_companions"), "add")):
        if not value:
            continue
        try:
            state = apply(state, Update(field=field, op=op, value=value, source="profile", confidence="medium",
                                        evidence=ev))
        except (ValueError, ValidationError):
            continue
    return state
