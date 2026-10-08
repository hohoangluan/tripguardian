"""Checks an agent TurnPlan before it touches the session (docs/PLACE_DECISION.md §18): quotes come from the message, aliases are on
screen, values are in the allowed sets; `say` holds no number or place name the user and the screen do not hold."""

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict

from trip import contains, squash

Op = Literal["select", "drop", "lock", "travel", "crowd", "price", "trip", "visited"]
FEEDBACK = {"travel": "far", "crowd": "crowded", "price": "pricey"}
REASONS = ("far", "crowded", "pricey", "dislike", "visited")
PLACE_OPS = {"select", "lock", "drop", "visited"}


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PlanUpdate(Frozen):
    op: Op
    place: str
    value: str
    quote: str


class TurnPlan(Frozen):
    say: str
    updates: tuple[PlanUpdate, ...] = ()


@dataclass
class Guarded:
    actions: list[dict]
    say: str
    log: list[str] = field(default_factory=list)


def names_in(text: str, name: str) -> bool:
    """The user named this place: its whole name, or its last two words (the distinctive part of most names)."""
    words = squash(name).split()
    return contains(text, name) or (len(words) >= 2 and contains(text, " ".join(words[-2:])))


def _named(quote: str, name: str, name_keys) -> bool:
    """The quote names this place: the whole name, or its last two words when no other place ends the same way."""
    if contains(quote, name):
        return True
    words = squash(name).split()
    if len(words) < 2 or not contains(quote, " ".join(words[-2:])):
        return False
    tail = " ".join(words[-2:])
    return sum(1 for k, _ in name_keys if k == tail or k.endswith(" " + tail)) <= 1


def guard(plan: TurnPlan, text: str, aliases: dict[str, dict], screen_text: str,
          name_keys: list[tuple[str, str]]) -> Guarded:
    """aliases: "P1" -> {"id", "name", ...}; screen_text: what the user sees (its numbers may be repeated);
    name_keys: (squashed name, id) of every place whose name is long enough to recognise in text."""
    log, actions = [], []
    for u in plan.updates:
        if not contains(text, u.quote):
            log.append(f"drop {u.op}: quote {u.quote!r} not in the message")
            continue
        place = aliases.get(u.place) if u.place else None
        if u.place and place is None:
            log.append(f"drop {u.op}: unknown alias {u.place!r}")
            continue
        if u.op in PLACE_OPS and place is None:
            log.append(f"drop {u.op}: needs a place")
            continue
        if u.op in ("select", "lock") and not _named(u.quote, place["name"], name_keys):
            log.append(f"drop {u.op}: the user did not name {place['name']!r}")
            continue
        if u.op in ("select", "lock"):
            actions.append({"type": u.op, "place_id": place["id"]})
        elif u.op == "drop":
            actions.append({"type": "drop", "place_id": place["id"], "reason": u.value if u.value in REASONS else None})
        elif u.op == "visited":
            actions.append({"type": "drop", "place_id": place["id"], "reason": "visited"})
        elif u.op in FEEDBACK:
            actions.append({"type": "feedback", "reason": FEEDBACK[u.op]})
        elif u.op == "trip":
            actions.append({"type": "trip", "text": u.quote.strip()})
    say = plan.say.strip()
    why = _bad_say(say, f"{text} {screen_text}", aliases, name_keys)
    if why:
        log.append(f"say replaced: {why}")
        say = ""
    return Guarded(actions, say, log)


def _bad_say(say: str, heard: str, aliases: dict[str, dict], name_keys) -> str | None:
    said = set(re.findall(r"\d+", heard))
    extra = [n for n in re.findall(r"\d+", say) if n not in said]
    if extra:
        return f"numbers {extra} not said or shown"
    shown = {a["id"] for a in aliases.values()}
    s = f" {squash(say)} "
    for key, pid in name_keys:
        if pid not in shown and f" {key} " in s:
            return f"names place {pid}"
    return None
