"""Checks an agent TurnPlan before it reaches Engine.act (docs/PLANNING.md §Vòng người dùng sửa và góp
ý): quotes come from the message, aliases are on screen, a risky pick (lodging, variant) is named by the user.
Mirrors src/decision/guard.py in shape, not in import -- planning may not import decision (RULE.md §2)."""

import re
from dataclasses import dataclass, field
from functools import cache
from typing import Literal

from pydantic import BaseModel, ConfigDict

from corpus.ontology import load
from trip import contains, squash

Op = Literal["drop", "move_day", "reorder_edge", "pick_lodging", "lodging_near", "pace", "relax", "variant",
            "unmapped"]
PLACE_OPS = {"drop", "move_day", "reorder_edge", "relax"}
NAMED_OPS = {"pick_lodging", "variant", "relax"}         # risky picks: the quote must name the target
REASONS = ("far", "crowded", "pricey", "dislike", "visited")
PACES = ("slow", "normal", "packed")
_NUM = re.compile(r"\d+")


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PlanUpdate(Frozen):
    op: Op
    ref: str
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


@cache
def _ontology():
    return load()


def names_in(text: str, name: str) -> bool:
    """The user named this place: its whole name, or its last two words (the distinctive part of most names)."""
    words = squash(name).split()
    return contains(text, name) or (len(words) >= 2 and contains(text, " ".join(words[-2:])))


def _label(ref: dict) -> str:
    """What the user has to say to name an alias: a place's or lodging candidate's name, a variant's label."""
    return ref.get("name") or ref.get("label", "")


def _reorder_edge(ref: dict, value: str, day_order: dict) -> dict | None:
    order = list(day_order.get(ref["day"], []))
    if ref["id"] not in order:
        return None
    rest = [i for i in order if i != ref["id"]]
    new = [ref["id"], *rest] if value == "first" else [*rest, ref["id"]] if value == "last" else None
    return {"type": "reorder", "day": ref["day"], "order": new} if new else None


def guard(plan: TurnPlan, text: str, aliases: dict[str, dict], day_order: dict[int, list[str]],
         screen_text: str) -> Guarded:
    log, actions = [], []
    for u in plan.updates:
        if not contains(text, u.quote):
            log.append(f"drop {u.op}: quote {u.quote!r} not in the message")
            continue
        ref = aliases.get(u.ref) if u.ref else None
        if u.ref and ref is None:
            log.append(f"drop {u.op}: unknown alias {u.ref!r}")
            continue
        if u.op in PLACE_OPS and (ref is None or ref["kind"] != "place"):
            log.append(f"drop {u.op}: needs a place")
            continue
        if u.op in NAMED_OPS and ref is not None and not names_in(u.quote, _label(ref)):
            log.append(f"drop {u.op}: the user did not name {_label(ref)!r}")
            continue
        if u.op == "drop":
            reason = u.value if u.value in REASONS else None
            actions.append({"type": "drop_place", "place": ref["id"], "reason": reason})
        elif u.op == "move_day":
            try:
                day = int(u.value.strip()) - 1
            except ValueError:
                log.append(f"drop move_day: bad day {u.value!r}")
                continue
            actions.append({"type": "move_place", "place": ref["id"], "day": day})
        elif u.op == "reorder_edge":
            act = _reorder_edge(ref, u.value, day_order)
            if act is None:
                log.append(f"drop reorder_edge: {u.value!r} on {ref['id']!r} has no order to build")
                continue
            actions.append(act)
        elif u.op == "pick_lodging":
            if ref is None or ref["kind"] != "lodging":
                log.append("drop pick_lodging: needs a lodging candidate")
                continue
            actions.append({"type": "pick_lodging", "id": ref["id"]})
        elif u.op == "lodging_near":
            if not u.value.strip():
                log.append("drop lodging_near: empty area")
                continue
            actions.append({"type": "set_lodging", "text": u.value.strip()})
        elif u.op == "pace":
            if u.value not in PACES:
                log.append(f"drop pace: unknown level {u.value!r}")
                continue
            actions.append({"type": "set_pace", "level": u.value})
        elif u.op == "relax":
            if u.value not in _ontology().features:
                log.append(f"drop relax: unknown feature {u.value!r}")
                continue
            actions.append({"type": "relax", "place_id": ref["id"], "feature": u.value})
        elif u.op == "variant":
            if ref is None or ref["kind"] != "variant":
                log.append("drop variant: needs a plan option")
                continue
            actions.append({"type": "pick_variant", "id": ref["id"]})
        elif u.op == "unmapped" and u.value.strip():
            log.append(f"note: {u.value.strip()}")
    say = plan.say.strip()
    why = _bad_say(say, f"{text} {screen_text}")
    if why:
        log.append(f"say replaced: {why}")
        say = ""
    return Guarded(actions, say, log)


def _bad_say(say: str, heard: str) -> str | None:
    """Unlike Decision's own `_bad_say`, there is no name check here: every alias `guard` is ever given is built from
    the session's own current Schedule and lodging candidates, so a `say` naming a place is never by itself a
    hallucination -- only a number nobody said or showed is (a minute count, a price, a day number invented instead
    of read off screen)."""
    said = set(_NUM.findall(heard))
    extra = [n for n in _NUM.findall(say) if n not in said]
    return f"numbers {extra} not said or shown" if extra else None
