"""Trip State and Search Input (docs/TRIP_UNDERSTANDING.md §17).

Every value carries where it came from. apply() is the only way a state changes; settle() closes physical signals that
a hard filter already answers.
"""

from __future__ import annotations

import functools
import re
from datetime import date
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, model_validator

from corpus.ontology import Ontology, load as load_ontology

T = TypeVar("T")
Source = Literal["user", "anchor", "profile", "inferred", "default"]
Confidence = Literal["high", "medium", "low"]
Status = Literal["unknown", "asked", "confirmed", "skipped"]
Who = Literal["solo", "partner", "friends", "kids", "parents"]
Vehicle = Literal["motorbike", "car", "ride"]
Purpose = Literal["relax", "bond", "photo", "food_culture", "nature", "explore", "adventure"]
Pace = Literal["slow", "normal", "packed"]
Novelty = Literal["familiar", "new", "mix"]
Crowd = Literal["avoid", "ok_if_worth", "fine"]
Weight = Literal["love", "avoid", "off"]
SignalKind = Literal["knee", "elderly", "kids", "wheelchair", "pregnant", "motion_sick", "height", "vegetarian"]

EFFORT_SIGNALS = frozenset({"knee", "elderly", "kids", "wheelchair", "pregnant"})  # answered by question c_effort
OTHER_SIGNALS = frozenset({"motion_sick", "height", "vegetarian"})  # answered by question c_other
EFFORT_FEATURES = frozenset({"steep_or_stairs", "long_walk"})
SCALARS = ("start_date", "month", "days", "people", "base", "mobility", "arrive_at", "leave_at", "day_end", "purpose",
           "pace", "max_leg_min", "crowd_tolerance", "novelty", "budget_vnd")
RANGES = {"month": (1, 12), "days": (1, 7), "people": (1, 20), "max_leg_min": (5, 180),
          "budget_vnd": (10_000, 50_000_000)}
CLOCKS = ("arrive_at", "leave_at", "day_end")
CLOCK = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
WEIGHT_SIGN = {"love": 1, "avoid": -1, "off": 0}


@functools.cache
def ontology() -> Ontology:
    return load_ontology()


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Evidence(Frozen):
    turn: int
    quote: str | None = None
    tool: str | None = None

    @model_validator(mode="after")
    def _has_origin(self):
        if not (self.quote or self.tool):
            raise ValueError("evidence needs a quote or a tool")
        return self


class Field(Frozen, Generic[T]):
    value: T | None = None
    source: Source = "default"
    confidence: Confidence = "low"
    status: Status = "unknown"
    evidence: tuple[Evidence, ...] = ()

    @model_validator(mode="after")
    def _evidenced(self):
        if self.value is not None and self.source != "default" and not self.evidence:
            raise ValueError("a value that is not a default needs evidence")
        return self

    @property
    def known(self) -> bool:
        return self.value is not None

    @property
    def locked(self) -> bool:
        """Said or chosen by the user: only the user changes it."""
        return self.source == "user" and self.status == "confirmed"


class SoftKey(Frozen):
    feature: str
    value: str
    context: tuple[tuple[str, str], ...] = ()

    @model_validator(mode="after")
    def _in_ontology(self):
        o = ontology()
        if not o.valid(self.feature, self.value):
            raise ValueError(f"{self.feature}={self.value} is not in ontology v{o.version}")
        for k, v in self.context:
            if v == "unknown" or not o.valid_context(k, v):
                raise ValueError(f"context {k}={v} is not in ontology v{o.version}")
        return self

    def __str__(self) -> str:
        return f"{self.feature}={self.value}" + "".join(f"@{k}.{v}" for k, v in self.context)

    @classmethod
    def parse(cls, text: str) -> SoftKey:
        """'crowd=low@day_type.weekend' -> SoftKey; ValueError when malformed or not in the ontology."""
        head, *ctx = text.strip().split("@")
        feature, eq, value = head.partition("=")
        if not eq:
            raise ValueError(f"soft key {text!r} needs feature=value")
        pairs = []
        for c in ctx:
            k, dot, v = c.partition(".")
            if not dot:
                raise ValueError(f"context {c!r} needs key.value")
            pairs.append((k.strip(), v.strip()))
        return cls(feature=feature.strip(), value=value.strip(), context=tuple(sorted(pairs)))


class Hard(Frozen):
    feature: str
    op: Literal["ne", "eq"]
    value: str
    unknown_policy: Literal["exclude", "flag"] | None = None
    evidence: tuple[Evidence, ...]

    @model_validator(mode="after")
    def _valid(self):
        if not ontology().valid(self.feature, self.value):
            raise ValueError(f"hard filter {self.feature}={self.value} is not in the ontology")
        if not self.evidence:
            raise ValueError("a hard filter needs evidence")
        return self


class Base(Frozen):
    place_id: str | None = None
    text: str


class Anchor(Frozen):
    text: str
    place_id: str | None = None
    state: Literal["matched", "choose", "missing"]
    candidates: tuple[str, ...] = ()
    priority: Literal["must", "want"] = "must"


class Signal(Frozen):
    kind: SignalKind
    quote: str
    turn: int
    handled: bool = False


class Unmapped(Frozen):
    phrase: str
    turn: int


class Ambiguous(Frozen):
    phrase: str
    keys: tuple[str, ...]
    turn: int


class Meta(Frozen):
    experience: Literal["first", "returning"] | None = None
    start_with: Literal["nothing", "saved", "must", "itinerary"] | None = None
    turn: int = 0
    adaptive_turns: int = 0
    asked: tuple[str, ...] = ()
    skipped: frozenset[str] = frozenset()
    unsure_streak: int = 0
    pending: tuple[Ambiguous, ...] = ()  # subjective words still to clarify


class TripState(Frozen):
    start_date: Field[date] = Field[date]()
    month: Field[int] = Field[int]()
    days: Field[int] = Field[int]()
    companions: Field[frozenset[Who]] = Field[frozenset[Who]]()
    people: Field[int] = Field[int]()
    base: Field[Base] = Field[Base]()
    mobility: Field[Vehicle] = Field[Vehicle]()
    arrive_at: Field[str] = Field[str]()
    leave_at: Field[str] = Field[str]()
    day_end: Field[str] = Field[str]()
    purpose: Field[Purpose] = Field[Purpose]()
    pace: Field[Pace] = Field[Pace]()
    max_leg_min: Field[int] = Field[int]()
    crowd_tolerance: Field[Crowd] = Field[Crowd]()
    novelty: Field[Novelty] = Field[Novelty]()
    budget_vnd: Field[int] = Field[int]()
    anchors: tuple[Anchor, ...] = ()
    signals: tuple[Signal, ...] = ()
    hard: tuple[Hard, ...] = ()
    soft: dict[str, Field[Weight]] = {}
    visited: tuple[str, ...] = ()
    unmapped: tuple[Unmapped, ...] = ()
    meta: Meta = Meta()


class Draft(Frozen):
    """An update without its evidence yet: what a chip writes when chosen."""
    field: str
    op: Literal["set", "add", "remove"] = "set"
    value: Any = None
    inferred: bool = False


class Update(Frozen):
    field: str
    op: Literal["set", "add", "remove"] = "set"
    value: Any = None
    source: Source
    confidence: Confidence
    evidence: Evidence


def with_meta(state: TripState, **changes) -> TripState:
    return state.model_copy(update={"meta": state.meta.model_copy(update=changes)})


def _kind(field: str):
    return TripState.model_fields[field].annotation


def apply(state: TripState, u: Update) -> TripState:
    """One validated change. Raises ValueError (pydantic ValidationError included) when the value does not fit."""
    status = "confirmed" if u.source == "user" and u.confidence == "high" else "unknown"
    f = u.field
    if f in SCALARS:
        cur = getattr(state, f)
        if cur.locked and u.source != "user":
            return state
        if u.op == "remove":
            return state.model_copy(update={f: _kind(f)(status="skipped" if u.source == "user" else "unknown")})
        if f in RANGES and not RANGES[f][0] <= int(u.value) <= RANGES[f][1]:
            raise ValueError(f"{f}={u.value} is out of range {RANGES[f]}")
        if f in CLOCKS and not CLOCK.fullmatch(str(u.value)):
            raise ValueError(f"{f}={u.value} is not HH:MM")
        new = _kind(f)(value=u.value, source=u.source, confidence=u.confidence, status=status, evidence=(u.evidence,))
        return state.model_copy(update={f: new})
    if f == "companions":
        cur = state.companions
        if cur.locked and u.source != "user":
            return state
        have = cur.value or frozenset()
        vals = frozenset(u.value) if isinstance(u.value, (list, tuple, set, frozenset)) else frozenset({u.value})
        if u.op == "set":
            new_set = vals
        elif u.op == "add":
            new_set = have | vals
        else:
            new_set = have - vals
        new = _kind(f)(value=new_set or None, source=u.source, confidence=u.confidence, status=status,
                       evidence=cur.evidence + (u.evidence,))
        return state.model_copy(update={f: new})
    if f == "soft":
        if u.op == "remove":
            key = str(SoftKey.parse(u.value))
            cur = state.soft.get(key)
            if cur is None or (cur.locked and u.source != "user"):
                return state
            return state.model_copy(update={"soft": {k: v for k, v in state.soft.items() if k != key}})
        raw_key, weight = u.value
        key = str(SoftKey.parse(raw_key))
        cur = state.soft.get(key)
        if cur is not None and cur.locked and u.source != "user":
            return state
        new = Field[Weight](value=weight, source=u.source, confidence=u.confidence, status=status, evidence=(u.evidence,))
        return state.model_copy(update={"soft": {**state.soft, key: new}})
    if f == "hard":
        if u.op == "remove":
            return state.model_copy(update={"hard": tuple(h for h in state.hard if h.feature != u.value)})
        v = dict(u.value)
        h = Hard(feature=v["feature"], op=v["op"], value=v["value"], unknown_policy=v.get("unknown_policy"),
                 evidence=(u.evidence,))
        old = next((x for x in state.hard if (x.feature, x.op, x.value) == (h.feature, h.op, h.value)), None)
        if old is not None:
            h = h.model_copy(update={"unknown_policy": old.unknown_policy or h.unknown_policy,
                                     "evidence": old.evidence + h.evidence})
        return state.model_copy(update={"hard": tuple(x for x in state.hard if x is not old) + (h,)})
    if f == "hard_policy":
        feature, policy = u.value
        if policy not in ("exclude", "flag"):
            raise ValueError(f"unknown_policy {policy!r}")
        return state.model_copy(update={"hard": tuple(
            h.model_copy(update={"unknown_policy": policy}) if h.feature == feature else h for h in state.hard)})
    if f == "anchor":
        if u.op == "remove":
            i = int(u.value)
            return state.model_copy(update={"anchors": state.anchors[:i] + state.anchors[i + 1:]})
        a = u.value if isinstance(u.value, Anchor) else Anchor.model_validate(u.value)
        if any(x.text == a.text or (a.place_id and x.place_id == a.place_id) for x in state.anchors):
            return state
        return state.model_copy(update={"anchors": state.anchors + (a,)})
    if f in ("anchor_pick", "anchor_priority"):
        i, v = u.value
        a = state.anchors[int(i)]
        if f == "anchor_pick":
            a = a.model_copy(update={"place_id": v, "state": "matched" if v else "missing"})
        elif v in ("must", "want"):
            a = a.model_copy(update={"priority": v})
        else:
            raise ValueError(f"priority {v!r}")
        anchors = list(state.anchors)
        anchors[int(i)] = a
        return state.model_copy(update={"anchors": tuple(anchors)})
    if f == "signal":
        kind = u.value["kind"] if isinstance(u.value, dict) else u.value
        if u.op == "remove":
            return state.model_copy(update={"signals": tuple(s for s in state.signals if s.kind != kind)})
        if any(s.kind == kind for s in state.signals):
            return state
        s = Signal(kind=kind, quote=u.evidence.quote or u.evidence.tool or "", turn=u.evidence.turn)
        return state.model_copy(update={"signals": state.signals + (s,)})
    if f == "signal_handled":
        kinds = set(u.value)
        return state.model_copy(update={"signals": tuple(
            s.model_copy(update={"handled": True}) if s.kind in kinds else s for s in state.signals)})
    if f == "unmapped":
        if u.op == "remove":
            i = int(u.value)
            return state.model_copy(update={"unmapped": state.unmapped[:i] + state.unmapped[i + 1:]})
        phrase = str(u.value).strip()
        if not phrase or any(x.phrase.casefold() == phrase.casefold() for x in state.unmapped):
            return state
        return state.model_copy(update={"unmapped": state.unmapped + (Unmapped(phrase=phrase, turn=u.evidence.turn),)})
    if f == "visited":
        return state if u.value in state.visited else state.model_copy(update={"visited": state.visited + (u.value,)})
    if f == "pending":
        if u.op == "remove":
            return with_meta(state, pending=tuple(a for a in state.meta.pending if a.phrase != u.value))
        a = Ambiguous(phrase=u.value["phrase"], keys=tuple(u.value["keys"]), turn=u.evidence.turn)
        if any(x.phrase == a.phrase for x in state.meta.pending):
            return state
        return with_meta(state, pending=state.meta.pending + (a,))
    raise ValueError(f"unknown field {f!r}")


def settle(state: TripState) -> TripState:
    """Physical signals count as handled once a hard filter answers them."""
    feats = {h.feature for h in state.hard}
    done: set[str] = set()
    if feats & EFFORT_FEATURES:
        done |= EFFORT_SIGNALS
    if "vegetarian_options" in feats:
        done.add("vegetarian")
    if not any(s.kind in done and not s.handled for s in state.signals):
        return state
    return state.model_copy(update={"signals": tuple(
        s.model_copy(update={"handled": True}) if s.kind in done else s for s in state.signals)})


def apply_drafts(state: TripState, drafts, turn: int, tool: str, quote: str | None = None) -> TripState:
    for d in drafts:
        state = apply(state, Update(field=d.field, op=d.op, value=d.value,
                                    source="inferred" if d.inferred else "user",
                                    confidence="medium" if d.inferred else "high",
                                    evidence=Evidence(turn=turn, quote=quote, tool=tool)))
    return settle(state)


def pending_signals(state: TripState) -> list[Signal]:
    return [s for s in state.signals if not s.handled]


def unknown_fields(state: TripState) -> list[str]:
    out = [] if state.start_date.known or state.month.known else ["dates"]
    return out + [f for f in ("days", "companions", "base", "mobility", "purpose", "pace", "budget_vnd")
                  if not getattr(state, f).known]


# ---------- Search Input (output of this step, input of Place Decision) ----------

class Context(Frozen):
    start_date: date | None
    month: int | None
    days: int | None
    base: Base | None
    mobility: Vehicle | None
    companions: tuple[Who, ...]
    people: int | None
    arrive_at: str | None
    leave_at: str | None
    day_end: str | None
    budget_vnd: int | None = None
    experience: Literal["first", "returning"] | None = None


class HardFilter(Frozen):
    feature: str
    op: Literal["ne", "eq"]
    value: str
    unknown_policy: Literal["exclude", "flag"]


class AnchorRef(Frozen):
    place_id: str
    priority: Literal["must", "want"]


class SoftWeight(Frozen):
    feature: str
    value: str
    context: dict[str, str] | None
    weight: Literal[1, -1, 0]
    source: Source


class PaceSpec(Frozen):
    level: Pace | None
    max_leg_min: int | None
    crowd_tolerance: Crowd | None


class NoveltySpec(Frozen):
    level: Novelty | None
    visited: tuple[str, ...]


class SearchInput(Frozen):
    ontology_version: int
    context: Context
    hard_filters: tuple[HardFilter, ...]
    anchors: tuple[AnchorRef, ...]
    soft_weights: tuple[SoftWeight, ...]
    pace: PaceSpec
    novelty: NoveltySpec
    unknowns: tuple[str, ...]
    unmapped: tuple[str, ...]
