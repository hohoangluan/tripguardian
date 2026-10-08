"""Checks an agent TurnPlan before it touches the Trip State (docs/TRIP_UNDERSTANDING.md §4)."""

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import ValidationError

from . import values
from ..infrastructure.catalog import Catalog
from ..infrastructure.settings import Settings
from .policy import askable, next_question
from .questions import READY, Chip, Question, clarify_q, prior_q, required
from .state import SCALARS, Evidence, Frozen, TripState, Update, apply, settle
from .text import contains, squash

FieldName = Literal["start_date", "month", "days", "companions", "people", "base", "entry_point", "exit_point", "mobility",
                    "arrive_at", "leave_at", "day_end", "purpose", "anchor", "signal", "soft", "hard", "pace", "max_leg_min", "crowd_tolerance",
                    "novelty", "budget_vnd", "unmapped"]
LIST_FIELDS = {"companions", "anchor", "signal", "soft", "hard", "unmapped"}


class PlanUpdate(Frozen):
    field: FieldName
    op: Literal["set", "add", "remove"]
    value: str
    quote: str
    how: Literal["said", "inferred"]


class PlanNext(Frozen):
    kind: Literal["ask", "stop"]
    qid: str = ""
    custom_text: str = ""
    custom_chips: tuple[str, ...] = ()
    reason: str = ""


class TurnPlan(Frozen):
    say: str
    updates: tuple[PlanUpdate, ...] = ()
    next: PlanNext


@dataclass
class Guarded:
    state: TripState
    question: Question
    say: str
    log: list[str] = field(default_factory=list)


def guard(plan: TurnPlan, state: TripState, text: str, turn: int, catalog: Catalog, cfg: Settings,
          heard: str, compared: list[dict] | None = None) -> Guarded:
    """text: this turn's message (quotes must come from it); heard: every user message so far (numbers allowed in say);
    compared: places this message compares the trip to, with their traits (trip.domain.traits)."""
    log: list[str] = []
    for u in plan.updates:
        if not contains(text, u.quote):
            log.append(f"drop {u.field}={u.value!r}: quote {u.quote!r} not in the message")
            continue
        named = [c for c in compared or () if contains(u.quote, c["name"])] \
            if u.field == "soft" and u.how == "inferred" else []
        if named:
            key = values.split_weight(u.value)[0].replace(" ", "")
            if key not in {f"{t['feature']}={t['value']}" for c in named for t in c["traits"]}:
                log.append(f"drop soft={u.value!r}: not a trait of {named[0]['name']!r}")
                continue
        # a taste read from a place the user compared to remembers that place: the ticket says "(giống X)"
        ev = Evidence(turn=turn, quote=u.quote, tool=f"place:{named[0]['id']}" if named else None)
        said = u.how == "said"
        op = u.op if u.field in LIST_FIELDS else ("remove" if u.op == "remove" else "set")
        try:
            if op == "remove":
                value = None if u.field in SCALARS else values.parse_remove(u.field, u.value)
            else:
                value = values.parse(u.field, u.value, catalog)
            state = apply(state, Update(field=u.field, op=op, value=value, source="user" if said else "inferred",
                                        confidence="high" if said else "medium", evidence=ev))
        except (ValueError, ValidationError) as e:
            if u.field in ("soft", "hard") and op != "remove":
                state = apply(state, Update(field="unmapped", op="add", value=u.quote, source="user",
                                            confidence="high", evidence=ev))
                log.append(f"unmapped {u.field}={u.value!r}: {str(e).splitlines()[0]}")
            else:
                log.append(f"drop {u.field}={u.value!r}: {str(e).splitlines()[0]}")
    state = settle(state)
    question = _question(plan.next, state, turn, catalog, cfg, log)
    say = plan.say.strip()
    if question.custom is False and plan.next.qid != question.qid:
        say = drop_questions(say)  # the card asks something else: keep the acknowledgement
    why = _bad_say(say, heard, state, catalog, {c["id"] for c in compared or ()})
    if why:
        log.append(f"say replaced: {why}")
        say = ""
    return Guarded(state, question, say, log)


def drop_questions(say: str) -> str:
    """The sentences of `say` that are not questions."""
    return " ".join(x for x in re.split(r"(?<=[.!?…])\s+", say) if not x.rstrip().endswith("?")).strip()


def _question(nx: PlanNext, state: TripState, turn: int, catalog: Catalog, cfg: Settings, log: list[str]) -> Question:
    req = required(state, catalog, cfg)
    if req:
        if nx.qid != req.qid:
            log.append(f"forced tier-1 {req.qid} over {nx.qid or nx.custom_text or nx.kind!r}")
        return req
    if nx.kind == "stop" or state.meta.adaptive_turns >= cfg.turn_budget or state.meta.idle_streak >= cfg.idle_limit:
        return READY
    if q := prior_q(state, catalog):
        if nx.qid != q.qid:
            log.append(f"stored tastes first: prior over {nx.qid or nx.custom_text or nx.kind!r}")
        return q
    if nx.custom_text.strip() and (q := clarify_q(state)):
        log.append(f"custom question dropped: {q.qid} is already waiting")     # the rules ask what a word means, once
        return q
    if nx.custom_text.strip():
        chips = [c.strip() for c in nx.custom_chips if c.strip()]
        if 2 <= len(chips) <= 6 and all(len(c) <= 40 for c in chips):
            return Question(qid=f"custom:{turn}", group="I", tier=2, custom=True, multi=True,
                            text=nx.custom_text.strip(), reason=nx.reason.strip(),
                            chips=tuple(Chip(id=f"c{i}", label=c) for i, c in enumerate(chips)))
        log.append(f"custom question rejected: {len(chips)} chips")
    elif nx.qid:
        q = askable(state, catalog, cfg).get(nx.qid)
        if q:
            return q
        log.append(f"unknown qid {nx.qid!r}")
    return next_question(state, catalog, cfg)


def _bad_say(say: str, heard: str, state: TripState, catalog: Catalog, compared: set[str]) -> str | None:
    said = set(re.findall(r"\d+", heard))
    extra = [n for n in re.findall(r"\d+", say) if n not in said]
    if extra:
        return f"numbers {extra} the user did not say"
    named = {a.place_id for a in state.anchors if a.place_id} | compared  # the user named these
    s = f" {squash(say)} "
    for key, pid in catalog.name_keys:
        if pid not in named and f" {key} " in s:
            return f"names place {pid}"
    return None
