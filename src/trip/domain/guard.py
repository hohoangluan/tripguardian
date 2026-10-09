"""Evidence checks between the agent and the Trip State (docs/TRIP_UNDERSTANDING.md §4).

The agent proposes; nothing is written unless the quote is the user's own words and the value parses. A refusal is
returned as text so the agent can correct itself in the same turn.
"""

import re
from typing import Literal

from pydantic import ValidationError

from . import values
from ..infrastructure.catalog import Catalog
from .state import SCALARS, Evidence, TripState, Update, apply, settle
from .text import contains, squash

FieldName = Literal["start_date", "month", "month_part", "days", "companions", "people", "base", "entry_point", "exit_point", "mobility",
                    "arrive_at", "leave_at", "day_end", "purpose", "anchor", "signal", "soft", "hard", "pace", "max_leg_min", "crowd_tolerance",
                    "novelty", "budget_vnd", "budget_scope", "liked_groups", "unmapped"]
GENERIC = {"du", "lich", "da", "lat", "dalat", "viet", "nam", "thanh", "pho", "tour"}  # a place name made only of these is a phrase
LIST_FIELDS = {"companions", "liked_groups", "anchor", "signal", "soft", "hard", "unmapped"}


def record_fact(state: TripState, field: str, op: str, value: str, quote: str, how: str, text: str, turn: int,
                catalog: Catalog, compared: list[dict] | None = None) -> tuple[TripState, str]:
    """-> (state, note). note is "" when the fact was written, else why it was refused (the agent reads it and corrects).
    text: this turn's message (the quote must come from it); compared: places the message compares the trip to,
    with their traits (trip.domain.traits)."""
    if not contains(text, quote):
        return state, f"refused: quote {quote!r} is not in the user's message; copy the user's exact words"
    named = [c for c in compared or () if contains(quote, c["name"])] if field == "soft" and how == "inferred" else []
    if named:
        key = values.split_weight(value)[0].replace(" ", "")
        if key not in {f"{t['feature']}={t['value']}" for c in named for t in c["traits"]}:
            return state, f"refused: {value!r} is not a trait of {named[0]['name']!r}"
    # a taste read from a place the user compared to remembers that place: the ticket says "(giống X)"
    ev = Evidence(turn=turn, quote=quote, tool=f"place:{named[0]['id']}" if named else None)
    said = how == "said"
    op = op if field in LIST_FIELDS else ("remove" if op == "remove" else "set")
    try:
        if op == "remove":
            parsed = None if field in SCALARS else values.parse_remove(field, value)
        else:
            parsed = values.parse(field, value, catalog)
        state = apply(state, Update(field=field, op=op, value=parsed, source="user" if said else "inferred",
                                    confidence="high" if said else "medium", evidence=ev))
    except (ValueError, ValidationError) as e:
        hint = " (soft: feature=value:love|avoid with ids from FEATURES; if none fits, use field unmapped)" \
            if field in ("soft", "hard") else ""
        return state, f"refused: {value!r} is not a valid {field}: {str(e).splitlines()[0]}{hint}"
    return settle(state), ""


def drop_questions(say: str) -> str:
    """The sentences of `say` that are not questions."""
    return " ".join(x for x in re.split(r"(?<=[.!?…])\s+", say) if not x.rstrip().endswith("?")).strip()


def split_lead(text: str) -> tuple[str, str]:
    """A card's text is only the question: -> (lead, question). Whatever the agent wrote before the first question
    sentence (a comment, an answer to what the user asked) is the lead and goes to the chat, not the card title."""
    parts = re.split(r"(?<=[.!?…])\s+", text.strip())
    i = next((k for k, x in enumerate(parts) if x.rstrip().endswith("?")), 0)
    return " ".join(parts[:i]), " ".join(parts[i:]) or text.strip()


def bad_say(say: str, heard: str, state: TripState, catalog: Catalog, compared: set[str]) -> str | None:
    """Why `say` may not be shown: a number the user never said, or a place the user never named."""
    said = set(re.findall(r"\d+", heard))
    extra = [n for n in re.findall(r"\d+", say) if n not in said]
    if extra:
        return f"numbers {extra} the user did not say"
    named = {a.place_id for a in state.anchors if a.place_id} | compared  # the user named these
    s = f" {squash(say)} "
    for key, pid in catalog.name_keys:
        if pid not in named and not set(key.split()) <= GENERIC and f" {key} " in s:
            return f"names place {pid}"
    return None
