# Trip Understanding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A conversational Trip Understanding step: the user talks / taps chips, the system keeps a sourced Trip State, asks only questions that matter, and hands a typed `SearchInput` to the existing Shortlist.

**Architecture:** New Python package `src/trip/` (read-only over `data/intel`), one Gemma call per free-text turn streamed over SSE, deterministic prepass + policy for chips, edits and fallback; a guard validates every agent output before it touches state. Web replaces Setup + Discover with one chat + understanding-panel screen; an adapter maps `SearchInput` onto the existing web `TripState`.

**Tech Stack:** Python 3.13, pydantic 2, openai SDK (OpenAI-compatible UIT Gemma endpoint), stdlib `http.server`; React 19 + TypeScript + Vite.

**Spec:** `docs/plans/TRIP_UNDERSTANDING_SPEC.md` (product design: `docs/TRIP_UNDERSTANDING.md`, `docs/ARCHITECTURE.md` §18).

## Global Constraints

- Docs in Vietnamese; code, comments, identifiers, commit messages in English (`RULE.md` §0).
- `trip` imports `corpus` only via `corpus.ontology` and `corpus.llm` (public). Never writes under `data/intel`.
- Every prompt and model setting lives in `src/corpus/llm/` (role `AGENT`, task `TRIP_TURN`). Model only from `.env` (`AGENT_API_KEY`, `AGENT_BASE_URL`, `AGENT_MODEL`), default = Gemma UIT. No automatic switch to another model.
- Agent timeouts: first token 8 s, total 30 s (`config/trip.yaml`); on timeout / error / bad JSON the turn is answered by the deterministic policy.
- Chip answers, panel edits and "Xem gợi ý" never call the LLM.
- Unknown stays `unknown`; no invented field, place or number; hard filters fail-closed (`unknown_policy` default `exclude`).
- Server binds `127.0.0.1:8766`; web proxies `/api/trip` there, before the `/api` → 8765 rule.
- Commit tested work per task (memory: commit allowed, push needs asking). Docs with other sessions' uncommitted edits are not committed in this plan.

## Review Focus

1. User never taps the opening chips and only types → `frame` must count as asked and the missing fields (days, companions, mobility) are asked one by one, not the frame again (Task 7 test `test_text_only_user_gets_missing_fields_one_by_one`).
2. Gemma unreachable for the whole session → every text turn still returns a card from the policy and the session can reach "Xem gợi ý" (Task 7 test `test_conversation_completes_without_the_agent`).
3. Page reload mid-conversation → same session, transcript, card and panel come back (Task 7 test `test_session_survives_restart`, Task 10 browser check).
4. User deletes a tier-1 value in the panel (e.g. mobility) → that question comes back as the card; "Xem gợi ý" refuses until answered (Task 7 test `test_removing_a_required_value_brings_its_question_back`).
5. Vietnamese words that look like signals but are not ("bầu trời", "mê chụp ảnh", "bỏ qua", "không cần view") must not create signals, companions or wishes (Task 3 test `test_lookalike_words_do_not_trigger`).

---

### Task 1: Trip State model, settings, text folding

**Files:**
- Create: `config/trip.yaml`, `src/trip/__init__.py`, `src/trip/settings.py`, `src/trip/text.py`, `src/trip/state.py`
- Modify: `pyproject.toml`
- Test: `tests/trip/__init__.py` (empty), `tests/trip/test_state.py`, `tests/trip/test_text.py`

**Interfaces:**
- Produces: `trip.settings.Settings` (`n_min, top_k, enough_factor, turn_budget, stop_score, first_token_s, total_s`, property `enough`), `trip.settings.load()`, `trip.settings.ROOT`; `trip.text.fold/squash/contains`; `trip.state.*`: `Frozen, Evidence, Field[T], SoftKey, Hard, Base, Anchor, Signal, Unmapped, Ambiguous, Meta, TripState, Draft, Update, apply, apply_drafts, settle, with_meta, pending_signals, unknown_fields, ontology`, constants `SCALARS, EFFORT_SIGNALS, OTHER_SIGNALS, EFFORT_FEATURES, WEIGHT_SIGN`, search-input models `Context, HardFilter, AnchorRef, SoftWeight, PaceSpec, NoveltySpec, SearchInput`.

- [ ] **Step 1: Add pydantic + pytest marker**

`pyproject.toml`: add `"pydantic>=2.6",` to `dependencies`; replace `[tool.pytest.ini_options]` with:

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
markers = ["live: calls the real AGENT model (python -m pytest -m live)"]
addopts = "-m 'not live'"
```

- [ ] **Step 2: Write config and small modules**

`config/trip.yaml`:

```yaml
# Trip Understanding thresholds (docs/TRIP_UNDERSTANDING.md §5.4, §8-9; docs/plans/TRIP_UNDERSTANDING_SPEC.md).
n_min: 1            # reviews behind a place's feature value before it counts as evidence
top_k: 20           # shortlist size used to measure whether a question changes the result
enough_factor: 1.5  # a hard filter's coverage is "enough" when verified passes >= top_k * enough_factor
turn_budget: 5      # adaptive questions after the opening card; tier-1 questions are asked anyway
stop_score: 0.15    # stop asking when the best remaining question scores below this
first_token_s: 8    # agent: wait this long for the first streamed token, then answer from the policy
total_s: 30         # agent: whole-call limit
```

`src/trip/__init__.py` (public API filled in Task 8):

```python
"""Trip Understanding: understand what the user needs for this trip -> Search Input (docs/TRIP_UNDERSTANDING.md)."""
```

`src/trip/settings.py`:

```python
"""Thresholds for Trip Understanding (config/trip.yaml)."""

from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    n_min: int = 1
    top_k: int = 20
    enough_factor: float = 1.5
    turn_budget: int = 5
    stop_score: float = 0.15
    first_token_s: float = 8.0
    total_s: float = 30.0

    @property
    def enough(self) -> int:
        return round(self.top_k * self.enough_factor)


def load(path: Path = ROOT / "config" / "trip.yaml") -> Settings:
    return Settings(**yaml.safe_load(path.read_text(encoding="utf-8")))
```

`src/trip/text.py`:

```python
"""Vietnamese text folding that keeps character positions, so a match in folded text maps back to the user's words."""

import re
import unicodedata


def fold(s: str) -> str:
    """Lowercase, strip diacritics, đ -> d. Same length as unicodedata.normalize('NFC', s)."""
    out = []
    for ch in unicodedata.normalize("NFC", s):
        c = ch.lower()
        out.append("d" if c == "đ" else unicodedata.normalize("NFD", c)[0])
    return "".join(out)


def squash(s: str) -> str:
    """fold, then anything that is not a letter or digit becomes one space."""
    return re.sub(r"[^a-z0-9]+", " ", fold(s)).strip()


def contains(haystack: str, needle: str) -> bool:
    """needle occurs in haystack as whole words, ignoring case, diacritics and punctuation."""
    n = squash(needle)
    return bool(n) and f" {n} " in f" {squash(haystack)} "
```

- [ ] **Step 3: Write the failing tests**

`tests/trip/__init__.py`: empty file.

`tests/trip/test_text.py`:

```python
from trip.text import contains, fold, squash


def test_fold_keeps_length_and_strips_marks():
    s = "Mẹ đau gối, Đà Lạt"
    assert fold(s) == "me dau goi, da lat"
    assert len(fold(s)) == len(s)


def test_contains_ignores_marks_and_punctuation():
    assert contains("Tháng 12 đi Đà Lạt, mẹ đau gối!", "Mẹ  đau gối")
    assert contains("đau gối", "đau")
    assert not contains("đau gối", "au g")
    assert squash("  A--b ") == "a b"
```

`tests/trip/test_state.py`:

```python
from datetime import date

import pytest
from pydantic import ValidationError

from trip.state import (Draft, Evidence, Field, SoftKey, TripState, Update, apply, apply_drafts, unknown_fields)

EV = Evidence(turn=1, quote="x")


def up(field, value=None, op="set", source="user", confidence="high"):
    return Update(field=field, op=op, value=value, source=source, confidence=confidence, evidence=EV)


def test_value_without_evidence_is_rejected():
    with pytest.raises(ValidationError):
        Field[int](value=3, source="user")
    with pytest.raises(ValidationError):
        Evidence(turn=1)


def test_soft_key_must_be_in_ontology():
    k = SoftKey.parse("crowd=low@time_of_day.morning@day_type.weekend")
    assert str(k) == "crowd=low@day_type.weekend@time_of_day.morning"
    for bad in ("crowd=empty", "nope=present", "crowd=low@time_of_day.midnight", "crowd", "crowd=low@morning"):
        with pytest.raises(ValueError):
            SoftKey.parse(bad)


def test_user_confirmed_value_is_not_overwritten_by_inference():
    s = apply(TripState(), up("pace", "packed"))
    assert apply(s, up("pace", "slow", source="inferred", confidence="medium")).pace.value == "packed"
    assert apply(s, up("pace", op="remove", source="inferred", confidence="medium")).pace.value == "packed"
    assert apply(s, up("pace", "slow")).pace.value == "slow"


def test_keyword_value_can_be_replaced_by_the_agent():
    s = apply(TripState(), up("days", 3, confidence="medium"))  # prepass: user words, not confirmed
    assert apply(s, up("days", 4, source="inferred", confidence="medium")).days.value == 4


def test_ranges_clock_and_literals_are_checked():
    with pytest.raises(ValueError):
        apply(TripState(), up("days", 12))
    with pytest.raises(ValueError):
        apply(TripState(), up("arrive_at", "9h"))
    with pytest.raises(ValueError):
        apply(TripState(), up("mobility", "bus"))
    assert apply(TripState(), up("arrive_at", "09:30")).arrive_at.value == "09:30"


def test_companions_add_and_remove():
    s = apply(apply(TripState(), up("companions", "parents", op="add")), up("companions", "kids", op="add"))
    assert s.companions.value == {"parents", "kids"}
    assert apply(s, up("companions", "kids", op="remove")).companions.value == {"parents"}


def test_soft_set_and_remove_normalise_the_key():
    s = apply(TripState(), up("soft", ("crowd=low@time_of_day.morning", "love"), op="add"))
    assert list(s.soft) == ["crowd=low@time_of_day.morning"]
    assert apply(s, up("soft", "crowd=low@time_of_day.morning", op="remove")).soft == {}


def test_user_remove_marks_skipped():
    s = apply(apply(TripState(), up("budget_vnd", 300_000)), up("budget_vnd", op="remove"))
    assert not s.budget_vnd.known and s.budget_vnd.status == "skipped"


def test_effort_hard_filter_settles_physical_signals():
    s = apply(TripState(), up("signal", "knee", op="add"))
    assert [x.handled for x in s.signals] == [False]
    steep = Draft(field="hard", op="add", value={"feature": "steep_or_stairs", "op": "ne", "value": "present"})
    s = apply_drafts(s, [steep], turn=2, tool="chip:c_effort:steep")
    assert [x.handled for x in s.signals] == [True]


def test_hard_dedupe_and_policy():
    d = {"feature": "steep_or_stairs", "op": "ne", "value": "present"}
    s = apply(apply(TripState(), up("hard", d, op="add")), up("hard", d, op="add"))
    assert len(s.hard) == 1
    assert apply(s, up("hard_policy", ("steep_or_stairs", "flag"))).hard[0].unknown_policy == "flag"
    with pytest.raises(ValueError):
        apply(TripState(), up("hard", {"feature": "steep_or_stairs", "op": "ne", "value": "maybe"}, op="add"))


def test_pending_add_and_remove():
    s = apply(TripState(), up("pending", {"phrase": "chill", "keys": ["noise=quiet", "crowd=low"]}, op="add"))
    assert s.meta.pending[0].keys == ("noise=quiet", "crowd=low")
    assert apply(s, up("pending", "chill", op="remove")).meta.pending == ()


def test_unknown_fields_lists_what_is_missing():
    s = apply(TripState(), up("days", 3))
    assert "dates" in unknown_fields(s) and "days" not in unknown_fields(s)


def test_state_round_trips_through_json():
    s = apply(apply(TripState(), up("start_date", date(2026, 12, 12))), up("companions", "parents", op="add"))
    s = apply(s, up("soft", ("noise=quiet", "love"), op="add"))
    assert TripState.model_validate_json(s.model_dump_json()) == s
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python -m pytest -q tests/trip`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'trip.state'`.

- [ ] **Step 5: Implement `src/trip/state.py`**

```python
"""Trip State and Search Input (docs/plans/TRIP_UNDERSTANDING_SPEC.md §2).

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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pip install -e . && python -m pytest -q tests/trip`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml config/trip.yaml src/trip tests/trip
git commit -m "feat(trip): sourced Trip State with validated updates"
```

---

### Task 2: Catalog and coverage

**Files:**
- Create: `src/trip/catalog.py`, `src/trip/coverage.py`, `tests/trip/conftest.py`
- Test: `tests/trip/test_catalog.py`

**Interfaces:**
- Consumes: `trip.state.Hard`, `trip.text.squash`, `trip.settings.Settings`.
- Produces: `Known(value, n, by_context)`, `Candidate(id, name, category, lat, lng, hours, known, weight)` with `value(feature, context=()) -> str | None`; `Catalog(places, videos=None)` with `.places`, `.by_id`, `.video_place`, `.name_keys`, `count(key) -> int`, classmethods `from_records(records, n_min, videos=None)`, `load(data: Path, n_min)`. `coverage.verdict(c, h)`, `Coverage(passed, failed, unknown, level)`, `coverage(h, places, enough)`, `admissible(c, hard) -> bool`. Test fixtures `rec(...)`, `catalog`, `cfg`.

- [ ] **Step 1: Write fixtures and failing tests**

`tests/trip/conftest.py`:

```python
import pytest

from trip.catalog import Catalog
from trip.settings import Settings


def rec(i, name, feats, hours=None, status="signal", needs_review=False):
    """One data/intel/places record; feats: {feature: (top_value, n) or (top_value, n, by_context)}."""
    return {"place_fid": f"0x{i:x}:0x1", "place_name": name,
            "identity": {"category": "Quán cà phê", "lat": 11.94, "lng": 108.45},
            "operation": {"hours": hours},
            "features": {f: {"n": v[1], "top_value": v[0], "status": status, "needs_review": needs_review,
                             "by_context": v[2] if len(v) > 2 else {}} for f, v in feats.items()}}


MONDAY_CLOSED = {"mon": [], "tue": [["07:00", "22:00"]], "wed": [["07:00", "22:00"]], "thu": [["07:00", "22:00"]],
                 "fri": [["07:00", "22:00"]], "sat": [["07:00", "22:00"]], "sun": [["07:00", "22:00"]]}


@pytest.fixture
def records():
    quiet = [rec(i, f"Quán Yên Tĩnh Số {i}", {"noise": ("quiet", 5), "long_stay_chill": ("present", 4),
                                               "crowd": ("low", 3)}) for i in range(1, 7)]
    loud = [rec(i, f"Quán Nhạc Sống {i}", {"noise": ("loud", 5), "live_music": ("present", 6),
                                            "crowd": ("high", 4)}) for i in range(7, 13)]
    steep = [rec(i, f"Đồi Dốc Cao {i}", {"steep_or_stairs": ("present", 3), "scenic_view": ("present", 9),
                                          "photo_spot": ("present", 4)}) for i in range(13, 17)]
    flat = [rec(17, "Vườn Phẳng Lặng Xanh", {"steep_or_stairs": ("absent", 2), "scenic_view": ("present", 3)},
                hours=MONDAY_CLOSED)]
    other = [rec(i, f"Chợ Phiên Đêm {i}", {"local_specialty_food": ("present", 5)}) for i in range(18, 22)]
    return quiet + loud + steep + flat + other


@pytest.fixture
def catalog(records):
    return Catalog.from_records(records, n_min=1, videos={"7565853238147255573": "0x11:0x1"})


@pytest.fixture
def cfg():
    return Settings(n_min=1, top_k=4, enough_factor=1.0, turn_budget=5, stop_score=0.05)
```

`tests/trip/test_catalog.py`:

```python
import json

import pytest

from trip.catalog import Catalog
from trip.coverage import admissible, coverage, verdict
from trip.state import Evidence, Hard

from .conftest import rec

EV = (Evidence(turn=1, quote="x"),)


def hard(**kw):
    return Hard(feature="steep_or_stairs", op="ne", value="present", evidence=EV, **kw)


def test_only_served_values_count():
    c = Catalog.from_records([
        rec(1, "A", {"noise": ("quiet", 1)}),
        rec(2, "B", {"noise": ("quiet", 5)}, status="uncertain"),
        rec(3, "C", {"kids": ("suitable", 5)}, needs_review=True),
    ], n_min=2)
    assert c.by_id["0x1:0x1"].value("noise") is None
    assert c.by_id["0x2:0x1"].value("noise") is None
    assert c.by_id["0x3:0x1"].value("kids") is None


def test_context_value_wins_when_present():
    c = Catalog.from_records([rec(1, "A", {"crowd": ("high", 5, {"time_of_day=morning": {"low": 3, "high": 1}})})], 1)
    p = c.by_id["0x1:0x1"]
    assert p.value("crowd") == "high"
    assert p.value("crowd", (("time_of_day", "morning"),)) == "low"
    assert p.value("crowd", (("time_of_day", "night"),)) == "high"


def test_count_and_hours(catalog):
    assert catalog.count("noise=quiet") == 6
    assert catalog.count("crowd=low@time_of_day.morning") == 6
    assert catalog.by_id["0x11:0x1"].hours["mon"] == ()


def test_load_reads_intel_and_tiktok(tmp_path, records):
    (tmp_path / "intel" / "places").mkdir(parents=True)
    for r in records[:2]:
        (tmp_path / "intel" / "places" / f"{r['place_fid'].replace(':', '_')}.json").write_text(json.dumps(r), "utf-8")
    (tmp_path / "tiktok" / "place_filter").mkdir(parents=True)
    (tmp_path / "tiktok" / "place_filter" / "x.json").write_text(json.dumps({"fid": "0x1:0x1", "videos": [
        {"video_id": "111", "llm": {"relevance": "yes"}}, {"video_id": "222", "llm": {"relevance": "no"}}]}), "utf-8")
    c = Catalog.load(tmp_path, n_min=1)
    assert len(c.places) == 2 and c.video_place == {"111": "0x1:0x1"}


def test_load_without_intel_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        Catalog.load(tmp_path, n_min=1)


def test_coverage_counts_pass_fail_unknown(catalog):
    c = coverage(hard(), catalog.places, enough=4)
    assert (c.passed, c.failed, c.level) == (1, 4, "thin")
    assert c.passed + c.failed + c.unknown == len(catalog.places)
    assert coverage(Hard(feature="long_walk", op="ne", value="present", evidence=EV), catalog.places, 4).level == "none"


def test_unknown_is_excluded_unless_flagged(catalog):
    flat, steep, quiet = catalog.by_id["0x11:0x1"], catalog.by_id["0xd:0x1"], catalog.by_id["0x1:0x1"]
    assert verdict(flat, hard()) == "pass" and verdict(steep, hard()) == "fail" and verdict(quiet, hard()) == "unknown"
    assert admissible(flat, [hard()]) and not admissible(steep, [hard(unknown_policy="flag")])
    assert not admissible(quiet, [hard()]) and admissible(quiet, [hard(unknown_policy="flag")])
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest -q tests/trip/test_catalog.py`
Expected: ERROR `No module named 'trip.catalog'`.

- [ ] **Step 3: Implement**

`src/trip/catalog.py`:

```python
"""Read-only view of Place Intelligence for online use: data/intel/places + data/tiktok/place_filter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .text import squash


@dataclass(frozen=True)
class Known:
    value: str
    n: int
    by_context: dict[str, str]  # "time_of_day=morning" -> top value in that context


@dataclass(frozen=True)
class Candidate:
    id: str
    name: str
    category: str | None
    lat: float | None
    lng: float | None
    hours: dict[str, tuple[tuple[str, str], ...]] | None
    known: dict[str, Known]  # served features only (enough reviews, not uncertain, not waiting for review)
    weight: int  # total evidence behind the record; ranking tie-break

    def value(self, feature: str, context: tuple[tuple[str, str], ...] = ()) -> str | None:
        k = self.known.get(feature)
        if k is None:
            return None
        for key, v in context:
            hit = k.by_context.get(f"{key}={v}")
            if hit:
                return hit
        return k.value


@dataclass
class Catalog:
    places: tuple[Candidate, ...]
    video_place: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        self.places = tuple(self.places)
        self.by_id = {p.id: p for p in self.places}
        # names long enough that seeing one in the agent's text means it named a place
        self.name_keys = [(k, p.id) for p in self.places if len((k := squash(p.name)).split()) >= 3]
        self._counts: dict[str, int] = {}

    def count(self, key: str) -> int:
        """Places whose served value matches 'feature=value' (context suffix ignored)."""
        if key not in self._counts:
            feature, _, value = key.split("@")[0].partition("=")
            self._counts[key] = sum(1 for p in self.places if p.value(feature) == value)
        return self._counts[key]

    @classmethod
    def from_records(cls, records: Iterable[dict], n_min: int, videos: dict[str, str] | None = None) -> Catalog:
        out = []
        for r in records:
            known, total = {}, 0
            for fid, sig in (r.get("features") or {}).items():
                total += sig.get("n", 0)
                served = sig.get("n", 0) >= n_min and sig.get("status") == "signal" and not sig.get("needs_review")
                if served and sig.get("top_value"):
                    ctx = {k: max(d, key=d.get) for k, d in (sig.get("by_context") or {}).items() if d}
                    known[fid] = Known(sig["top_value"], sig["n"], ctx)
            ident = r.get("identity") or {}
            hours = (r.get("operation") or {}).get("hours")
            out.append(Candidate(
                id=r["place_fid"], name=r["place_name"], category=ident.get("category"),
                lat=ident.get("lat"), lng=ident.get("lng"),
                hours={d: tuple(tuple(w) for w in ws) for d, ws in hours.items()} if hours else None,
                known=known, weight=total))
        return cls(tuple(out), dict(videos or {}))

    @classmethod
    def load(cls, data: Path, n_min: int) -> Catalog:
        files = sorted((data / "intel" / "places").glob("*.json"))
        if not files:
            raise FileNotFoundError(f"no place records in {data / 'intel' / 'places'}: run python -m corpus aggregate")
        records = [json.loads(p.read_text(encoding="utf-8")) for p in files]
        videos: dict[str, str] = {}
        for p in sorted((data / "tiktok" / "place_filter").glob("*.json")):
            d = json.loads(p.read_text(encoding="utf-8"))
            for v in d.get("videos") or []:
                if (v.get("llm") or {}).get("relevance") == "yes":
                    videos[str(v["video_id"])] = d["fid"]
        return cls.from_records(records, n_min, videos)
```

`src/trip/coverage.py`:

```python
"""How many candidates the corpus can actually check for a hard filter (docs/TRIP_UNDERSTANDING.md §5.4)."""

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Literal

from .catalog import Candidate
from .state import Hard

Verdict = Literal["pass", "fail", "unknown"]


def verdict(c: Candidate, h: Hard) -> Verdict:
    v = c.value(h.feature)
    if v is None:
        return "unknown"
    return "pass" if (v == h.value) == (h.op == "eq") else "fail"


@dataclass(frozen=True)
class Coverage:
    passed: int
    failed: int
    unknown: int
    level: Literal["enough", "thin", "none"]


def coverage(h: Hard, places: Iterable[Candidate], enough: int) -> Coverage:
    n = Counter(verdict(c, h) for c in places)
    p = n["pass"]
    return Coverage(p, n["fail"], n["unknown"], "enough" if p >= enough else "thin" if p else "none")


def admissible(c: Candidate, hard: Iterable[Hard]) -> bool:
    """Fail-closed: a failing place is out; an unknown one is out unless the user chose to see it flagged."""
    for h in hard:
        v = verdict(c, h)
        if v == "fail" or (v == "unknown" and h.unknown_policy != "flag"):
            return False
    return True
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest -q tests/trip`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/trip/catalog.py src/trip/coverage.py tests/trip
git commit -m "feat(trip): read-only place catalog and hard-filter coverage"
```

---

### Task 3: Prepass, resolve, value parsing

**Files:**
- Create: `src/trip/prepass.py`, `src/trip/resolve.py`, `src/trip/values.py`
- Test: `tests/trip/test_prepass.py`, `tests/trip/test_resolve.py`

**Interfaces:**
- Consumes: `trip.text.fold/squash`, `trip.catalog.Catalog`, `trip.state.Anchor/Base/SoftKey/ontology`.
- Produces: `prepass(text, today) -> Prepass(proposals: tuple[Proposal], ambiguous: tuple[tuple[quote, keys]])`, `Proposal(field, op, value, quote, inferred)`. `resolve.URL`, `score(q, name)`, `search(q, catalog, limit=6) -> list[Candidate]`, `link_place(url, catalog)`, `anchor_for(text, catalog) -> Anchor`. `values.parse(field, raw, catalog)`, `values.parse_remove(field, raw)`, `values.clock(raw)`, `values.money(raw)`, `values.jsonable(v)`.

- [ ] **Step 1: Write failing tests**

`tests/trip/test_prepass.py`:

```python
from datetime import date

from trip.prepass import prepass

TODAY = date(2026, 10, 2)


def got(text):
    return {(p.field, p.value if not isinstance(p.value, dict) else p.value["feature"], p.inferred)
            for p in prepass(text, TODAY).proposals}


def test_days():
    assert ("days", 3, False) in got("đi Đà Lạt 3 ngày 2 đêm")
    assert ("days", 2, False) in got("lịch 2N1Đ")
    assert ("days", 3, False) in got("ba ngày thôi")
    assert not any(f == "days" for f, *_ in got("đi 5 người"))


def test_month_and_dates():
    assert ("month", 12, False) in got("tháng 12 đi")
    g = got("đi từ 12-14/12")
    assert ("start_date", date(2026, 12, 12), False) in g and ("days", 3, False) in g
    assert ("start_date", date(2027, 1, 5), False) in got("ngày 5/1")


def test_companions_and_signals():
    g = got("Đi với ba má, mẹ đau gối")
    assert ("companions", "parents", False) in g
    assert ("signal", "elderly", True) in g and ("signal", "knee", False) in g


def test_quote_is_the_users_own_words():
    p = next(p for p in prepass("Mẹ Đau Gối lắm", TODAY).proposals if p.field == "signal")
    assert p.quote == "Đau Gối"


def test_mobility_people_budget():
    g = got("4 người đi xe máy, không quá 300k/người")
    assert ("mobility", "motorbike", False) in g and ("people", 4, False) in g and ("budget_vnd", 300_000, False) in g


def test_chill_is_ambiguous_and_single_meaning_is_soft():
    r = prepass("muốn chill, săn mây", TODAY)
    assert r.ambiguous[0][0] == "chill" and "noise=quiet" in r.ambiguous[0][1]
    assert any(p.field == "soft" and p.value == ("cloud_hunting=present", "love") for p in r.proposals)


def test_effort_words_become_hard_filters():
    assert ("hard", "steep_or_stairs", False) in got("tránh dốc giúp mình")
    assert ("hard", "long_walk", False) in got("mẹ ngại đi bộ")


def test_lookalike_words_do_not_trigger():
    g = got("mê chụp ảnh bầu trời, bỏ qua, không cần view")
    assert not any(f in ("signal", "companions") for f, *_ in g)
    fields = {(f, v) for f, v, _ in g}
    assert ("soft", ("scenic_view=present", "love")) not in fields
```

`tests/trip/test_resolve.py`:

```python
from datetime import date

import pytest

from trip import values
from trip.resolve import anchor_for, search
from trip.state import Base


def test_exact_name_matches(catalog):
    a = anchor_for("Vườn Phẳng Lặng Xanh", catalog)
    assert (a.state, a.place_id) == ("matched", "0x11:0x1")


def test_shared_words_ask_to_choose(catalog):
    a = anchor_for("Quán Yên Tĩnh", catalog)
    assert a.state == "choose" and len(a.candidates) == 3


def test_generic_words_never_match(catalog):
    assert anchor_for("quán cà phê", catalog).state == "missing"


def test_links(catalog):
    maps = "https://www.google.com/maps/place/X/data=!4m2!3m1!1s0x11:0x1"
    assert anchor_for(maps, catalog).place_id == "0x11:0x1"
    tt = "https://www.tiktok.com/@a/video/7565853238147255573"
    assert anchor_for(tt, catalog).place_id == "0x11:0x1"
    assert anchor_for("https://maps.app.goo.gl/abc", catalog).state == "missing"


def test_search_prefers_prefix(catalog):
    assert search("Vườn Phẳng", catalog)[0].id == "0x11:0x1"
    assert search("x", catalog) == []


def test_value_parsing(catalog):
    assert values.clock("9h") == "09:00" and values.clock("14:30") == "14:30"
    assert values.money("300k") == 300_000 and values.money("1,5tr") == 1_500_000
    assert values.parse("start_date", "2026-12-12", catalog) == date(2026, 12, 12)
    assert values.parse("days", "3 ngày", catalog) == 3
    assert values.parse("hard", "steep_or_stairs!=present", catalog) == {"feature": "steep_or_stairs", "op": "ne",
                                                                         "value": "present"}
    assert values.parse("soft", "noise=quiet", catalog) == ("noise=quiet", "love")
    assert values.parse("soft", "crowd=low@time_of_day.morning:avoid", catalog) == ("crowd=low@time_of_day.morning", "avoid")
    assert values.parse("base", "0x11:0x1", catalog) == Base(place_id="0x11:0x1", text="Vườn Phẳng Lặng Xanh")
    assert values.parse("base", "gần chợ", catalog) == Base(place_id=None, text="gần chợ")
    for field, raw in (("hard", "steep_or_stairs!=maybe"), ("soft", "nope=present"), ("arrive_at", "sáng"), ("days", "")):
        with pytest.raises(ValueError):
            values.parse(field, raw, catalog)
    assert values.parse_remove("soft", "noise=quiet:love") == "noise=quiet"
    assert values.parse_remove("hard", "steep_or_stairs!=present") == "steep_or_stairs"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest -q tests/trip/test_prepass.py tests/trip/test_resolve.py`
Expected: ERROR `No module named 'trip.prepass'`.

- [ ] **Step 3: Implement `src/trip/prepass.py`**

```python
"""Deterministic first read of a user message (docs/plans/TRIP_UNDERSTANDING_SPEC.md §5).

Numbers, dates, who, transport, health hints, money and keyword features. Runs before the agent, so the screen reacts at
once and a failed agent call still records something. Every proposal quotes the user's own words.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from .text import fold


@dataclass(frozen=True)
class Proposal:
    field: str
    op: str
    value: object
    quote: str
    inferred: bool = False


@dataclass(frozen=True)
class Prepass:
    proposals: tuple[Proposal, ...]
    ambiguous: tuple[tuple[str, tuple[str, ...]], ...]  # (quote, soft keys it may mean)


NUMBER = {"mot": 1, "hai": 2, "ba": 3, "bon": 4, "tu": 4, "nam": 5, "sau": 6, "bay": 7}
NEGATION = re.compile(r"\b(khong|chang|ko|tranh|ghet|ngai|so)\s+(\w+\s+)?$")

COMPANIONS = [
    (r"\b(bo me|ba me|ba ma|cha me|ong ba|phu huynh|nguoi lon tuoi)\b", "parents"),
    (r"\b(nguoi yeu|ban gai|ban trai|vo chong|hai vo chong|cap doi|honeymoon|trang mat)\b", "partner"),
    (r"\b(ban be|nhom ban|hoi ban|dong nghiep|team)\b", "friends"),
    (r"\b(con nho|tre nho|tre em|em be|be nho|cac be|con trai|con gai)\b", "kids"),
    (r"\b(mot minh|solo)\b", "solo"),
]
SIGNALS = [
    (r"\b(dau goi|dau chan|dau lung|moi goi|thoai hoa|kho di lai|di lai kho|chan yeu|yeu chan)\b", "knee"),
    (r"\b(nguoi gia|lon tuoi|cao tuoi)\b", "elderly"),
    (r"\bxe lan\b", "wheelchair"),
    (r"\b(co bau|mang thai|dang bau|bau bi)\b", "pregnant"),
    (r"\bsay (xe|deo)\b", "motion_sick"),
    (r"\bso (do cao|cao)\b", "height"),
    (r"\b(an chay|chay truong|thuan chay)\b", "vegetarian"),
]
MOBILITY = [
    (r"\b(xe may|xe so|xe tay ga)\b", "motorbike"),
    (r"\b(o to|oto|xe hoi|xe rieng|tu lai|xe 4 cho|xe 7 cho)\b", "car"),
    (r"\b(grab|taxi|xe cong nghe|xanh sm|goi xe)\b", "ride"),
]
PACE = [
    (r"\b(thong tha|nhe nhang|di it|khong voi|cham rai)\b", "slow"),
    (r"\b(di nhieu|cang nhieu cang tot|kham pha het|full lich)\b", "packed"),
]
NOVELTY = [
    (r"\b(thu moi|cho moi|cai moi|muon khac|chua di bao gio)\b", "new"),
    (r"\b(cho quen|nhu lan truoc)\b", "familiar"),
]
HARD = [
    (r"\b(tranh doc|khong leo|ngai leo|ngai bac thang|khong bac thang|it bac thang)\b", "steep_or_stairs"),
    (r"\b(khong di bo xa|ngai di bo|it di bo|khong di bo nhieu)\b", "long_walk"),
]
# Minimal lexicon until the span lexicon exists (docs/TRIP_UNDERSTANDING.md §5.2): one key = a clear wish,
# several = a subjective word to clarify.
LEXICON = [
    (r"\b(chill|thu gian|thu thai)\b", ("long_stay_chill=present", "noise=quiet", "crowd=low", "scenic_view=present",
                                       "cozy_decor=present")),
    (r"\b(yen tinh|tinh lang)\b", ("noise=quiet",)),
    (r"\b(vang ve|it nguoi|khong dong|tranh dong)\b", ("crowd=low",)),
    (r"\b(view|canh dep|ngam canh)\b", ("scenic_view=present",)),
    (r"\b(san may|bien may)\b", ("cloud_hunting=present",)),
    (r"\b(hoang hon|binh minh)\b", ("sunset_view=present",)),
    (r"\b(chup anh|chup hinh|song ao|check in|checkin)\b", ("photo_spot=present",)),
    (r"\b(thien nhien|rung thong|thac|suoi)\b", ("nature=present",)),
    (r"\b(vuon hoa|doi hoa|ngam hoa|mua hoa)\b", ("flower_garden=present",)),
    (r"\b(kien truc|di tich|lich su|co kinh)\b", ("heritage_architecture=present",)),
    (r"\bvan hoa\b", ("heritage_architecture=present", "cultural_show=present")),
    (r"\b(cafe|ca phe|coffee)\b", ("cozy_decor=present", "long_stay_chill=present", "drink_quality=good",
                                   "scenic_view=present")),
    (r"\b(dac san|mon dia phuong)\b", ("local_specialty_food=present",)),
    (r"\b(an ngon|do an ngon)\b", ("food_quality=good",)),
    (r"\b(am thuc|an uong)\b", ("local_specialty_food=present", "food_quality=good")),
    (r"\b(nhac song|acoustic)\b", ("live_music=present",)),
    (r"\b(mao hiem|zipline|mang truot|canyoning|cam giac manh)\b", ("adventure_activity=present",)),
    (r"\b(leo nui|trekking|trek)\b", ("hiking=present",)),
    (r"\b(hai dau|vuon dau|hai trai cay)\b", ("pick_your_own=present",)),
    (r"\b(cam trai|glamping|ngu leu)\b", ("camping=present",)),
    (r"\b(workshop|tu tay lam)\b", ("hands_on_workshop=present",)),
    (r"\b(thu cung|vuon thu|so thu)\b", ("animals=present",)),
    (r"\b(gia re|binh dan|dang tien|gia hop ly)\b", ("value_for_money=good",)),
    (r"\b(lam viec|laptop)\b", ("laptop_friendly=present",)),
    (r"\b(rong rai|thoang dang)\b", ("spacious=present",)),
]


def _next_date(day: int, month: int, today: date) -> date | None:
    for year in (today.year, today.year + 1):
        try:
            d = date(year, month, day)
        except ValueError:
            return None
        if d >= today:
            return d
    return None


def prepass(text: str, today: date) -> Prepass:
    raw = unicodedata.normalize("NFC", text)
    low = fold(raw)
    out: list[Proposal] = []
    taken: list[tuple[int, int]] = []

    def add(field, value, m, op="set", inferred=False, group=0):
        out.append(Proposal(field, op, value, raw[m.start(group):m.end(group)], inferred))

    # a range first, so "12-14/12" is not also read as two single dates
    for m in re.finditer(r"\b(\d{1,2})\s*(?:-|–|den)\s*(\d{1,2})\s*/\s*(\d{1,2})\b", low):
        d1, d2, mo = map(int, m.groups())
        start = _next_date(d1, mo, today)
        if start and d2 >= d1:
            add("start_date", start, m)
            add("days", d2 - d1 + 1, m)
            taken.append(m.span())
    for m in re.finditer(r"\b(\d{1,2})\s*/\s*(\d{1,2})\b", low):
        if any(a <= m.start() < b for a, b in taken):
            continue
        start = _next_date(int(m[1]), int(m[2]), today)
        if start:
            add("start_date", start, m)
    for m in re.finditer(r"\bthang\s*(\d{1,2})\b", low):
        if 1 <= int(m[1]) <= 12:
            add("month", int(m[1]), m)
    if not any(p.field == "days" for p in out):
        m = re.search(r"\b(\d)\s*n\s*(\d)\s*d\b", low)
        if m:
            add("days", int(m[1]), m)
        else:
            for m in re.finditer(r"\b(\d{1,2}|mot|hai|ba|bon|nam|sau|bay)\s*(?:ngay|n)\b", low):
                n = int(m[1]) if m[1].isdigit() else NUMBER[m[1]]
                if 1 <= n <= 7:
                    add("days", n, m)
                    break
    for m in re.finditer(r"\b(\d{1,2})\s*(?:nguoi|ng)\b", low):
        add("people", int(m[1]), m)
        break
    for m in re.finditer(r"\b(\d+(?:[.,]\d+)?)\s*(k|nghin|ngan|tr|trieu|cu)\b", low):
        n = float(m[1].replace(",", "."))
        add("budget_vnd", int(n * (1000 if m[2] in ("k", "nghin", "ngan") else 1_000_000)), m)
        break
    for pattern, who in COMPANIONS:
        for m in re.finditer(pattern, low):
            add("companions", who, m, op="add")
            if who == "parents":
                add("signal", "elderly", m, op="add", inferred=True)
            if who == "kids":
                add("signal", "kids", m, op="add", inferred=True)
    for pattern, kind in SIGNALS:
        for m in re.finditer(pattern, low):
            add("signal", kind, m, op="add")
    for table, field in ((MOBILITY, "mobility"), (PACE, "pace"), (NOVELTY, "novelty")):
        for pattern, value in table:
            m = re.search(pattern, low)
            if m:
                add(field, value, m)
                break
    for pattern, feature in HARD:
        for m in re.finditer(pattern, low):
            add("hard", {"feature": feature, "op": "ne", "value": "present"}, m, op="add")
    ambiguous: list[tuple[str, tuple[str, ...]]] = []
    for pattern, keys in LEXICON:
        for m in re.finditer(pattern, low):
            if NEGATION.search(low[max(0, m.start() - 16):m.start()]):
                continue
            if len(keys) == 1:
                add("soft", (keys[0], "love"), m, op="add")
            else:
                ambiguous.append((raw[m.start():m.end()], keys))
    seen, unique = set(), []
    for p in out:
        key = (p.field, p.op, repr(p.value))
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return Prepass(tuple(unique), tuple(dict.fromkeys(ambiguous)))
```

- [ ] **Step 4: Implement `src/trip/resolve.py`**

```python
"""Place name or link -> catalog place (docs/PLACE_DECISION.md §4). Port of web/src/user/search.ts."""

import re

from .catalog import Candidate, Catalog
from .state import Anchor
from .text import squash

STOP = {"quan", "tiem", "cafe", "ca", "phe", "coffee", "nha", "hang", "the", "va", "cua"}
CITY = re.compile(r"\b(da lat|dalat|tp|thanh pho)\b")
URL = re.compile(r"https?://\S+")
FID = re.compile(r"0x[0-9a-f]+:0x[0-9a-f]+", re.I)
VIDEO = re.compile(r"/video/(\d+)")


def _name(s: str) -> str:
    return " ".join(CITY.sub(" ", squash(s)).split())


def _tokens(s: str) -> list[str]:
    return [t for t in _name(s).split() if len(t) > 1]


def score(q: str, name: str) -> float:
    """Token overlap on distinctive words; never a match on generic words alone."""
    qt, nt = _tokens(q), set(_tokens(name))
    if not qt:
        return 0.0
    fq, fn = _name(q), _name(name)
    if fq == fn:
        return 1.0
    hits = [t for t in qt if t in nt]
    if not [t for t in hits if t not in STOP]:
        return 0.0
    s = len(hits) / max(len(qt), len(nt))
    if fq in fn or fn in fq:
        s = max(s, 0.8)
    return s


def search(q: str, catalog: Catalog, limit: int = 6) -> list[Candidate]:
    if len(squash(q)) < 2:
        return []
    fq = _name(q)
    ranked = sorted(((score(q, p.name) + (0.3 if _name(p.name).startswith(fq) else 0.0), p.id, p)
                     for p in catalog.places), key=lambda x: (-x[0], x[1]))
    return [p for s, _, p in ranked if s > 0.2][:limit]


def link_place(url: str, catalog: Catalog) -> str | None:
    m = FID.search(url)
    if m and m[0].lower() in catalog.by_id:
        return m[0].lower()
    m = VIDEO.search(url)
    return catalog.video_place.get(m[1]) if m else None


def anchor_for(text: str, catalog: Catalog) -> Anchor:
    text = text.strip()
    if URL.match(text):
        pid = link_place(text, catalog)
        return Anchor(text=text, place_id=pid, state="matched" if pid else "missing")
    ranked = sorted(((score(text, p.name), p.id) for p in catalog.places), key=lambda x: (-x[0], x[1]))
    ranked = [r for r in ranked if r[0] > 0.34]
    if not ranked:
        return Anchor(text=text, state="missing")
    s1, id1 = ranked[0]
    if s1 >= 0.8 and (len(ranked) == 1 or s1 - ranked[1][0] >= 0.25):
        return Anchor(text=text, place_id=id1, state="matched")
    return Anchor(text=text, state="choose", candidates=tuple(i for _, i in ranked[:3]))
```

- [ ] **Step 5: Implement `src/trip/values.py`**

```python
"""Turn the agent's / the screen's string values into typed values for apply()."""

import re
from datetime import date
from typing import Any

from pydantic import BaseModel

from .catalog import Catalog
from .resolve import anchor_for
from .state import Base, SoftKey, ontology
from .text import fold

MONEY = re.compile(r"(\d+(?:[.,]\d+)?)\s*(k|nghin|ngan|tr|trieu|cu)?")
LITERALS = ("companions", "mobility", "purpose", "pace", "novelty", "crowd_tolerance", "signal")


def clock(raw: str) -> str:
    m = re.fullmatch(r"\s*(\d{1,2})\s*(?:[:h]\s*(\d{2})?)?\s*", raw.lower())
    if not m or int(m[1]) > 23 or int(m[2] or 0) > 59:
        raise ValueError(f"not a time: {raw!r}")
    return f"{int(m[1]):02d}:{int(m[2] or 0):02d}"


def money(raw: str) -> int:
    m = MONEY.search(fold(raw))
    if not m:
        raise ValueError(f"not an amount: {raw!r}")
    n = float(m[1].replace(",", "."))
    unit = m[2]
    return int(n * 1000 if unit in ("k", "nghin", "ngan") else n * 1_000_000 if unit in ("tr", "trieu", "cu") else n)


def parse(field: str, raw: str, catalog: Catalog) -> Any:
    raw = raw.strip()
    if not raw:
        raise ValueError(f"{field}: empty value")
    if field == "start_date":
        return date.fromisoformat(raw[:10])
    if field in ("month", "days", "people", "max_leg_min"):
        m = re.search(r"\d+", raw)
        if not m:
            raise ValueError(f"{field}: no number in {raw!r}")
        return int(m[0])
    if field == "budget_vnd":
        return money(raw)
    if field in ("arrive_at", "leave_at", "day_end"):
        return clock(raw)
    if field == "base":
        if raw in catalog.by_id:
            return Base(place_id=raw, text=catalog.by_id[raw].name)
        a = anchor_for(raw, catalog)
        return Base(place_id=a.place_id if a.state == "matched" else None, text=raw)
    if field == "anchor":
        return anchor_for(raw, catalog)
    if field == "soft":
        key, sep, weight = raw.rpartition(":")
        if not sep or weight not in ("love", "avoid", "off"):
            key, weight = raw, "love"
        return str(SoftKey.parse(key)), weight
    if field == "hard":
        m = re.fullmatch(r"\s*([a-z_]+)\s*(!=|=)\s*([a-z_0-9]+)\s*", raw)
        if not m or not ontology().valid(m[1], m[3]):
            raise ValueError(f"hard filter {raw!r} is not feature!=value from the ontology")
        return {"feature": m[1], "op": "ne" if m[2] == "!=" else "eq", "value": m[3]}
    if field in LITERALS:
        return raw.lower()
    if field == "unmapped":
        return raw
    raise ValueError(f"unknown field {field!r}")


def parse_remove(field: str, raw: str) -> Any:
    """What apply() needs to remove something the agent names."""
    raw = raw.strip()
    if field == "soft":
        key, sep, weight = raw.rpartition(":")
        return str(SoftKey.parse(key if sep and weight in ("love", "avoid", "off") else raw))
    if field == "hard":
        return re.split(r"!=|=", raw)[0].strip()
    if field in ("companions", "signal"):
        return raw.lower()
    raise ValueError(f"{field}: the agent cannot remove by name")


def jsonable(v: Any) -> Any:
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (frozenset, set)):
        return sorted(v)
    if isinstance(v, BaseModel):
        return v.model_dump(mode="json")
    if isinstance(v, (tuple, list)):
        return [jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    return v
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest -q tests/trip`
Expected: all pass. If a Vietnamese case fails, fix the pattern table, not the test.

- [ ] **Step 7: Commit**

```bash
git add src/trip/prepass.py src/trip/resolve.py src/trip/values.py tests/trip
git commit -m "feat(trip): deterministic prepass, place resolve and value parsing"
```

---

### Task 4: Question bank, tier-1 rules, question value, policy

**Files:**
- Create: `src/trip/questions.py`, `src/trip/policy.py`
- Test: `tests/trip/test_questions.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: `Chip(id, label, row, drafts)`, `Question(qid, group, text, reason, chips, multi, single_rows, cost, tier, input, input_field, exits, exit_drafts, custom)`; `required(state, catalog, cfg) -> Question | None`; `bank(state, catalog, cfg) -> list[Question]`; `shortlist(state, catalog, cfg) -> list[str]`; `rank_questions(state, catalog, cfg) -> list[tuple[Question, float]]`; `clarify_q(state)`, `purpose_q()`, `show_first_q()`, `READY`. `policy.next_question(state, catalog, cfg) -> Question`, `policy.askable(state, catalog, cfg) -> dict[str, Question]`.

- [ ] **Step 1: Write failing tests**

`tests/trip/test_questions.py`:

```python
from datetime import date

from trip.policy import askable, next_question
from trip.questions import READY, bank, rank_questions, required
from trip.state import Anchor, Evidence, TripState, Update, apply, with_meta

EV = Evidence(turn=1, quote="x")


def up(s, field, value=None, op="set"):
    return apply(s, Update(field=field, op=op, value=value, source="user", confidence="high", evidence=EV))


def framed(**meta):
    s = up(up(up(TripState(), "days", 3), "companions", "solo", "add"), "mobility", "motorbike")
    s = up(s, "start_date", date(2026, 12, 14))  # a Monday
    return with_meta(s, asked=("frame",), **meta)


def test_frame_comes_first(catalog, cfg):
    q = required(TripState(), catalog, cfg)
    assert q.qid == "frame" and {c.row for c in q.chips} == {"Số ngày", "Đi với ai", "Đi lại bằng"}


def test_missing_frame_fields_are_asked_one_by_one(catalog, cfg):
    s = with_meta(up(TripState(), "days", 3), asked=("frame",))
    assert required(s, catalog, cfg).qid == "companions"


def test_effort_signal_beats_everything(catalog, cfg):
    s = up(TripState(), "signal", "knee", "add")
    q = required(s, catalog, cfg)
    assert q.qid == "c_effort" and q.exit_drafts


def test_thin_coverage_asks_unknown_policy_with_real_counts(catalog, cfg):
    s = up(framed(), "hard", {"feature": "steep_or_stairs", "op": "ne", "value": "present"}, "add")
    q = required(s, catalog, cfg)
    assert q.qid == "policy:steep_or_stairs" and "1 nơi" in q.text and "16 nơi" in q.text


def test_ambiguous_anchor_is_asked(catalog, cfg):
    s = up(framed(), "anchor", Anchor(text="Quán Yên", state="choose", candidates=("0x1:0x1", "0x2:0x1")), "add")
    q = required(s, catalog, cfg)
    assert q.qid == "anchor:0" and [c.drafts[0].value for c in q.chips][:2] == [(0, "0x1:0x1"), (0, "0x2:0x1")]


def test_anchor_closed_on_a_trip_day_is_a_conflict(catalog, cfg):
    s = up(framed(), "anchor", Anchor(text="Vườn", place_id="0x11:0x1", state="matched"), "add")
    q = required(s, catalog, cfg)
    assert q.qid == "closed:0" and "14/12" in q.text


def test_rank_prefers_questions_that_change_the_shortlist(catalog, cfg):
    scores = {q.qid: sc for q, sc in rank_questions(framed(), catalog, cfg)}
    assert scores["purpose"] > 0 and scores["pace"] == 0


def test_policy_ready_when_budget_is_spent(catalog, cfg):
    assert next_question(framed(adaptive_turns=5), catalog, cfg) is READY


def test_policy_ready_when_nothing_changes_results(catalog, cfg):
    s = framed(asked=("frame", "purpose", "vibe", "crowd", "pace", "max_leg", "budget", "times"))
    assert next_question(s, catalog, cfg) is READY


def test_unsure_twice_offers_show_first(catalog, cfg):
    assert next_question(framed(unsure_streak=2), catalog, cfg).qid == "show_first"


def test_clarify_uses_pending_keys(catalog, cfg):
    s = up(framed(), "pending", {"phrase": "chill", "keys": ["noise=quiet", "crowd=low"]}, "add")
    q = next_question(s, catalog, cfg)
    assert q.qid == "clarify:chill" and [c.label for c in q.chips] == ["Yên tĩnh", "Ít người"]


def test_first_timer_without_wishes_is_asked_purpose(catalog, cfg):
    assert next_question(framed(experience="first"), catalog, cfg).qid == "purpose"


def test_askable_contains_bank_and_ready(catalog, cfg):
    qs = askable(framed(), catalog, cfg)
    assert "purpose" in qs and "ready" in qs and {q.qid for q in bank(framed(), catalog, cfg)} <= set(qs)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest -q tests/trip/test_questions.py`
Expected: ERROR `No module named 'trip.policy'`.

- [ ] **Step 3: Implement `src/trip/questions.py`**

```python
"""Question bank, tier-1 rules and question value (docs/TRIP_UNDERSTANDING.md §7-8, Project_Context.md §12.2).

Every chip carries the updates it writes, so answering a chip never needs the model.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Literal

from .catalog import Catalog
from .coverage import Coverage, admissible, coverage
from .settings import Settings
from .state import (EFFORT_SIGNALS, OTHER_SIGNALS, Anchor, Draft, Frozen, Hard, SoftKey, TripState, apply_drafts,
                    ontology, pending_signals)


class Chip(Frozen):
    id: str
    label: str
    row: str | None = None
    drafts: tuple[Draft, ...] = ()


class Question(Frozen):
    qid: str
    group: str
    text: str
    reason: str = ""
    chips: tuple[Chip, ...] = ()
    multi: bool = False
    single_rows: tuple[str, ...] = ()  # rows of a multi question where only one chip may be on
    cost: float = 1.0
    tier: int = 3
    input: Literal["none", "text", "date", "place"] = "none"
    input_field: str | None = None
    exits: bool = True  # shows "Không chắc" / "Bỏ qua"
    exit_drafts: tuple[Draft, ...] = ()  # written when the user picks an exit
    custom: bool = False  # written by the agent; a chip answer goes back through the agent as text


def d(field: str, value=None, op: str = "set", inferred: bool = False) -> Draft:
    return Draft(field=field, op=op, value=value, inferred=inferred)


def soft(key: str) -> Draft:
    return d("soft", (key, "love"), "add", inferred=True)


WHO = {
    "solo": ("Một mình", (d("companions", "solo", "add"),)),
    "partner": ("Người yêu, vợ chồng", (d("companions", "partner", "add"), soft("couples=suitable"))),
    "friends": ("Bạn bè", (d("companions", "friends", "add"), soft("groups=suitable"))),
    "kids": ("Có trẻ nhỏ", (d("companions", "kids", "add"), d("signal", "kids", "add", True), soft("kids=suitable"))),
    "parents": ("Bố mẹ, người lớn tuổi",
                (d("companions", "parents", "add"), d("signal", "elderly", "add", True), soft("elderly=suitable"))),
}
VEHICLE = {"motorbike": "Xe máy", "car": "Ô tô riêng", "ride": "Grab, taxi"}
PURPOSE = {
    "relax": ("Nghỉ ngơi, thư giãn", (d("pace", "slow", inferred=True), soft("long_stay_chill=present"),
                                      soft("noise=quiet"))),
    "bond": ("Gắn kết người đi cùng", ()),
    "photo": ("Chụp ảnh", (soft("photo_spot=present"), soft("scenic_view=present"))),
    "food_culture": ("Ẩm thực, văn hóa", (soft("local_specialty_food=present"), soft("heritage_architecture=present"),
                                          soft("cultural_show=present"))),
    "nature": ("Thiên nhiên", (soft("nature=present"), soft("scenic_view=present"))),
    "explore": ("Khám phá nhiều nơi", (d("pace", "packed", inferred=True),)),
    "adventure": ("Trải nghiệm mạnh", (soft("adventure_activity=present"), soft("hiking=present"))),
}
VIBE = (("scenic_view=present", "View đồi núi"), ("cloud_hunting=present", "Săn mây"),
        ("nature=present", "Thiên nhiên, thác, rừng"), ("flower_garden=present", "Vườn hoa"),
        ("photo_spot=present", "Chụp ảnh đẹp"), ("long_stay_chill=present", "Ngồi lâu, chill"),
        ("pick_your_own=present", "Hái dâu, trái cây"), ("animals=present", "Có thú để chơi"),
        ("hiking=present", "Leo núi, trekking"), ("heritage_architecture=present", "Kiến trúc, di tích"),
        ("local_specialty_food=present", "Món đặc sản"), ("live_music=present", "Nhạc sống"))
SOFT_LABEL = dict(VIBE) | {
    "noise=quiet": "Yên tĩnh", "crowd=low": "Ít người", "scenic_view=present": "Có view",
    "cozy_decor=present": "Không gian ấm cúng", "drink_quality=good": "Đồ uống ngon", "food_quality=good": "Đồ ăn ngon",
    "cultural_show=present": "Biểu diễn văn hóa", "long_stay_chill=present": "Ngồi lâu được",
}
HARD_LABEL = {"steep_or_stairs": "tránh dốc và bậc thang", "long_walk": "không phải đi bộ xa",
              "vegetarian_options": "có món chay"}
WEEKDAY = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

READY = Question(qid="ready", group="I", tier=0, exits=False,
                 text="Mình đã hiểu đủ để tìm chỗ hợp với chuyến này. Xem gợi ý nhé? Bạn vẫn sửa được mọi dòng bên cạnh.",
                 chips=(Chip(id="show", label="Xem gợi ý"),))


# ---------- tier 1 ----------

def frame(state: TripState) -> Question:
    text = "Kể mình nghe chuyến đi bạn đang tính: đi mấy ngày, với ai, muốn trải nghiệm gì. Gõ tự nhiên, hoặc chọn nhanh bên dưới."
    if state.meta.start_with in ("saved", "must", "itinerary"):
        text += " Có sẵn nơi muốn đến thì dán tên hoặc link vào ô, mỗi dòng một nơi."
    chips = tuple(Chip(id=f"days:{n}", label=f"{n} ngày", row="Số ngày", drafts=(d("days", n),)) for n in (2, 3, 4, 5))
    chips += tuple(Chip(id=f"who:{k}", label=label, row="Đi với ai", drafts=dr) for k, (label, dr) in WHO.items())
    chips += tuple(Chip(id=f"mobility:{k}", label=label, row="Đi lại bằng", drafts=(d("mobility", k),))
                   for k, label in VEHICLE.items())
    return Question(qid="frame", group="A", tier=1, multi=True, single_rows=("Số ngày", "Đi lại bằng"), input="text",
                    exits=False, text=text, reason="Ba điều này quyết định nơi nào hợp và lịch có đi kịp không.",
                    chips=chips)


def days_q() -> Question:
    return Question(qid="days", group="A", tier=1, text="Chuyến này bạn đi mấy ngày?",
                    reason="Số ngày quyết định đi được bao nhiêu nơi.",
                    chips=tuple(Chip(id=f"days:{n}", label=f"{n} ngày", drafts=(d("days", n),)) for n in (1, 2, 3, 4, 5)))


def companions_q() -> Question:
    return Question(qid="companions", group="B", tier=1, multi=True, text="Bạn đi cùng ai?",
                    reason="Đi cùng ai đổi mạnh nơi nào hợp.",
                    chips=tuple(Chip(id=f"who:{k}", label=label, drafts=dr) for k, (label, dr) in WHO.items()))


def mobility_q() -> Question:
    return Question(qid="mobility", group="A", tier=1, text="Bạn đi lại trong Đà Lạt bằng gì?",
                    reason="Để ước lượng thời gian giữa các nơi.",
                    chips=tuple(Chip(id=f"mobility:{k}", label=label, drafts=(d("mobility", k),))
                                for k, label in VEHICLE.items()))


def dates_q() -> Question:
    return Question(qid="dates", group="A", tier=1, input="date", input_field="start_date", exits=False,
                    text="Bạn đi từ ngày nào?", reason="Để kiểm tra giờ mở cửa đúng ngày bạn đi.",
                    chips=(Chip(id="undecided", label="Chưa chốt ngày", drafts=(d("start_date", op="remove"),)),))


def c_effort(state: TripState) -> Question:
    kinds = {s.kind for s in pending_signals(state)}
    who = "người lớn tuổi" if kinds & {"elderly", "knee"} else "trẻ nhỏ" if "kids" in kinds else "người trong nhóm"
    handled = d("signal_handled", tuple(sorted(EFFORT_SIGNALS)))
    steep = d("hard", {"feature": "steep_or_stairs", "op": "ne", "value": "present"}, "add")
    walk = d("hard", {"feature": "long_walk", "op": "ne", "value": "present"}, "add")
    return Question(
        qid="c_effort", group="C", tier=1,
        text="Để tránh chỗ phải leo dốc: trong nhóm có ai ngại đi bộ xa hoặc lên nhiều bậc thang không? Bạn có thể bỏ qua.",
        reason=f"Đi cùng {who}, chỗ nhiều bậc dễ làm mệt cả buổi.",
        chips=(Chip(id="steep", label="Tránh dốc, bậc thang", drafts=(steep, handled)),
               Chip(id="walk", label="Không đi bộ xa", drafts=(walk, handled)),
               Chip(id="both", label="Tránh cả hai", drafts=(steep, walk, handled)),
               Chip(id="fine", label="Đi lại bình thường", drafts=(handled,))),
        exit_drafts=(handled,))


def c_other(state: TripState) -> Question:
    kinds = {s.kind for s in pending_signals(state)}
    chips = []
    if "vegetarian" in kinds:
        chips.append(Chip(id="veg", label="Cần quán có món chay", drafts=(
            d("hard", {"feature": "vegetarian_options", "op": "eq", "value": "yes"}, "add"),
            d("signal_handled", ("vegetarian",)))))
    if "motion_sick" in kinds:
        chips.append(Chip(id="pass", label="Tránh đường đèo dài", drafts=(
            d("unmapped", "tránh đường đèo dài (say xe)", "add"), d("signal_handled", ("motion_sick",)))))
    if "height" in kinds:
        chips.append(Chip(id="height", label="Tránh chỗ cao, cầu kính", drafts=(
            d("unmapped", "tránh chỗ cao, cầu kính", "add"), d("signal_handled", ("height",)))))
    handled = d("signal_handled", tuple(sorted(OTHER_SIGNALS)))
    chips.append(Chip(id="none", label="Không cần lọc", drafts=(handled,)))
    return Question(qid="c_other", group="C", tier=1, multi=True, text="Mình nên lưu ý gì để chuyến đi dễ chịu hơn?",
                    reason="Bạn vừa nhắc tới sức khỏe hoặc ăn uống; chọn để mình lọc đúng.", chips=tuple(chips),
                    exit_drafts=(handled,))


def policy_q(h: Hard, cov: Coverage) -> Question:
    label = HARD_LABEL.get(h.feature, h.feature)
    known = f"chỉ {cov.passed} nơi xác minh được" if cov.passed else "chưa nơi nào xác minh được"
    exclude, flag = d("hard_policy", (h.feature, "exclude")), d("hard_policy", (h.feature, "flag"))
    return Question(qid=f"policy:{h.feature}", group="C", tier=1,
                    text=f"Để {label}: {known}, {cov.unknown} nơi chưa có thông tin. Bạn muốn?",
                    reason="Mình không coi nơi chưa có thông tin là an toàn.",
                    chips=(Chip(id="exclude", label="Chỉ nơi đã xác minh", drafts=(exclude,)),
                           Chip(id="flag", label="Xem cả nơi chưa rõ, gắn cờ", drafts=(flag,))),
                    exit_drafts=(exclude,))


def anchor_pick(i: int, a: Anchor, catalog: Catalog) -> Question:
    chips = tuple(Chip(id=pid, label=catalog.by_id[pid].name, drafts=(d("anchor_pick", (i, pid)),))
                  for pid in a.candidates if pid in catalog.by_id)
    none = d("anchor_pick", (i, None))
    return Question(qid=f"anchor:{i}", group="E", tier=1, text=f"“{a.text}” là nơi nào?",
                    reason="Tên này khớp nhiều nơi; mình không đoán.",
                    chips=chips + (Chip(id="none", label="Không phải nơi nào ở đây", drafts=(none,)),),
                    exit_drafts=(none,))


def closed_conflict(state: TripState, catalog: Catalog) -> Question | None:
    start, days = state.start_date.value, state.days.value or 1
    if start is None:
        return None
    for i, a in enumerate(state.anchors):
        c = catalog.by_id.get(a.place_id or "")
        if a.state != "matched" or c is None or c.hours is None or f"closed:{i}" in state.meta.asked:
            continue
        closed = [day for k in range(days) if (day := start + timedelta(k)) and c.hours.get(WEEKDAY[day.weekday()]) == ()]
        if closed:
            when = ", ".join(x.strftime("%d/%m") for x in closed)
            return Question(qid=f"closed:{i}", group="E", tier=1, exits=False,
                            text=f"{c.name} đóng cửa ngày {when} trong chuyến của bạn. Bạn muốn?",
                            reason="Theo giờ mở cửa trên Google Maps.",
                            chips=(Chip(id="redate", label="Đổi ngày đi", drafts=(d("start_date", op="remove", inferred=True),)),
                                   Chip(id="drop", label="Bỏ nơi này", drafts=(d("anchor", i, "remove"),)),
                                   Chip(id="keep", label="Vẫn giữ, xếp vào ngày khác")))
    return None


def required(state: TripState, catalog: Catalog, cfg: Settings) -> Question | None:
    """Tier 1: safety, blocking fields, ambiguous anchors, real conflicts. The guard forces these."""
    skipped, asked = state.meta.skipped, state.meta.asked
    pending = {s.kind for s in pending_signals(state)}
    if pending & EFFORT_SIGNALS:
        return c_effort(state)
    if pending & OTHER_SIGNALS:
        return c_other(state)
    for h in state.hard:
        if h.unknown_policy is None:
            cov = coverage(h, catalog.places, cfg.enough)
            if cov.level != "enough":
                return policy_q(h, cov)
    for i, a in enumerate(state.anchors):
        if a.state == "choose":
            return anchor_pick(i, a, catalog)
    if "frame" not in asked and not (state.days.known and state.companions.known and state.mobility.known):
        return frame(state)
    for field, build in (("days", days_q), ("companions", companions_q), ("mobility", mobility_q)):
        if not getattr(state, field).known and field not in skipped:
            return build()
    if not (state.start_date.known or state.month.known or state.start_date.status == "skipped" or "dates" in skipped):
        return dates_q()
    return closed_conflict(state, catalog)


# ---------- tier 2-3 ----------

def purpose_q() -> Question:
    return Question(qid="purpose", group="G", tier=2, text="Chuyến này chủ yếu để làm gì?",
                    reason="Biết mục đích, mình chọn đúng kiểu nơi hơn.",
                    chips=tuple(Chip(id=k, label=label, drafts=(d("purpose", k),) + dr)
                                for k, (label, dr) in PURPOSE.items()))


def vibe_q(catalog: Catalog, cfg: Settings) -> Question | None:
    chips = tuple(Chip(id=key, label=label, drafts=(d("soft", (key, "love"), "add"),))
                  for key, label in VIBE if catalog.count(key) >= cfg.top_k)
    if len(chips) < 2:
        return None
    return Question(qid="vibe", group="G", multi=True, cost=1.2, chips=chips,
                    text="Bạn muốn có những khoảnh khắc nào? Chọn bao nhiêu cũng được.",
                    reason="Chỉ hiện những kiểu mình có đủ đánh giá để kiểm.")


def clarify_q(state: TripState) -> Question | None:
    if not state.meta.pending:
        return None
    a = state.meta.pending[0]
    done = d("pending", a.phrase, "remove")
    return Question(qid=f"clarify:{a.phrase}", group="I", tier=2, multi=True,
                    text=f"“{a.phrase}” với bạn là gì? Chọn những ý đúng.",
                    reason="Mỗi người hiểu từ này một kiểu, mình hỏi để không đoán sai.",
                    chips=tuple(Chip(id=f"k{i}", label=SOFT_LABEL.get(k, k), drafts=(d("soft", (k, "love"), "add"), done))
                                for i, k in enumerate(a.keys)),
                    exit_drafts=(done,))


def show_first_q() -> Question:
    return Question(qid="show_first", group="I", tier=2, exits=False,
                    text="Bạn muốn xem vài gợi ý trước rồi chỉnh tiếp không?",
                    chips=(Chip(id="show", label="Xem gợi ý"), Chip(id="more", label="Hỏi tiếp")))


def bank(state: TripState, catalog: Catalog, cfg: Settings) -> list[Question]:
    done = set(state.meta.asked) | state.meta.skipped
    out: list[Question] = []

    def want(qid: str, cond: bool) -> bool:
        return cond and qid not in done

    if want("purpose", not state.purpose.known):
        out.append(purpose_q())
    experience = ontology().features
    has_wish = any(f.value == "love" and experience[SoftKey.parse(k).feature].group == "experience"
                   for k, f in state.soft.items())
    if want("vibe", not has_wish) and (q := vibe_q(catalog, cfg)):
        out.append(q)
    if want("crowd", not state.crowd_tolerance.known):
        out.append(Question(qid="crowd", group="F", text="Chỗ đông người thì sao?",
                            reason="Nhiều nơi đẹp nhưng rất đông vào giờ cao điểm.", chips=(
                Chip(id="avoid", label="Tránh chỗ đông", drafts=(d("crowd_tolerance", "avoid"),
                                                                 d("soft", ("crowd=low", "love"), "add"))),
                Chip(id="ok", label="Chấp nhận nếu đáng", drafts=(d("crowd_tolerance", "ok_if_worth"),)),
                Chip(id="fine", label="Không ngại", drafts=(d("crowd_tolerance", "fine"),)))))
    if want("pace", not state.pace.known):
        out.append(Question(qid="pace", group="F", text="Mỗi ngày bạn muốn đi thế nào?",
                            reason="Để xếp số nơi mỗi ngày vừa sức.", chips=(
                Chip(id="slow", label="Thong thả, ít nơi", drafts=(d("pace", "slow"),)),
                Chip(id="normal", label="Vừa phải", drafts=(d("pace", "normal"),)),
                Chip(id="packed", label="Đi được nhiều", drafts=(d("pace", "packed"),)))))
    if want("max_leg", not state.max_leg_min.known):
        out.append(Question(qid="max_leg", group="F", text="Một chặng di chuyển tối đa bao lâu thì bạn vẫn thấy ổn?",
                            reason="Đà Lạt đường đèo, nơi xa có thể mất cả tiếng.",
                            chips=tuple(Chip(id=str(m), label=f"Dưới {m} phút", drafts=(d("max_leg_min", m),))
                                        for m in (15, 30, 60))))
    if want("budget", not state.budget_vnd.known):
        out.append(Question(qid="budget", group="D", cost=2.0,
                            text="Mức chi cho ăn uống và vé, mỗi người mỗi ngày khoảng bao nhiêu? Bạn có thể bỏ qua.",
                            reason="Để tránh nơi vượt mức bạn muốn chi.", chips=(
                Chip(id="low", label="Dưới 300 nghìn", drafts=(d("budget_vnd", 300_000),)),
                Chip(id="mid", label="300–700 nghìn", drafts=(d("budget_vnd", 700_000),)),
                Chip(id="high", label="Trên 700 nghìn", drafts=(d("budget_vnd", 1_500_000),)))))
    if want("novelty", state.meta.experience == "returning" and not state.novelty.known):
        out.append(Question(qid="novelty", group="H", text="Lần này bạn muốn quay lại chỗ quen hay thử cái mới?",
                            reason="Để bớt những nơi bạn đã đi.", chips=(
                Chip(id="familiar", label="Theo gu quen", drafts=(d("novelty", "familiar"),)),
                Chip(id="new", label="Thử cái mới", drafts=(d("novelty", "new"),)),
                Chip(id="mix", label="Trộn cả hai", drafts=(d("novelty", "mix"),)))))
    matched = [(i, a) for i, a in enumerate(state.anchors) if a.state == "matched"]
    if want("base", not state.base.known and (len(matched) >= 2 or state.max_leg_min.known)):
        out.append(Question(qid="base", group="A", cost=1.5, input="place", input_field="base",
                            text="Bạn ở khu nào? Chọn một nơi gần chỗ ở.", reason="Để tính đường đi mỗi ngày."))
    if want("times", state.days.known and not state.arrive_at.known):
        out.append(Question(qid="times", group="A", multi=True, single_rows=("Ngày đầu tới lúc", "Ngày cuối rời lúc"),
                            text="Ngày đầu bạn tới lúc nào, ngày cuối rời Đà Lạt lúc nào?",
                            reason="Để không xếp lịch trùng giờ xe.",
                            chips=tuple(Chip(id=f"arrive:{h}", label=f"{h}h", row="Ngày đầu tới lúc",
                                             drafts=(d("arrive_at", f"{h:02d}:00"),)) for h in (7, 9, 12, 15))
                            + tuple(Chip(id=f"leave:{h}", label=f"{h}h", row="Ngày cuối rời lúc",
                                         drafts=(d("leave_at", f"{h:02d}:00"),)) for h in (12, 15, 19))))
    if want("anchor_priority", len(matched) >= 2 and all(a.priority == "must" for _, a in matched)):
        out.append(Question(qid="anchor_priority", group="E", multi=True, cost=1.2,
                            text="Nếu không đủ thời gian, nơi nào có thể bỏ trước?",
                            reason="Để biết nơi nào phải giữ bằng mọi giá.",
                            chips=tuple(Chip(id=f"a{i}", label=catalog.by_id[a.place_id].name,
                                             drafts=(d("anchor_priority", (i, "want")),))
                                        for i, a in matched if a.place_id in catalog.by_id)))
    return out


def shortlist(state: TripState, catalog: Catalog, cfg: Settings) -> list[str]:
    weights = []
    for key, f in state.soft.items():
        if f.value in ("love", "avoid"):
            weights.append((SoftKey.parse(key), 1 if f.value == "love" else -1))
    skip = set(state.visited) if state.novelty.value == "new" else set()
    scored = []
    for c in catalog.places:
        if c.id in skip or not admissible(c, state.hard):
            continue
        s = sum(w for k, w in weights if c.value(k.feature, k.context) == k.value)
        scored.append((-s, -c.weight, c.id))
    scored.sort()
    return [pid for *_, pid in scored[:cfg.top_k]]


def rank_questions(state: TripState, catalog: Catalog, cfg: Settings) -> list[tuple[Question, float]]:
    """impact = mean over chips of how much the top-K changes; score = impact / cost (docs/TRIP_UNDERSTANDING.md §8)."""
    now = set(shortlist(state, catalog, cfg))
    out = []
    for q in bank(state, catalog, cfg):
        chips = [c for c in q.chips if c.drafts]
        if not chips:
            out.append((q, 0.0))
            continue
        impact = 0.0
        for chip in chips:
            alt = set(shortlist(apply_drafts(state, chip.drafts, state.meta.turn, f"rank:{q.qid}"), catalog, cfg))
            union = now | alt
            impact += 1 - len(now & alt) / len(union) if union else 0.0
        out.append((q, impact / len(chips) / q.cost))
    return sorted(out, key=lambda x: -x[1])
```

Note on `closed_conflict`: the walrus inside the comprehension condition must stay truthy; `date` objects are always truthy, so `(day := ...) and ...` works.

- [ ] **Step 4: Implement `src/trip/policy.py`**

```python
"""Deterministic choice of the next question (docs/TRIP_UNDERSTANDING.md §7, §9). Used for chips, edits, and as the
fallback when the agent fails."""

from .catalog import Catalog
from .questions import READY, Question, bank, clarify_q, purpose_q, rank_questions, required, show_first_q
from .settings import Settings
from .state import TripState


def next_question(state: TripState, catalog: Catalog, cfg: Settings) -> Question:
    req = required(state, catalog, cfg)
    if req:
        return req
    done = set(state.meta.asked) | state.meta.skipped
    if state.meta.unsure_streak >= 2 and "show_first" not in done:
        return show_first_q()
    if state.meta.adaptive_turns >= cfg.turn_budget:
        return READY
    if q := clarify_q(state):
        return q
    if state.meta.experience == "first" and not state.purpose.known and not state.soft and "purpose" not in done:
        return purpose_q()
    ranked = rank_questions(state, catalog, cfg)
    if ranked and ranked[0][1] >= cfg.stop_score:
        return ranked[0][0]
    return READY


def askable(state: TripState, catalog: Catalog, cfg: Settings) -> dict[str, Question]:
    """Questions the agent may pick by qid this turn (tier 1 is handled separately by the guard)."""
    qs = bank(state, catalog, cfg)
    if q := clarify_q(state):
        qs.append(q)
    qs += [show_first_q(), READY]
    if not state.purpose.known:
        qs.append(purpose_q())
    return {q.qid: q for q in qs}
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest -q tests/trip`
Expected: all pass. `test_rank_prefers_questions_that_change_the_shortlist` needs `purpose` to move the top-4 (relax → quiet cafés) and `pace` to move nothing.

- [ ] **Step 6: Commit**

```bash
git add src/trip/questions.py src/trip/policy.py tests/trip/test_questions.py
git commit -m "feat(trip): question bank, tier-1 rules and value-of-question ranking"
```

---

### Task 5: Compile Search Input and the understanding view

**Files:**
- Create: `src/trip/compile.py`, `src/trip/understanding.py`
- Test: `tests/trip/test_compile.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: `compile.UnhandledSignal`, `compile.compile_search_input(state) -> SearchInput`; `understanding.view(state, catalog, cfg) -> dict` with keys `purpose, trip, anchors, hard, soft, pace, max_leg_min, crowd_tolerance, novelty, budget_vnd, unknowns, unmapped, safety_pending`.

- [ ] **Step 1: Write failing tests**

`tests/trip/test_compile.py`:

```python
from datetime import date

import pytest

from trip.compile import UnhandledSignal, compile_search_input
from trip.state import Evidence, TripState, Update, apply
from trip.understanding import view

EV = Evidence(turn=1, quote="x")


def up(s, field, value=None, op="set", source="user"):
    return apply(s, Update(field=field, op=op, value=value, source=source,
                           confidence="high" if source == "user" else "medium", evidence=EV))


def doc_example():
    """docs/TRIP_UNDERSTANDING.md §15."""
    s = up(TripState(), "start_date", date(2026, 12, 12))
    s = up(up(up(s, "days", 3), "companions", "parents", "add"), "mobility", "car")
    s = up(s, "signal", "elderly", "add", source="inferred")
    for f in ("steep_or_stairs", "long_walk"):
        s = up(s, "hard", {"feature": f, "op": "ne", "value": "present"}, "add")
        s = up(s, "hard_policy", (f, "flag"))
    for k in ("long_stay_chill=present", "noise=quiet", "crowd=low"):
        s = up(s, "soft", (k, "love"), "add")
    s = up(s, "soft", ("scenic_view=present", "love"), "add", source="anchor")
    s = up(s, "soft", ("hiking=present", "off"), "add")
    s = up(s, "pace", "slow", source="inferred")
    s = up(up(s, "novelty", "new"), "unmapped", "nhạc nhẹ", "add")
    from trip.state import settle
    return settle(s)


def test_doc_example_compiles():
    si = compile_search_input(doc_example())
    assert si.context.days == 3 and si.context.companions == ("parents",) and si.context.mobility == "car"
    assert {(h.feature, h.unknown_policy) for h in si.hard_filters} == {("steep_or_stairs", "flag"), ("long_walk", "flag")}
    assert {(w.feature, w.value, w.weight, w.source) for w in si.soft_weights} >= {
        ("noise", "quiet", 1, "user"), ("scenic_view", "present", 1, "anchor"), ("hiking", "present", 0, "user")}
    assert si.pace.level == "slow" and si.novelty.level == "new"
    assert "budget_vnd" in si.unknowns and si.unmapped == ("nhạc nhẹ",)


def test_unhandled_signal_blocks_compile():
    with pytest.raises(UnhandledSignal):
        compile_search_input(up(TripState(), "signal", "knee", "add"))


def test_unknown_policy_defaults_to_exclude():
    s = up(TripState(), "hard", {"feature": "vegetarian_options", "op": "eq", "value": "yes"}, "add")
    assert compile_search_input(s).hard_filters[0].unknown_policy == "exclude"


def test_view_marks_inferred_and_counts_coverage(catalog, cfg):
    v = view(doc_example(), catalog, cfg)
    assert v["pace"]["mark"] is True and v["trip"][0]["target"] == "start_date"
    assert v["hard"][0]["coverage"]["passed"] == 1
    assert {r["key"] for r in v["soft"]} >= {"noise=quiet"} and v["unmapped"][0]["phrase"] == "nhạc nhẹ"
    assert v["safety_pending"] is False
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest -q tests/trip/test_compile.py`
Expected: ERROR `No module named 'trip.compile'`.

- [ ] **Step 3: Implement**

`src/trip/compile.py`:

```python
"""Trip State -> Search Input (docs/TRIP_UNDERSTANDING.md §11). Deterministic; refuses while a physical signal is open."""

from .state import (AnchorRef, Context, HardFilter, NoveltySpec, PaceSpec, SearchInput, SoftKey, SoftWeight, TripState,
                    WEIGHT_SIGN, ontology, pending_signals, unknown_fields)


class UnhandledSignal(Exception):
    """A health / body / diet hint has not been answered yet (docs/ARCHITECTURE.md §18.3)."""


def compile_search_input(state: TripState) -> SearchInput:
    pending = pending_signals(state)
    if pending:
        raise UnhandledSignal(", ".join(s.kind for s in pending))

    def v(field):
        return getattr(state, field).value

    soft = []
    for key, f in sorted(state.soft.items()):
        if f.known:
            k = SoftKey.parse(key)
            soft.append(SoftWeight(feature=k.feature, value=k.value, context=dict(k.context) or None,
                                   weight=WEIGHT_SIGN[f.value], source=f.source))
    return SearchInput(
        ontology_version=ontology().version,
        context=Context(start_date=v("start_date"), month=v("month"), days=v("days"), base=v("base"),
                        mobility=v("mobility"), companions=tuple(sorted(v("companions") or ())), people=v("people"),
                        arrive_at=v("arrive_at"), leave_at=v("leave_at"), day_end=v("day_end")),
        hard_filters=tuple(HardFilter(feature=h.feature, op=h.op, value=h.value,
                                      unknown_policy=h.unknown_policy or "exclude") for h in state.hard),
        anchors=tuple(AnchorRef(place_id=a.place_id, priority=a.priority)
                      for a in state.anchors if a.state == "matched" and a.place_id),
        soft_weights=tuple(soft),
        pace=PaceSpec(level=v("pace"), max_leg_min=v("max_leg_min"), crowd_tolerance=v("crowd_tolerance")),
        novelty=NoveltySpec(level=v("novelty"), visited=state.visited),
        unknowns=tuple(unknown_fields(state)),
        unmapped=tuple(u.phrase for u in state.unmapped))
```

`src/trip/understanding.py`:

```python
"""Trip State -> the understanding panel (docs/TRIP_UNDERSTANDING.md §10). Data only; the web writes the words."""

from dataclasses import asdict

from .catalog import Catalog
from .coverage import coverage
from .settings import Settings
from .state import SoftKey, TripState, pending_signals, unknown_fields
from .values import jsonable

MARKED = ("inferred", "anchor", "profile")
TRIP_ROWS = ("start_date", "month", "days", "companions", "people", "base", "mobility", "arrive_at", "leave_at", "day_end")


def view(state: TripState, catalog: Catalog, cfg: Settings) -> dict:
    def row(target: str) -> dict | None:
        f = getattr(state, target)
        if not f.known:
            return None
        value = jsonable(f.value)
        if target == "base" and f.value.place_id in catalog.by_id:
            value["name"] = catalog.by_id[f.value.place_id].name
        return {"target": target, "value": value, "mark": f.source in MARKED, "confidence": f.confidence}

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
    }
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest -q tests/trip`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/trip/compile.py src/trip/understanding.py tests/trip/test_compile.py
git commit -m "feat(trip): compile Search Input and the understanding view"
```

---

### Task 6: AGENT role, TRIP_TURN task, streaming agent, guard

**Files:**
- Modify: `src/corpus/llm/roles.py`, `src/corpus/llm/tasks.py`, `src/corpus/llm/__init__.py`, `.env.example`
- Create: `src/trip/agent.py`, `src/trip/guard.py`
- Test: `tests/trip/test_agent.py`, `tests/trip/test_guard.py`, `tests/trip/test_live.py`

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces: `corpus.llm.AGENT`, `corpus.llm.TRIP_TURN`, `Task.stream(client, model, **fields) -> AsyncIterator[str]`, `corpus.llm.tasks.TRIP_FIELDS`. `agent.AgentError`, `agent.SayStream`, `agent.prompt_fields(state, text, pre, required, ranked, cfg, last_question, today) -> dict`, `agent.run_agent(fields, on_say, cfg, open_stream=gemma_stream) -> TurnPlan`. `guard.PlanUpdate/PlanNext/TurnPlan`, `guard.Guarded(state, question, say, log)`, `guard.guard(plan, state, text, turn, catalog, cfg, heard) -> Guarded`.

- [ ] **Step 1: Role, task, stream**

`src/corpus/llm/roles.py` — append:

```python
AGENT = Role(
    name="agent",
    purpose="live conversation turns: one streamed structured call per user message (src/trip)",
    key_env="AGENT_API_KEY", base_url_env="AGENT_BASE_URL", model_env="AGENT_MODEL",
)
```

`src/corpus/llm/tasks.py`: change the import to `from .roles import AGENT, EXTRACTOR, JUDGE, Role`; add to class `Task` after `ask`:

```python
    async def stream(self, client, model: str, **fields):
        """Text deltas of one streamed call. No retry: a live turn falls back instead of waiting."""
        s = await client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": self.render(**fields)}],
            temperature=self.temperature, max_tokens=self.max_tokens, stream=True,
            response_format={"type": "json_schema", "json_schema": {"name": self.name, "schema": self.schema,
                                                                    "strict": True}})
        async for chunk in s:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
```

Append at the end of `tasks.py`:

```python
TRIP_FIELDS = ["start_date", "month", "days", "companions", "people", "base", "mobility", "arrive_at", "leave_at",
               "day_end", "purpose", "anchor", "signal", "soft", "hard", "pace", "max_leg_min", "crowd_tolerance",
               "novelty", "budget_vnd", "unmapped"]

TRIP_TURN = Task(
    name="trip_turn",
    role=AGENT,
    max_tokens=900,
    temperature=0.2,
    parallel=4,
    # `say` first: the server streams it to the user before the structured part arrives (src/trip/agent.py).
    schema={
        "type": "object",
        "properties": {
            "say": {"type": "string"},
            "updates": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string", "enum": TRIP_FIELDS},
                    "op": {"type": "string", "enum": ["set", "add", "remove"]},
                    "value": {"type": "string"},
                    "quote": {"type": "string"},
                    "how": {"type": "string", "enum": ["said", "inferred"]},
                },
                "required": ["field", "op", "value", "quote", "how"],
                "additionalProperties": False,
            }},
            "next": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["ask", "stop"]},
                    "qid": {"type": "string"},
                    "custom_text": {"type": "string"},
                    "custom_chips": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
                "required": ["kind", "qid", "custom_text", "custom_chips", "reason"],
                "additionalProperties": False,
            },
        },
        "required": ["say", "updates", "next"],
        "additionalProperties": False,
    },
    prompt="""You help a traveller prepare a trip to Đà Lạt, Vietnam. In this turn: understand the user's latest
message, record what it says about the trip, and choose the next question. Never suggest places in this step.

`say` (Vietnamese): 1-2 short sentences, warm but not chummy, "mình" for yourself and "bạn" for the user, no slang,
no emoji. Acknowledge what you understood, then lead into the next question. Never name a place. Never state a number
or fact the user did not say. The question and its options appear on a card under your text, so do not list options.

`updates`: one entry per fact in the user's message.
- field: one of the allowed fields. op: set for one value; add / remove for lists (companions, anchor, signal, soft,
  hard, unmapped).
- value formats:
  start_date YYYY-MM-DD (today is {today}; a date already past means next year) | month 1-12 | days 1-7 | people
  companions solo|partner|friends|kids|parents | mobility motorbike|car|ride | arrive_at, leave_at, day_end HH:MM
  purpose relax|bond|photo|food_culture|nature|explore|adventure | pace slow|normal|packed | max_leg_min minutes
  crowd_tolerance avoid|ok_if_worth|fine | novelty familiar|new|mix | budget_vnd VND per person per day
  base: the area or place the user stays at, in their words | anchor: one place name or link they must visit
  signal: knee|elderly|kids|wheelchair|pregnant|motion_sick|height|vegetarian (health, body or diet hints)
  soft: feature=value[@context_key.context_value]:love|avoid, ids from FEATURES only
  hard: feature!=value or feature=value, only for what must not / must happen
  unmapped: a wish FEATURES cannot express, in the user's words
- quote: the exact words from the user's message that support the update, copied, not paraphrased.
- how: said when the user stated it; inferred when you concluded it (e.g. "đi với bố mẹ" -> signal elderly, inferred).
- A subjective word with several meanings ("chill", "đẹp", "vui"): do not guess a feature; ask what it means.
- When unsure, leave it out. A missing value is fine; a wrong one is not.

`next`:
- If REQUIRED is not "none": kind ask, qid = its id.
- Otherwise follow the user's thread: clarify a subjective word, or ask why they want a place they named (at most
  twice), using custom_text + 2-6 short custom_chips naming concrete things; or pick a qid from CANDIDATES; or kind
  stop when nothing left would change the result (BUDGET 0 means stop).
- reason: why the question matters, Vietnamese, one short clause, shown to the user.
- Unused fields: "" or [].

FEATURES (id: values - meaning)
{features}

TRIP STATE
{state}

LAST QUESTION SHOWN: {last_question}
EXPERIENCE WITH ĐÀ LẠT: {experience}
KEYWORD MATCHES (deterministic, may be wrong): {prepass}
REQUIRED: {required}
CANDIDATES:
{candidates}
BUDGET: {budget}

USER MESSAGE:
{text}""",
)
```

`src/corpus/llm/__init__.py`: export `AGENT` and `TRIP_TURN` (add to both import lines and `__all__`).

`.env.example`: append

```
# Agent role: live Trip Understanding turns (python -m trip serve); Gemma on UIT API, same key as Extractor
AGENT_API_KEY=
AGENT_BASE_URL=https://llm.uit.edu.vn/gemma/v1
AGENT_MODEL=gemma-4-26b
```

Local `.env` (never print the key): add the same three lines with the key copied from `LLM_API_KEY`:

```bash
python - <<'EOF'
from dotenv import dotenv_values
env = dotenv_values(".env")
if "AGENT_MODEL" not in env:
    with open(".env", "a", encoding="utf-8") as f:
        f.write(f"\n# Agent role (Trip Understanding)\nAGENT_API_KEY={env['LLM_API_KEY']}\n"
                f"AGENT_BASE_URL={env['EXTRACTOR_BASE_URL']}\nAGENT_MODEL={env['EXTRACTOR_MODEL']}\n")
EOF
```

- [ ] **Step 2: Write failing tests**

`tests/trip/test_agent.py`:

```python
import asyncio
import json
from datetime import date

import pytest

from corpus.llm import TRIP_TURN
from corpus.llm.tasks import TRIP_FIELDS
from trip.agent import AgentError, SayStream, prompt_fields, run_agent
from trip.guard import PlanUpdate
from trip.prepass import prepass
from trip.questions import c_effort
from trip.settings import Settings
from trip.state import TripState, ontology

PLAN = {"say": "Mình hiểu rồi.", "updates": [], "next": {"kind": "ask", "qid": "pace", "custom_text": "",
                                                       "custom_chips": [], "reason": ""}}


def test_say_stream_handles_split_escapes():
    s, out = SayStream(), []
    for piece in ['{"say": "Chào b', 'ạn \\"x\\" và \\u00', 'e0 nhé", "upd', 'ates": []}']:
        out.append(s.feed(piece))
    assert "".join(out) == 'Chào bạn "x" và à nhé'


def test_prompt_renders_with_every_field():
    st = TripState()
    f = prompt_fields(st, "đi 3 ngày", prepass("đi 3 ngày", date(2026, 10, 2)), c_effort(st), [], Settings(),
                      "Câu trước?", date(2026, 10, 2))
    text = TRIP_TURN.render(**f)
    assert "REQUIRED: c_effort" in text and "đi 3 ngày" in text
    assert all(fid in text for fid in ontology().features)


def test_schema_fields_match_the_guard():
    assert set(TRIP_FIELDS) == set(PlanUpdate.model_fields["field"].annotation.__args__)


def fake(chunks, delay=0.0):
    def open_stream(fields):
        async def gen():
            for c in chunks:
                await asyncio.sleep(delay)
                yield c
        return gen()
    return open_stream


def test_run_agent_streams_say_and_returns_plan():
    raw = json.dumps(PLAN, ensure_ascii=False)
    said = []
    plan = asyncio.run(run_agent({}, said.append, Settings(), open_stream=fake([raw[:12], raw[12:30], raw[30:]])))
    assert "".join(said) == "Mình hiểu rồi." and plan.next.qid == "pace"


def test_run_agent_times_out_on_first_token():
    with pytest.raises(AgentError):
        asyncio.run(run_agent({}, lambda s: None, Settings(first_token_s=0.05), open_stream=fake(["{}"], delay=0.5)))


def test_run_agent_rejects_bad_json():
    with pytest.raises(AgentError):
        asyncio.run(run_agent({}, lambda s: None, Settings(), open_stream=fake(['{"say": "x"'])))
```

`tests/trip/test_guard.py`:

```python
from trip.guard import PlanNext, PlanUpdate, TurnPlan, guard
from trip.state import Evidence, TripState, Update, apply, with_meta

TEXT = "Tháng 12 đi 3 ngày với bố mẹ, muốn yên tĩnh"


def plan(*updates, say="Mình ghi lại rồi.", **nxt):
    n = {"kind": "ask", "qid": "", "custom_text": "", "custom_chips": (), "reason": ""} | nxt
    return TurnPlan(say=say, updates=tuple(PlanUpdate(**u) for u in updates), next=PlanNext(**n))


def u(field, value, quote, op="set", how="said"):
    return {"field": field, "op": op, "value": value, "quote": quote, "how": how}


def framed():
    ev = Evidence(turn=1, quote="x")
    s = TripState()
    for f, v, op in (("days", 3, "set"), ("companions", "solo", "add"), ("mobility", "car", "set")):
        s = apply(s, Update(field=f, op=op, value=v, source="user", confidence="high", evidence=ev))
    s = apply(s, Update(field="start_date", op="remove", source="user", confidence="high", evidence=ev))
    return with_meta(s, asked=("frame",))


def run(p, state, catalog, cfg, text=TEXT):
    return guard(p, state, text, 2, catalog, cfg, heard=text)


def test_update_with_quote_not_in_message_is_dropped(catalog, cfg):
    g = run(plan(u("days", "4", "4 ngày")), framed(), catalog, cfg)
    assert g.state.days.value == 3 and "not in the message" in g.log[0]


def test_said_and_inferred_sources(catalog, cfg):
    g = run(plan(u("month", "12", "Tháng 12"), u("pace", "slow", "yên tĩnh", how="inferred")), framed(), catalog, cfg)
    assert (g.state.month.source, g.state.month.status) == ("user", "confirmed")
    assert (g.state.pace.source, g.state.pace.confidence) == ("inferred", "medium")


def test_unknown_feature_becomes_unmapped(catalog, cfg):
    g = run(plan(u("soft", "quiet_music=present:love", "yên tĩnh", op="add")), framed(), catalog, cfg)
    assert [x.phrase for x in g.state.unmapped] == ["yên tĩnh"] and not g.state.soft


def test_tier_one_question_is_forced(catalog, cfg):
    g = run(plan(u("signal", "elderly", "bố mẹ", op="add", how="inferred"), qid="pace"), framed(), catalog, cfg)
    assert g.question.qid == "c_effort" and "forced" in g.log[-1]


def test_stop_and_budget_give_ready(catalog, cfg):
    assert run(plan(kind="stop"), framed(), catalog, cfg).question.qid == "ready"
    assert run(plan(qid="pace"), with_meta(framed(), adaptive_turns=5), catalog, cfg).question.qid == "ready"


def test_custom_question_needs_two_to_six_short_chips(catalog, cfg):
    ok = run(plan(custom_text="Vì sao bạn muốn đến đó?", custom_chips=("View", "Ít người")), framed(), catalog, cfg)
    assert ok.question.custom and [c.label for c in ok.question.chips] == ["View", "Ít người"]
    bad = run(plan(custom_text="Vì sao?", custom_chips=("View",)), framed(), catalog, cfg)
    assert not bad.question.custom


def test_unknown_qid_falls_back_to_policy(catalog, cfg):
    g = run(plan(qid="nope"), framed(), catalog, cfg)
    assert g.question.qid != "nope" and "unknown qid" in g.log[-1]


def test_say_with_new_number_or_place_name_is_replaced(catalog, cfg):
    assert run(plan(say="Có 38 nơi hợp."), framed(), catalog, cfg).say == ""
    assert run(plan(say="Thử Quán Yên Tĩnh Số 1 nhé."), framed(), catalog, cfg).say == ""
    assert run(plan(say="3 ngày tháng 12, ghi rồi."), framed(), catalog, cfg).say == "3 ngày tháng 12, ghi rồi."


def test_inference_cannot_overwrite_user_choice(catalog, cfg):
    g = run(plan(u("mobility", "motorbike", "đi 3 ngày", how="inferred")), framed(), catalog, cfg)
    assert g.state.mobility.value == "car"
```

`tests/trip/test_live.py`:

```python
"""Real Gemma calls: python -m pytest -m live tests/trip/test_live.py -s (needs UIT network + AGENT_* in .env)."""

import asyncio
import time
from datetime import date

import pytest

from trip.agent import prompt_fields, run_agent
from trip.prepass import prepass
from trip.settings import load
from trip.state import TripState

pytestmark = pytest.mark.live
MESSAGES = ["Tháng 12 đi Đà Lạt 3 ngày với bố mẹ, mẹ đau gối, muốn chill",
            "2 vợ chồng đi xe máy, thích săn mây với cà phê view đồi",
            "đi 4 người bạn, không quá 500k/người, thích chỗ đông vui có nhạc sống",
            "lần trước đi Langbiang rồi, lần này muốn khác",
            "chưa biết đi đâu, gợi ý giúp"]


@pytest.mark.parametrize("text", MESSAGES)
def test_gemma_returns_a_valid_plan(text):
    cfg, today = load(), date.today()
    fields = prompt_fields(TripState(), text, prepass(text, today), None, [], cfg, None, today)
    first, t0 = [], time.monotonic()
    plan = asyncio.run(run_agent(fields, lambda s: first or first.append(time.monotonic() - t0), cfg))
    shown = f"{first[0]:.1f}s" if first else "none"
    print(f"\n{text}\n  first say {shown} total {time.monotonic() - t0:.1f}s\n  {plan}")
    assert plan.say
```

- [ ] **Step 3: Run to verify failure**

Run: `python -m pytest -q tests/trip/test_agent.py tests/trip/test_guard.py`
Expected: ERROR `No module named 'trip.agent'`.

- [ ] **Step 4: Implement `src/trip/guard.py`**

```python
"""Checks an agent TurnPlan before it touches the Trip State (docs/plans/TRIP_UNDERSTANDING_SPEC.md §5)."""

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import ValidationError

from . import values
from .catalog import Catalog
from .policy import askable, next_question
from .questions import READY, Chip, Question, required
from .settings import Settings
from .state import SCALARS, Evidence, Frozen, TripState, Update, apply, settle
from .text import contains, squash

FieldName = Literal["start_date", "month", "days", "companions", "people", "base", "mobility", "arrive_at", "leave_at",
                    "day_end", "purpose", "anchor", "signal", "soft", "hard", "pace", "max_leg_min", "crowd_tolerance",
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
          heard: str) -> Guarded:
    """text: this turn's message (quotes must come from it); heard: every user message so far (numbers allowed in say)."""
    log: list[str] = []
    for u in plan.updates:
        if not contains(text, u.quote):
            log.append(f"drop {u.field}={u.value!r}: quote {u.quote!r} not in the message")
            continue
        ev = Evidence(turn=turn, quote=u.quote)
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
    why = _bad_say(say, heard, state, catalog)
    if why:
        log.append(f"say replaced: {why}")
        say = ""
    return Guarded(state, question, say, log)


def _question(nx: PlanNext, state: TripState, turn: int, catalog: Catalog, cfg: Settings, log: list[str]) -> Question:
    req = required(state, catalog, cfg)
    if req:
        if nx.qid != req.qid:
            log.append(f"forced tier-1 {req.qid} over {nx.qid or nx.custom_text or nx.kind!r}")
        return req
    if nx.kind == "stop" or state.meta.adaptive_turns >= cfg.turn_budget:
        return READY
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


def _bad_say(say: str, heard: str, state: TripState, catalog: Catalog) -> str | None:
    said = set(re.findall(r"\d+", heard))
    extra = [n for n in re.findall(r"\d+", say) if n not in said]
    if extra:
        return f"numbers {extra} the user did not say"
    anchors = {a.place_id for a in state.anchors if a.place_id}
    s = f" {squash(say)} "
    for key, pid in catalog.name_keys:
        if pid not in anchors and f" {key} " in s:
            return f"names place {pid}"
    return None
```

- [ ] **Step 5: Implement `src/trip/agent.py`**

```python
"""One agent call per free-text turn: prompt from prefetched facts, streamed say, typed plan (spec §5)."""

import asyncio
import functools
import json
import re
from datetime import date
from typing import AsyncIterator, Callable

import openai
from pydantic import ValidationError

from corpus.llm import AGENT, TRIP_TURN

from .guard import TurnPlan
from .prepass import Prepass
from .questions import Question
from .settings import Settings
from .state import SCALARS, Base, TripState, ontology


class AgentError(Exception):
    """The agent did not give a usable plan in time; the turn falls back to the policy."""


class SayStream:
    """Pulls the "say" string out of a JSON object while it streams in."""

    def __init__(self):
        self.buf = ""
        self.sent = 0

    def feed(self, delta: str) -> str:
        self.buf += delta
        m = re.search(r'"say"\s*:\s*"', self.buf)
        if not m:
            return ""
        raw = self.buf[m.end():]
        end = _closing_quote(raw)
        raw = raw[:end] if end is not None else _trim_partial_escape(raw)
        try:
            text = json.loads('"' + raw + '"')
        except json.JSONDecodeError:
            return ""
        new, self.sent = text[self.sent:], max(self.sent, len(text))
        return new


def _closing_quote(raw: str) -> int | None:
    i = 0
    while i < len(raw):
        if raw[i] == "\\":
            i += 2
            continue
        if raw[i] == '"':
            return i
        i += 1
    return None


def _trim_partial_escape(raw: str) -> str:
    m = re.search(r"\\u[0-9a-fA-F]{0,3}$", raw)
    if m:
        return raw[:m.start()]
    tail = len(raw) - len(raw.rstrip("\\"))
    return raw[:-1] if tail % 2 else raw


@functools.cache
def _features() -> str:
    o = ontology()
    lines = [f"{f.id}: {'|'.join(f.values)} - {re.split(r'[;(:]', f.hint)[0].strip()[:70]}" for f in o.features.values()]
    return "\n".join(lines) + "\ncontexts: " + "; ".join(f"{k}: {'|'.join(v)}" for k, v in o.contexts.items())


def _plain(v):
    if isinstance(v, (frozenset, set)):
        return sorted(v)
    if isinstance(v, Base):
        return v.text
    return v.isoformat() if isinstance(v, date) else v


def summarize(state: TripState) -> str:
    out: dict = {}
    for f in SCALARS + ("companions",):
        x = getattr(state, f)
        if x.known:
            out[f] = {"value": _plain(x.value), "source": x.source}
    if state.soft:
        out["soft"] = {k: f.value for k, f in state.soft.items()}
    if state.hard:
        out["hard"] = [f"{h.feature}{'!=' if h.op == 'ne' else '='}{h.value}" for h in state.hard]
    if state.anchors:
        out["anchors"] = [a.text for a in state.anchors]
    if state.signals:
        out["signals"] = [s.kind + ("" if s.handled else " (open)") for s in state.signals]
    if state.unmapped:
        out["unmapped"] = [u.phrase for u in state.unmapped]
    return json.dumps(out, ensure_ascii=False, default=str)


def prompt_fields(state: TripState, text: str, pre: Prepass, required: Question | None,
                  ranked: list[tuple[Question, float]], cfg: Settings, last_question: str | None, today: date) -> dict:
    hits = [{"field": p.field, "value": _plain(p.value), "quote": p.quote} for p in pre.proposals]
    hits += [{"ambiguous": q, "may_mean": list(k)} for q, k in pre.ambiguous]
    return {
        "features": _features(),
        "state": summarize(state),
        "text": text,
        "prepass": json.dumps(hits, ensure_ascii=False, default=str),
        "required": f"{required.qid}: {required.text}" if required else "none",
        "candidates": "\n".join(f"{q.qid}: {q.text}" for q, _ in ranked[:5]) or "none",
        "budget": max(0, cfg.turn_budget - state.meta.adaptive_turns),
        "experience": state.meta.experience or "unknown",
        "last_question": last_question or "none",
        "today": today.isoformat(),
    }


def gemma_stream(fields: dict) -> AsyncIterator[str]:
    async def gen():
        client, model = AGENT.client()
        try:
            async for d in TRIP_TURN.stream(client, model, **fields):
                yield d
        finally:
            await client.close()
    return gen()


async def run_agent(fields: dict, on_say: Callable[[str], None], cfg: Settings,
                    open_stream: Callable[[dict], AsyncIterator[str]] = gemma_stream) -> TurnPlan:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + cfg.total_s
    it = open_stream(fields).__aiter__()
    say, buf, first = SayStream(), [], True
    try:
        while True:
            timeout = cfg.first_token_s if first else deadline - loop.time()
            if timeout <= 0:
                raise AgentError(f"no complete answer in {cfg.total_s:.0f} s")
            try:
                delta = await asyncio.wait_for(it.__anext__(), timeout)
            except StopAsyncIteration:
                break
            first = False
            buf.append(delta)
            if new := say.feed(delta):
                on_say(new)
    except asyncio.TimeoutError as e:
        raise AgentError("first token too slow" if first else "answer too slow") from e
    except openai.OpenAIError as e:
        raise AgentError(f"{type(e).__name__}: {e}") from e
    finally:
        aclose = getattr(it, "aclose", None)
        if aclose:
            try:
                await aclose()
            except Exception:
                pass
    try:
        return TurnPlan.model_validate_json("".join(buf))
    except ValidationError as e:
        raise AgentError(f"bad plan: {str(e).splitlines()[0]}") from e
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest -q tests/trip tests/test_llm_task.py`
Expected: all pass (live test deselected).

- [ ] **Step 7: Live smoke (UIT network)**

Run: `python -m pytest -m live tests/trip/test_live.py -s -q`
Expected: 5 passed; printed first-say time around 1–3 s when Gemma is not saturated. If prompt issues show up (wrong field formats), fix the prompt in `TRIP_TURN`, not the guard.

- [ ] **Step 8: Commit**

```bash
git add src/corpus/llm src/trip/agent.py src/trip/guard.py tests/trip .env.example
git commit -m "feat(trip): streamed Gemma turn with a guard over its plan"
```

---

### Task 7: Engine and session store

**Files:**
- Create: `src/trip/sessions.py`, `src/trip/engine.py`
- Test: `tests/trip/test_engine.py`

**Interfaces:**
- Consumes: Tasks 1–6.
- Produces: `sessions.Session(id, state, card, transcript, lock)`, `sessions.SessionStore(root: Path | None)` with `new(state)`, `get(sid)` (KeyError when absent), `save(s)`; `engine.TurnInput(kind, text, qid, chips, value, target)`, `engine.card(q) -> dict | None`, `engine.Engine(catalog, cfg, store, agent, today=date.today)` with `create(experience, start_with) -> view`, `load(sid) -> view`, `places(q) -> list[dict]`, `turn(sid, inp, emit)`; view = `{"id", "transcript": [{role, text, turn}], "understanding", "card"}`; events `preview`, `say` (`{"delta"}` or `{"replace"}`), `state` (`{"understanding"}`), `card`, `done` (`{"search_input"}`), `error` (`{"message"}`).

- [ ] **Step 1: Write failing tests**

`tests/trip/test_engine.py`:

```python
from datetime import date

import pytest

from trip.agent import AgentError
from trip.engine import FALLBACK_SAY, Engine, TurnInput
from trip.guard import TurnPlan
from trip.sessions import SessionStore


class FakeAgent:
    def __init__(self, plan=None, error=None, chunks=()):
        self.plan, self.error, self.chunks, self.calls = plan, error, chunks, 0

    async def __call__(self, fields, on_say):
        self.calls += 1
        self.fields = fields
        for c in self.chunks:
            on_say(c)
        if self.error:
            raise self.error
        return TurnPlan.model_validate(self.plan)


def plan(updates=(), say="Mình hiểu rồi.", qid="", kind="ask"):
    return {"say": say, "updates": list(updates),
            "next": {"kind": kind, "qid": qid, "custom_text": "", "custom_chips": [], "reason": ""}}


@pytest.fixture
def make(catalog, cfg, tmp_path):
    def build(agent=None, root=tmp_path):
        return Engine(catalog, cfg, SessionStore(root), agent or FakeAgent(error=AgentError("down")),
                      today=lambda: date(2026, 10, 2))
    return build


def run(engine, sid, **inp):
    events = []
    engine.turn(sid, TurnInput(**inp), lambda e, d: events.append((e, d)))
    return events


def names(events):
    return [e for e, _ in events]


def answer_frame(e, sid):
    return run(e, sid, kind="answer", qid="frame", chips=("days:3", "who:solo", "mobility:car"))


def test_create_opens_with_frame(make):
    v = make().create("first", "nothing")
    assert v["card"]["qid"] == "frame" and v["transcript"][0]["role"] == "agent"
    assert all(set(c) == {"id", "label", "row"} for c in v["card"]["chips"])


def test_chip_answer_needs_no_agent(make):
    agent = FakeAgent(error=AssertionError("must not be called"))
    e = make(agent)
    sid = e.create("first", "nothing")["id"]
    ev = answer_frame(e, sid)
    assert names(ev) == ["state", "card"] and ev[1][1]["qid"] == "dates" and agent.calls == 0


def test_text_turn_streams_say_then_state_then_card(make):
    agent = FakeAgent(plan(updates=[{"field": "days", "op": "set", "value": "3", "quote": "3 ngày", "how": "said"}]),
                      chunks=("Mình ", "hiểu rồi."))
    e = make(agent)
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi 3 ngày")
    assert names(ev) == ["preview", "say", "say", "state", "card"]
    assert ev[3][1]["understanding"]["trip"][0]["value"] == 3
    assert agent.fields["text"] == "đi 3 ngày"


def test_agent_failure_falls_back_to_policy(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi 3 ngày bằng xe máy")
    assert ("say", {"replace": FALLBACK_SAY}) in ev and names(ev)[-1] == "card"
    trip = {r["target"]: r["value"] for r in ev[-2][1]["understanding"]["trip"]}
    assert trip == {"days": 3, "mobility": "motorbike"}


def test_text_only_user_gets_missing_fields_one_by_one(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi 3 ngày bằng xe máy")
    assert ev[-1][1]["qid"] == "companions"


def test_show_with_pending_safety_returns_that_question(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="mẹ đau gối")
    ev = run(e, sid, kind="show")
    assert names(ev) == ["say", "card"] and ev[1][1]["qid"] == "c_effort"


def test_conversation_completes_without_the_agent(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="3 ngày với bố mẹ, đi ô tô")
    for _ in range(15):
        c = e.load(sid)["card"]
        if c["qid"] in ("ready", "show_first"):
            break
        first = [x["id"] for x in c["chips"]][:1]
        run(e, sid, kind="answer", qid=c["qid"], chips=tuple(first or ["skip"]))
    ev = run(e, sid, kind="answer", qid=c["qid"], chips=("show",))
    assert names(ev) == ["done"] and ev[0][1]["search_input"]["context"]["days"] == 3


def test_removing_a_required_value_brings_its_question_back(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    answer_frame(e, sid)
    ev = run(e, sid, kind="edit", target="mobility", value=None)
    assert names(ev) == ["state", "card"] and ev[1][1]["qid"] == "mobility"


def test_edit_soft_and_bad_value(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="edit", target="soft:noise=quiet", value="love")
    assert e.load(sid)["understanding"]["soft"][0]["key"] == "noise=quiet"
    run(e, sid, kind="edit", target="soft:noise=quiet", value=None)
    assert e.load(sid)["understanding"]["soft"] == []
    assert names(run(e, sid, kind="edit", target="days", value="mười"))[0] == "error"


def test_stale_answer_is_rejected(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="answer", qid="pace", chips=("slow",))
    assert names(ev) == ["error", "card"]


def test_session_survives_restart(make, tmp_path):
    sid = make().create("returning", "saved")["id"]
    answer_frame(make(), sid)
    v = make().load(sid)
    assert v["card"]["qid"] == "dates" and [t["role"] for t in v["transcript"]] == ["agent", "agent", "user"]


def test_unknown_session_raises(make):
    with pytest.raises(KeyError):
        make().load("0123456789ab")
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest -q tests/trip/test_engine.py`
Expected: ERROR `No module named 'trip.engine'`.

- [ ] **Step 3: Implement `src/trip/sessions.py`**

```python
"""Conversation sessions: in memory, mirrored to data/trip/sessions/<id>.json so a reload or restart resumes."""

import json
import re
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .questions import Question
from .state import TripState

SID = re.compile(r"[0-9a-f]{12}")


@dataclass
class Session:
    id: str
    state: TripState
    card: Question | None = None
    transcript: list[dict] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class SessionStore:
    def __init__(self, root: Path | None):
        self.root = root
        self._mem: dict[str, Session] = {}
        self._guard = threading.Lock()

    def new(self, state: TripState) -> Session:
        s = Session(uuid.uuid4().hex[:12], state)
        with self._guard:
            self._mem[s.id] = s
        return s

    def get(self, sid: str) -> Session:
        if not SID.fullmatch(sid):
            raise KeyError(sid)
        with self._guard:
            if sid in self._mem:
                return self._mem[sid]
            path = self.root / f"{sid}.json" if self.root else None
            if not path or not path.exists():
                raise KeyError(sid)
            d = json.loads(path.read_text(encoding="utf-8"))
            s = Session(sid, TripState.model_validate(d["state"]),
                        Question.model_validate(d["card"]) if d.get("card") else None, d.get("transcript", []))
            self._mem[sid] = s
            return s

    def save(self, s: Session) -> None:
        if not self.root:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        body = {"id": s.id, "state": s.state.model_dump(mode="json"),
                "card": s.card.model_dump(mode="json") if s.card else None, "transcript": s.transcript}
        tmp = self.root / f"{s.id}.json.tmp"
        tmp.write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.root / f"{s.id}.json")
```

- [ ] **Step 4: Implement `src/trip/engine.py`**

```python
"""One conversation turn (docs/plans/TRIP_UNDERSTANDING_SPEC.md §5).

answer / edit / show are deterministic. text runs prepass -> agent (streamed) -> guard; any agent failure is answered
by the policy with the same state.
"""

import asyncio
from datetime import date
from typing import Awaitable, Callable, Literal

from pydantic import ValidationError

from . import values
from .agent import AgentError, prompt_fields
from .catalog import Catalog
from .compile import compile_search_input
from .guard import TurnPlan, guard
from .policy import next_question
from .prepass import Prepass, prepass
from .questions import Question, rank_questions, required
from .resolve import URL, anchor_for, search
from .sessions import Session, SessionStore
from .settings import Settings
from .state import SCALARS, Evidence, Frozen, Meta, TripState, Update, apply, apply_drafts, settle, with_meta
from .understanding import view as understanding

Emit = Callable[[str, dict], None]
Agent = Callable[[dict, Callable[[str], None]], Awaitable[TurnPlan]]

GREETING = "Chào bạn! Mình hỏi vài câu ngắn để hiểu chuyến Đà Lạt của bạn trước khi chọn chỗ."
FALLBACK_SAY = "Mình ghi lại được một phần; câu bạn gõ mình chưa hiểu hết, bạn có thể nói lại theo cách khác."
SAFETY_SAY = "Còn một câu để tránh xếp nhầm chỗ không hợp, bạn trả lời giúp mình nhé."
DONE_SAY = "Xong rồi, mình đi tìm chỗ hợp với chuyến này."
BAD_VALUE = "Giá trị này mình chưa đọc được, bạn thử lại nhé."


class TurnInput(Frozen):
    kind: Literal["text", "answer", "edit", "show"]
    text: str = ""
    qid: str = ""
    chips: tuple[str, ...] = ()
    value: str | None = None
    target: str = ""


def card(q: Question | None) -> dict | None:
    if q is None:
        return None
    d = q.model_dump(mode="json", exclude={"exit_drafts"})
    d["chips"] = [{"id": c.id, "label": c.label, "row": c.row} for c in q.chips]
    return d


class Engine:
    def __init__(self, catalog: Catalog, cfg: Settings, store: SessionStore, agent: Agent,
                 today: Callable[[], date] = date.today):
        self.catalog, self.cfg, self.store, self.agent, self.today = catalog, cfg, store, agent, today

    # ---------- reads ----------

    def create(self, experience: str | None = None, start_with: str | None = None) -> dict:
        state = TripState(meta=Meta(experience=experience, start_with=start_with))
        s = self.store.new(state)
        s.card = next_question(state, self.catalog, self.cfg)
        s.transcript.append({"role": "agent", "text": GREETING, "turn": 0})
        self.store.save(s)
        return self.view(s)

    def load(self, sid: str) -> dict:
        return self.view(self.store.get(sid))

    def view(self, s: Session) -> dict:
        return {"id": s.id,
                "transcript": [{k: t[k] for k in ("role", "text", "turn")} for t in s.transcript
                               if t["role"] in ("user", "agent")],
                "understanding": understanding(s.state, self.catalog, self.cfg),
                "card": card(s.card)}

    def places(self, q: str) -> list[dict]:
        return [{"id": p.id, "name": p.name, "category": p.category} for p in search(q, self.catalog)]

    # ---------- turns ----------

    def turn(self, sid: str, inp: TurnInput, emit: Emit) -> None:
        s = self.store.get(sid)
        with s.lock:
            try:
                getattr(self, f"_{inp.kind}")(s, inp, emit)
            finally:
                self.store.save(s)

    def _answer(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        q = s.card
        if q is None or q.qid != inp.qid:
            emit("error", {"message": "Câu này đã qua, bạn trả lời câu mới nhất nhé."})
            emit("card", card(s.card))
            return
        if "show" in inp.chips:
            return self._show(s, inp, emit)
        exit_ = next((x for x in ("skip", "unsure") if x in inp.chips), None)
        chosen = [c for c in q.chips if c.id in inp.chips]
        if q.custom and not exit_:
            text = ", ".join([c.label for c in chosen] + ([inp.text.strip()] if inp.text.strip() else []))
            return self._text(s, TurnInput(kind="text", text=text), emit)
        turn = s.state.meta.turn + 1
        st = s.state
        try:
            if exit_:
                st = apply_drafts(st, q.exit_drafts, turn, tool=f"chip:{q.qid}:{exit_}")
                st = with_meta(st, skipped=st.meta.skipped | {q.qid}, unsure_streak=st.meta.unsure_streak + 1)
            else:
                for c in chosen:
                    st = apply_drafts(st, c.drafts, turn, tool=f"chip:{q.qid}:{c.id}", quote=c.label)
                if inp.value and q.input_field:
                    st = apply(st, Update(field=q.input_field, value=values.parse(q.input_field, inp.value, self.catalog),
                                          source="user", confidence="high",
                                          evidence=Evidence(turn=turn, tool=f"input:{q.qid}")))
                st = with_meta(st, unsure_streak=0)
        except (ValueError, ValidationError):
            emit("error", {"message": BAD_VALUE})
            return
        label = {"skip": "Bỏ qua", "unsure": "Không chắc"}.get(exit_ or "") or \
            ", ".join(c.label for c in chosen) or (inp.value or "")
        self._close_card(s)
        s.transcript.append({"role": "user", "text": label or "…", "turn": turn, "kind": "answer", "qid": q.qid})
        st = with_meta(st, turn=turn, asked=st.meta.asked + (q.qid,),
                       adaptive_turns=st.meta.adaptive_turns + int(q.tier >= 2))
        s.state, s.card = settle(st), None
        if inp.text.strip():
            return self._text(s, TurnInput(kind="text", text=inp.text), emit)
        self._advance(s, emit)

    def _text(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        text = inp.text.strip()
        if not text:
            emit("card", card(s.card))
            return
        st, prev = s.state, s.card
        turn = st.meta.turn + 1
        self._close_card(s)
        s.transcript.append({"role": "user", "text": text, "turn": turn, "kind": "text"})
        pre = prepass(text, self.today())
        emit("preview", {"fields": [{"target": p.field, "value": values.jsonable(p.value), "quote": p.quote}
                                    for p in pre.proposals]})
        answered = (prev.qid,) if prev and prev.qid not in st.meta.asked else ()
        st = with_meta(st, turn=turn, asked=st.meta.asked + answered, unsure_streak=0,
                       adaptive_turns=st.meta.adaptive_turns + int(bool(prev) and prev.tier >= 2))
        st = self._deterministic(st, text, pre, turn)
        req = required(st, self.catalog, self.cfg)
        ranked = rank_questions(st, self.catalog, self.cfg)[:5]
        fields = prompt_fields(st, text, pre, req, ranked, self.cfg, prev.text if prev else None, self.today())
        streamed: list[str] = []

        def on_say(delta: str) -> None:
            streamed.append(delta)
            emit("say", {"delta": delta})

        heard = " ".join(t["text"] for t in s.transcript if t["role"] == "user")
        try:
            g = guard(asyncio.run(self.agent(fields, on_say)), st, text, turn, self.catalog, self.cfg, heard)
            st, q, say, log = g.state, g.question, g.say, g.log
        except AgentError as e:
            st, say, log = settle(st), FALLBACK_SAY, [f"agent_fallback: {e}"]
            q = next_question(st, self.catalog, self.cfg)
        if say != "".join(streamed):
            emit("say", {"replace": say})
        if say:
            s.transcript.append({"role": "agent", "text": say, "turn": turn, "kind": "say"})
        if log:
            s.transcript.append({"role": "system", "text": "; ".join(log), "turn": turn})
        s.state = st
        self._advance(s, emit, q)

    def _edit(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        ev = Evidence(turn=s.state.meta.turn, tool="edit")

        def user(field, value=None, op="set"):
            return Update(field=field, op=op, value=value, source="user", confidence="high", evidence=ev)

        kind, _, arg = inp.target.partition(":")
        v = inp.value
        try:
            if kind in SCALARS:
                u = user(kind, op="remove") if v is None else user(kind, values.parse(kind, v, self.catalog))
            elif kind == "companions":
                u = user(kind, [x for x in (v or "").split(",") if x])
            elif kind == "soft":
                u = user("soft", arg, "remove") if v is None else user("soft", (arg, v))
            elif kind == "hard":
                u = user("hard", arg, "remove") if v is None else user("hard_policy", (arg, v))
            elif kind in ("anchor", "unmapped"):
                u = user(kind, int(arg), "remove")
            elif kind == "signal":
                u = user("signal", arg, "remove")
            else:
                raise ValueError(f"unknown target {inp.target!r}")
            s.state = settle(apply(s.state, u))
        except (ValueError, ValidationError, IndexError):
            emit("error", {"message": BAD_VALUE})
            return
        emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
        req = required(s.state, self.catalog, self.cfg)
        if req and (s.card is None or s.card.qid != req.qid):
            s.card = req
            emit("card", card(req))

    def _show(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        req = required(s.state, self.catalog, self.cfg)
        if req:
            s.card = req
            emit("say", {"replace": SAFETY_SAY})
            emit("card", card(req))
            return
        si = compile_search_input(s.state)
        self._close_card(s)
        s.card = None
        s.transcript.append({"role": "agent", "text": DONE_SAY, "turn": s.state.meta.turn, "kind": "done"})
        emit("done", {"search_input": si.model_dump(mode="json")})

    # ---------- helpers ----------

    def _deterministic(self, st: TripState, text: str, pre: Prepass, turn: int) -> TripState:
        """Links, pasted place lists, keyword matches: written before the agent so nothing depends on it."""
        lines = [x.strip() for x in text.splitlines() if x.strip()]
        names = [x for x in lines if not URL.match(x)] if len(lines) >= 2 else []
        for raw in URL.findall(text) + names:
            a = anchor_for(raw, self.catalog)
            if a.state == "missing" and not URL.match(raw):
                continue
            st = apply(st, Update(field="anchor", op="add", value=a, source="user", confidence="high",
                                  evidence=Evidence(turn=turn, quote=raw)))
        for p in pre.proposals:
            try:
                st = apply(st, Update(field=p.field, op=p.op, value=p.value,
                                      source="inferred" if p.inferred else "user",
                                      confidence="low" if p.inferred else "medium",
                                      evidence=Evidence(turn=turn, quote=p.quote)))
            except (ValueError, ValidationError):
                pass
        for quote, keys in pre.ambiguous:
            good = [k for k in keys if self.catalog.count(k) >= self.cfg.top_k]
            ev = Evidence(turn=turn, quote=quote)
            if len(good) >= 2:
                u = Update(field="pending", op="add", value={"phrase": quote, "keys": good}, source="user",
                           confidence="medium", evidence=ev)
            elif good:
                u = Update(field="soft", op="add", value=(good[0], "love"), source="inferred", confidence="medium",
                           evidence=ev)
            else:
                u = Update(field="unmapped", op="add", value=quote, source="user", confidence="medium", evidence=ev)
            st = apply(st, u)
        return settle(st)

    def _close_card(self, s: Session) -> None:
        if s.card:
            s.transcript.append({"role": "agent", "text": s.card.text, "turn": s.state.meta.turn, "kind": "card"})

    def _advance(self, s: Session, emit: Emit, question: Question | None = None) -> None:
        s.card = question or next_question(s.state, self.catalog, self.cfg)
        emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
        emit("card", card(s.card))
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest -q tests/trip`
Expected: all pass. `test_session_survives_restart` transcript: greeting, frame card text, user answer.

- [ ] **Step 6: Commit**

```bash
git add src/trip/sessions.py src/trip/engine.py tests/trip/test_engine.py
git commit -m "feat(trip): conversation engine with deterministic fallback and resumable sessions"
```

---

### Task 8: HTTP + SSE server, CLI, public API

**Files:**
- Create: `src/trip/server.py`, `src/trip/__main__.py`
- Modify: `src/trip/__init__.py`, `web/vite.config.ts`
- Test: `tests/trip/test_server.py`

**Interfaces:**
- Consumes: `Engine`, `TurnInput`, `Catalog.load`, `settings.load/ROOT`, `run_agent`.
- Produces: `server.handler(engine)`, `server.run(engine, port)`; HTTP API of spec §6; `python -m trip serve [--port 8766]`; `trip` public API: `Engine, TurnInput, SessionStore, Catalog, SearchInput, Settings, compile_search_input`.

- [ ] **Step 1: Write failing test**

`tests/trip/test_server.py`:

```python
import json
import threading
import urllib.request
from datetime import date
from http.server import ThreadingHTTPServer

import pytest

from trip.agent import AgentError
from trip.engine import Engine
from trip.server import handler
from trip.sessions import SessionStore

from .test_engine import FakeAgent


@pytest.fixture
def base(catalog, cfg):
    engine = Engine(catalog, cfg, SessionStore(None), FakeAgent(error=AgentError("down")),
                    today=lambda: date(2026, 10, 2))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler(engine))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/api/trip"
    srv.shutdown()


def post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=5)


def sse(resp):
    events, ev = [], None
    for line in resp.read().decode().splitlines():
        if line.startswith("event: "):
            ev = line[7:]
        elif line.startswith("data: "):
            events.append((ev, json.loads(line[6:])))
    return events


def test_create_turn_and_reload(base):
    v = json.load(post(f"{base}/sessions", {"experience": "first", "start_with": "nothing"}))
    assert v["card"]["qid"] == "frame"
    r = post(f"{base}/sessions/{v['id']}/turn", {"kind": "answer", "qid": "frame",
                                                 "chips": ["days:3", "who:solo", "mobility:car"]})
    assert r.headers["Content-Type"].startswith("text/event-stream")
    assert [e for e, _ in sse(r)] == ["state", "card"]
    again = json.load(urllib.request.urlopen(f"{base}/sessions/{v['id']}", timeout=5))
    assert again["card"]["qid"] == "dates"
    places = json.load(urllib.request.urlopen(f"{base}/places?q=V%C6%B0%E1%BB%9Dn", timeout=5))
    assert places[0]["id"] == "0x11:0x1"


def test_errors(base):
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(f"{base}/sessions/0123456789ab", timeout=5)
    assert e.value.code == 404
    v = json.load(post(f"{base}/sessions", {}))
    with pytest.raises(urllib.error.HTTPError) as e:
        post(f"{base}/sessions/{v['id']}/turn", {"kind": "dance"})
    assert e.value.code == 400
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest -q tests/trip/test_server.py`
Expected: ERROR `No module named 'trip.server'`.

- [ ] **Step 3: Implement**

`src/trip/server.py`:

```python
"""HTTP API for the web (docs/plans/TRIP_UNDERSTANDING_SPEC.md §6). Local only: binds 127.0.0.1."""

import json
import re
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from pydantic import ValidationError

from .engine import Engine, TurnInput

SESSION = re.compile(r"/api/trip/sessions/([0-9a-f]{12})")
TURN = re.compile(r"/api/trip/sessions/([0-9a-f]{12})/turn")


def handler(engine: Engine):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, code: int, obj) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            url = urlparse(self.path)
            if m := SESSION.fullmatch(url.path):
                try:
                    return self._json(200, engine.load(m[1]))
                except KeyError:
                    return self._json(404, {"error": "no such session"})
            if url.path == "/api/trip/places":
                return self._json(200, engine.places(parse_qs(url.query).get("q", [""])[0]))
            self._json(404, {"error": "not found"})

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                body = self._body()
            except json.JSONDecodeError:
                return self._json(400, {"error": "body is not JSON"})
            if path == "/api/trip/sessions":
                exp, start = body.get("experience"), body.get("start_with")
                if exp not in (None, "first", "returning") or start not in (None, "nothing", "saved", "must", "itinerary"):
                    return self._json(400, {"error": "bad experience / start_with"})
                return self._json(200, engine.create(exp, start))
            if m := TURN.fullmatch(path):
                try:
                    inp = TurnInput.model_validate(body)
                    engine.store.get(m[1])
                except ValidationError as e:
                    return self._json(400, {"error": str(e).splitlines()[0]})
                except KeyError:
                    return self._json(404, {"error": "no such session"})
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()

                def emit(event: str, data: dict) -> None:
                    self.wfile.write(f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode())
                    self.wfile.flush()

                try:
                    engine.turn(m[1], inp, emit)
                except Exception:
                    traceback.print_exc(file=sys.stderr)
                    emit("error", {"message": "Máy chủ gặp lỗi, bạn thử lại nhé."})
                return
            self._json(404, {"error": "not found"})

        def log_message(self, *args):
            pass

    return Handler


def run(engine: Engine, port: int = 8766) -> None:
    ThreadingHTTPServer(("127.0.0.1", port), handler(engine)).serve_forever()
```

`src/trip/__main__.py`:

```python
"""python -m trip serve: the Trip Understanding API for the web (http://127.0.0.1:8766)."""

import argparse
import os
import sys

from dotenv import load_dotenv

from .agent import run_agent
from .catalog import Catalog
from .engine import Engine
from .server import run
from .sessions import SessionStore
from .settings import ROOT, load


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m trip")
    sub = ap.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="run the API the web /app/understand screen talks to")
    serve.add_argument("--port", type=int, default=8766)
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    missing = [k for k in ("AGENT_API_KEY", "AGENT_BASE_URL", "AGENT_MODEL") if not os.environ.get(k)]
    if missing:
        sys.exit(f"missing {', '.join(missing)} in .env (see .env.example, docs/LLM_PROVIDER.md)")
    cfg = load()
    data = ROOT / os.environ.get("DATA_DIR", "data")
    catalog = Catalog.load(data, cfg.n_min)
    engine = Engine(catalog, cfg, SessionStore(data / "trip" / "sessions"),
                    agent=lambda fields, on_say: run_agent(fields, on_say, cfg))
    print(f"Trip Understanding: http://127.0.0.1:{args.port} ({len(catalog.places)} places, model {os.environ['AGENT_MODEL']})")
    run(engine, args.port)


if __name__ == "__main__":
    main()
```

`src/trip/__init__.py`:

```python
"""Trip Understanding: understand what the user needs for this trip -> Search Input (docs/TRIP_UNDERSTANDING.md)."""

from .catalog import Catalog
from .compile import UnhandledSignal, compile_search_input
from .engine import Engine, TurnInput
from .sessions import SessionStore
from .settings import Settings
from .state import SearchInput, TripState

__all__ = ["Catalog", "Engine", "SearchInput", "SessionStore", "Settings", "TripState", "TurnInput", "UnhandledSignal",
           "compile_search_input"]
```

`web/vite.config.ts`: replace the `server` line with

```ts
  // /api/trip: `python -m trip serve` (src/trip/server.py, Trip Understanding).
  // /api: `python -m corpus review` (src/corpus/review/server.py): decisions and gold labels.
  server: { proxy: { '/api/trip': 'http://127.0.0.1:8766', '/api': 'http://127.0.0.1:8765' } },
```

- [ ] **Step 4: Run tests + real start**

Run: `python -m pytest -q tests/trip` → all pass.
Run: `python -m trip serve` (background) then `curl -s -X POST localhost:8766/api/trip/sessions -d '{}'` → JSON with `card.qid == "frame"`; stop it.

- [ ] **Step 5: Commit**

```bash
git add src/trip tests/trip web/vite.config.ts
git commit -m "feat(trip): HTTP + SSE API and python -m trip serve"
```

---

### Task 9: Web client — types, API, adapter

**Files:**
- Create: `web/src/user/tu/types.ts`, `web/src/user/tu/api.ts`, `web/src/user/tu/adapter.ts`
- Modify: `web/src/user/trip.tsx` (add optional `searchInput` to `TripState`)

**Interfaces:**
- Consumes: server API (Task 8).
- Produces: types `Chip, Card, Row, AnchorRow, HardRow, SoftRow, Understanding, Turn, View, SearchInput, TurnInput, Handlers`; `createSession(experience, startWith) -> Promise<View>`, `getSession(id) -> Promise<View>` (throws `ApiError` with `.status`), `searchPlaces(q)`, `sendTurn(id, input, handlers)`; `fromSearchInput(si, today?) -> Partial<TripState>`.

- [ ] **Step 1: `web/src/user/tu/types.ts`**

```ts
// Shapes of the Trip Understanding API (src/trip/engine.py, understanding.py, state.py SearchInput).

export interface Chip {
  id: string
  label: string
  row: string | null
}

export interface Card {
  qid: string
  group: string
  text: string
  reason: string
  chips: Chip[]
  multi: boolean
  single_rows: string[]
  tier: number
  input: 'none' | 'text' | 'date' | 'place'
  input_field: string | null
  exits: boolean
  custom: boolean
}

export interface Row {
  target: string
  value: any
  mark: boolean
  confidence: 'high' | 'medium' | 'low'
}

export interface AnchorRow {
  target: string
  text: string
  place_id: string | null
  name: string | null
  state: 'matched' | 'choose' | 'missing'
  priority: 'must' | 'want'
}

export interface HardRow {
  target: string
  feature: string
  op: 'ne' | 'eq'
  value: string
  unknown_policy: 'exclude' | 'flag' | null
  coverage: { passed: number; failed: number; unknown: number; level: 'enough' | 'thin' | 'none' }
}

export interface SoftRow {
  target: string
  key: string
  feature: string
  value: string
  context: Record<string, string>
  weight: 'love' | 'avoid' | 'off'
  mark: boolean
}

export interface Understanding {
  purpose: Row | null
  trip: Row[]
  anchors: AnchorRow[]
  hard: HardRow[]
  soft: SoftRow[]
  pace: Row | null
  max_leg_min: Row | null
  crowd_tolerance: Row | null
  novelty: Row | null
  budget_vnd: Row | null
  unknowns: string[]
  unmapped: { target: string; phrase: string }[]
  safety_pending: boolean
}

export interface Turn {
  role: 'user' | 'agent'
  text: string
  turn: number
}

export interface View {
  id: string
  transcript: Turn[]
  understanding: Understanding
  card: Card | null
}

export interface SearchInput {
  ontology_version: number
  context: {
    start_date: string | null
    month: number | null
    days: number | null
    base: { place_id: string | null; text: string } | null
    mobility: 'motorbike' | 'car' | 'ride' | null
    companions: string[]
    people: number | null
    arrive_at: string | null
    leave_at: string | null
    day_end: string | null
  }
  hard_filters: { feature: string; op: 'ne' | 'eq'; value: string; unknown_policy: 'exclude' | 'flag' }[]
  anchors: { place_id: string; priority: 'must' | 'want' }[]
  soft_weights: { feature: string; value: string; context: Record<string, string> | null; weight: 1 | -1 | 0; source: string }[]
  pace: { level: 'slow' | 'normal' | 'packed' | null; max_leg_min: number | null; crowd_tolerance: string | null }
  novelty: { level: string | null; visited: string[] }
  unknowns: string[]
  unmapped: string[]
}

export type TurnInput =
  | { kind: 'text'; text: string }
  | { kind: 'answer'; qid: string; chips: string[]; text?: string; value?: string | null }
  | { kind: 'edit'; target: string; value: string | null }
  | { kind: 'show' }

export interface Handlers {
  preview?: (d: { fields: { target: string; value: unknown; quote: string }[] }) => void
  say?: (d: { delta?: string; replace?: string }) => void
  state?: (d: { understanding: Understanding }) => void
  card?: (d: Card | null) => void
  done?: (d: { search_input: SearchInput }) => void
  error?: (d: { message: string }) => void
}
```

- [ ] **Step 2: `web/src/user/tu/api.ts`**

```ts
import type { Handlers, TurnInput, View } from './types'

const BASE = '/api/trip'

export class ApiError extends Error {
  constructor(public status: number) {
    super(`Trip API ${status}`)
  }
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new ApiError(res.status)
  return res.json() as Promise<T>
}

export const createSession = (experience: string | null, startWith: string | null) =>
  fetch(`${BASE}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ experience, start_with: startWith }),
  }).then((r) => json<View>(r))

export const getSession = (id: string) => fetch(`${BASE}/sessions/${id}`).then((r) => json<View>(r))

export const searchPlaces = (q: string) =>
  fetch(`${BASE}/places?q=${encodeURIComponent(q)}`).then((r) => json<{ id: string; name: string; category: string | null }[]>(r))

// POST + server-sent events: EventSource cannot POST, so the stream is read by hand.
export async function sendTurn(id: string, input: TurnInput, h: Handlers): Promise<void> {
  const res = await fetch(`${BASE}/sessions/${id}/turn`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!res.ok || !res.body) throw new ApiError(res.status)
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += value
    let cut: number
    while ((cut = buf.indexOf('\n\n')) >= 0) {
      dispatch(buf.slice(0, cut), h)
      buf = buf.slice(cut + 2)
    }
  }
}

function dispatch(block: string, h: Handlers) {
  let event = 'message'
  let data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) event = line.slice(7)
    else if (line.startsWith('data: ')) data += line.slice(6)
  }
  if (!data) return
  const fn = (h as Record<string, ((d: unknown) => void) | undefined>)[event]
  fn?.(JSON.parse(data))
}
```

- [ ] **Step 3: `web/src/user/tu/adapter.ts`**

```ts
import type { TripState, Who } from '../trip'
import type { SearchInput } from './types'

// SearchInput -> the TripState the existing Shortlist / planner read. Lossy on purpose: what TripState cannot hold
// (unknown_policy, time contexts, unmapped wishes) stays in trip.searchInput for the real Place Decision.
export function fromSearchInput(si: SearchInput, today = new Date()): Partial<TripState> {
  const c = si.context
  const must = si.anchors.filter((a) => a.priority === 'must').map((a) => a.place_id)
  const prefs: TripState['prefs'] = {}
  for (const w of si.soft_weights) {
    if (w.weight === 0) continue
    prefs[w.feature] = { weight: w.weight > 0 ? 'love' : 'avoid', from: w.source === 'profile' ? 'profile' : 'answer' }
  }
  const patch: Partial<TripState> = {
    searchInput: si,
    prefs,
    mustVisit: must,
    locked: must,
    selected: must,
    rules: {
      maxLegMin: si.pace.max_leg_min,
      avoidSteep: si.hard_filters.some((h) => h.feature === 'steep_or_stairs' && h.op === 'ne' && h.value === 'present'),
      dayEnd: c.day_end ?? '21:30',
    },
  }
  if (c.start_date) patch.startDate = c.start_date
  else if (c.month) patch.startDate = firstOfMonth(c.month, today)
  if (c.days) patch.days = c.days
  if (c.people) patch.people = c.people
  if (c.mobility) patch.vehicle = c.mobility
  if (c.companions.length) patch.who = c.companions as Who[]
  if (c.base?.place_id) patch.lodging = c.base.place_id
  if (c.arrive_at) patch.arriveAt = c.arrive_at
  if (c.leave_at) patch.leaveAt = c.leave_at
  if (si.pace.level) patch.pace = si.pace.level
  return patch
}

// "tháng 12" without a day: the 1st of the next such month (an estimate the user can change later).
function firstOfMonth(month: number, today: Date) {
  const year = month - 1 < today.getMonth() ? today.getFullYear() + 1 : today.getFullYear()
  return `${year}-${String(month).padStart(2, '0')}-01`
}
```

- [ ] **Step 4: `web/src/user/trip.tsx`**

Add `import type { SearchInput } from './tu/types'` and in `interface TripState` after `feedback`: `searchInput?: SearchInput // from Trip Understanding; Place Decision reads it later`.

- [ ] **Step 5: Type-check**

Run: `cd web && npx tsc -b`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add web/src/user/tu web/src/user/trip.tsx
git commit -m "feat(web): Trip Understanding API client and SearchInput adapter"
```

---

### Task 10: Web screen — conversation + understanding panel

**Files:**
- Create: `web/src/user/screens/Understand.tsx`, `web/src/user/tu/labels.ts`
- Modify: `web/src/user/UserApp.tsx`, `web/src/user/user.css` (append), any `navigate('/app/setup')` / `'/app/discover'` callers
- Delete: `web/src/user/screens/Setup.tsx`, `web/src/user/screens/Discover.tsx`

**Interfaces:**
- Consumes: Task 9 (`api.ts`, `adapter.ts`, `types.ts`), `ui/bits` (`Icon`, `Page`, `Segmented`, `Sheet`), `data/labels` (`featureLabel`, `valueLabel`, `TIME_VI`), `trip.tsx` (`useTrip`, `WHO_LABEL`), `data/store` (`VEHICLE_LABEL`).
- Produces: route `/app/understand`; `Start` → `/app/understand`.

- [ ] **Step 1: Find callers of the removed routes**

Run: `grep -rn "app/setup\|app/discover\|screens/Setup\|screens/Discover" web/src`
Every hit outside `UserApp.tsx` changes to `/app/understand`.

- [ ] **Step 2: `web/src/user/tu/labels.ts`**

```ts
import { featureLabel, TIME_VI, valueLabel } from '../../data/labels'
import { VEHICLE_LABEL } from '../../data/store'
import { WHO_LABEL, type Who } from '../trip'
import type { HardRow, SoftRow } from './types'

export const FIELD_LABEL: Record<string, string> = {
  dates: 'Ngày đi', start_date: 'Ngày đi', month: 'Tháng', days: 'Số ngày', companions: 'Đi với ai', people: 'Số người',
  base: 'Chỗ ở', mobility: 'Đi lại', arrive_at: 'Ngày đầu tới', leave_at: 'Ngày cuối rời', day_end: 'Mỗi ngày xong trước',
  purpose: 'Mục đích', pace: 'Nhịp độ', max_leg_min: 'Mỗi chặng tối đa', crowd_tolerance: 'Chỗ đông', novelty: 'Mới hay quen',
  budget_vnd: 'Ngân sách',
}
export const PURPOSE_LABEL: Record<string, string> = {
  relax: 'Nghỉ ngơi', bond: 'Gắn kết', photo: 'Chụp ảnh', food_culture: 'Ẩm thực, văn hóa', nature: 'Thiên nhiên',
  explore: 'Khám phá', adventure: 'Mạo hiểm',
}
export const PACE_LABEL: Record<string, string> = { slow: 'Thong thả', normal: 'Vừa phải', packed: 'Đi nhiều' }
export const CROWD_LABEL: Record<string, string> = { avoid: 'Tránh', ok_if_worth: 'Nếu đáng', fine: 'Không ngại' }
export const NOVELTY_LABEL: Record<string, string> = { familiar: 'Quen', new: 'Mới', mix: 'Trộn' }
const HARD_TEXT: Record<string, string> = {
  steep_or_stairs: 'Tránh dốc, bậc thang', long_walk: 'Không đi bộ xa', vegetarian_options: 'Có món chay',
}

export function valueText(target: string, v: any): string {
  if (target === 'companions') return (v as Who[]).map((w) => WHO_LABEL[w] ?? w).join(', ')
  if (target === 'mobility') return VEHICLE_LABEL[v as keyof typeof VEHICLE_LABEL] ?? v
  if (target === 'start_date') return new Date(v + 'T00:00').toLocaleDateString('vi-VN')
  if (target === 'month') return `tháng ${v}`
  if (target === 'days') return `${v} ngày`
  if (target === 'people') return `${v} người`
  if (target === 'base') return v.name ?? v.text
  if (target === 'max_leg_min') return `${v} phút`
  if (target === 'budget_vnd') return `${Math.round(v / 1000)} nghìn / người / ngày`
  if (target === 'purpose') return PURPOSE_LABEL[v] ?? v
  if (target === 'pace') return PACE_LABEL[v] ?? v
  if (target === 'crowd_tolerance') return CROWD_LABEL[v] ?? v
  if (target === 'novelty') return NOVELTY_LABEL[v] ?? v
  return String(v)
}

export function softText(s: SoftRow) {
  const base = s.value === 'present' ? featureLabel(s.feature) : `${featureLabel(s.feature)}: ${valueLabel(s.value)}`
  const when = Object.values(s.context).map((c) => TIME_VI[c] ?? c)
  return (s.weight === 'avoid' ? 'Tránh: ' : '') + base + (when.length ? ` · ${when.join(', ')}` : '')
}

export const hardText = (h: HardRow) =>
  HARD_TEXT[h.feature] ?? `${featureLabel(h.feature)} ${h.op === 'ne' ? 'khác' : 'là'} ${valueLabel(h.value)}`
```

- [ ] **Step 3: `web/src/user/screens/Understand.tsx`**

```tsx
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { navigate } from '../../router'
import { Icon, Page, Segmented, Sheet } from '../../ui/bits'
import { WHO_LABEL, useTrip, type Who } from '../trip'
import { fromSearchInput } from '../tu/adapter'
import { ApiError, createSession, getSession, searchPlaces, sendTurn } from '../tu/api'
import { CROWD_LABEL, FIELD_LABEL, NOVELTY_LABEL, PACE_LABEL, PURPOSE_LABEL, hardText, softText, valueText } from '../tu/labels'
import type { Card, Chip, Row, TurnInput, Understanding } from '../tu/types'

const KEY = 'tg.tu.v1'
type Msg = { role: 'user' | 'agent'; text: string; live?: boolean }

const read = () => {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}
const write = (id: string | null) => {
  try {
    if (id) localStorage.setItem(KEY, id)
    else localStorage.removeItem(KEY)
  } catch {
    /* storage blocked: the session lasts until reload */
  }
}

export function Understand() {
  const { trip, dispatch } = useTrip()
  const [sid, setSid] = useState<string | null>(null)
  const [log, setLog] = useState<Msg[]>([])
  const [card, setCard] = useState<Card | null>(null)
  const [u, setU] = useState<Understanding | null>(null)
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState<Set<string>>(new Set())
  const [offline, setOffline] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [sheet, setSheet] = useState(false)
  const end = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const old = read()
        const resumed = old
          ? await getSession(old).catch((e) => {
              if (e instanceof ApiError && e.status === 404) return null
              throw e
            })
          : null
        const v = resumed ?? (await createSession(trip.experience, trip.startWith))
        if (!alive) return
        write(v.id)
        setSid(v.id)
        setLog(v.transcript.map((t) => ({ role: t.role, text: t.text })))
        setCard(v.card)
        setU(v.understanding)
      } catch {
        if (alive) setOffline(true)
      }
    })()
    return () => {
      alive = false
    }
    // the session opens once per mount; experience / startWith only matter for a new one
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  }, [log, card])

  const send = useCallback(
    async (input: TurnInput, echo?: string) => {
      if (!sid || busy) return
      setBusy(true)
      setNotice(null)
      if (echo !== undefined) setLog((l) => [...l, ...(card ? [{ role: 'agent' as const, text: card.text }] : []), { role: 'user', text: echo }])
      if (echo !== undefined) setCard(null)
      try {
        await sendTurn(sid, input, {
          preview: (p) => setPreview(new Set(p.fields.map((f) => f.target))),
          say: (d) =>
            setLog((l) => {
              const last = l[l.length - 1]
              if (d.replace !== undefined) {
                const base = last?.live ? l.slice(0, -1) : l
                return d.replace ? [...base, { role: 'agent', text: d.replace, live: true }] : base
              }
              if (last?.live) return [...l.slice(0, -1), { ...last, text: last.text + (d.delta ?? '') }]
              return [...l, { role: 'agent', text: d.delta ?? '', live: true }]
            }),
          state: (s) => {
            setU(s.understanding)
            setPreview(new Set())
          },
          card: (c) => setCard(c),
          done: (d) => {
            dispatch({ type: 'set', patch: fromSearchInput(d.search_input) })
            write(null)
            navigate('/app/shortlist')
          },
          error: (e) => setNotice(e.message),
        })
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) {
          write(null)
          setNotice('Phiên này đã hết. Tải lại trang để bắt đầu lại.')
        } else setOffline(true)
      } finally {
        setBusy(false)
        setPreview(new Set())
        setLog((l) => l.map((m) => (m.live ? { ...m, live: false } : m)))
      }
    },
    [sid, busy, card, dispatch],
  )

  const answer = (chips: string[], value?: string | null, label?: string) => {
    if (!card) return
    const names = card.chips.filter((c) => chips.includes(c.id)).map((c) => c.label)
    const echo = label ?? (chips.includes('skip') ? 'Bỏ qua' : chips.includes('unsure') ? 'Không chắc' : [...names, value ?? ''].filter(Boolean).join(', '))
    send({ kind: 'answer', qid: card.qid, chips, value: value ?? null }, echo)
  }
  const edit = (target: string, value: string | null) => send({ kind: 'edit', target, value })
  const show = () => send({ kind: 'show' })

  if (offline)
    return (
      <Page className="page--wide">
        <div className="tu__offline" role="alert">
          <Icon name="alert" />
          <p>
            Chưa kết nối được trợ lý. Chạy <code>python -m trip serve</code> rồi tải lại trang.
          </p>
        </div>
      </Page>
    )

  return (
    <Page className="page--wide">
      <header className="phead">
        <h1>Hiểu chuyến đi của bạn</h1>
        <p>Nói tự nhiên hoặc chọn nhanh. Mình chỉ hỏi điều làm thay đổi gợi ý, và bạn sửa được mọi thứ bên cạnh.</p>
      </header>
      <div className="tu">
        <section className="tu__chat" aria-label="Hội thoại">
          <ol className="tu__log" aria-live="polite">
            {log.map((m, i) => (
              <li key={i} className={`msg msg--${m.role}${m.live ? ' is-live' : ''}`}>
                {m.text}
              </li>
            ))}
            {busy && !log[log.length - 1]?.live && <li className="msg msg--agent msg--typing" aria-label="Đang hiểu">…</li>}
          </ol>
          {card && <QuestionCard key={card.qid} card={card} busy={busy} onAnswer={answer} />}
          {notice && (
            <p className="tu__notice" role="status">
              {notice}
            </p>
          )}
          <Composer busy={busy || !sid} onSend={(text) => send({ kind: 'text', text }, text)} />
          <div ref={end} />
        </section>
        <aside className="tu__panel" aria-label="Bản hiểu nhu cầu">
          {u && <Panel u={u} preview={preview} busy={busy} onEdit={edit} onShow={show} />}
        </aside>
      </div>
      {u && (
        <button type="button" className="tu__bar" onClick={() => setSheet(true)}>
          <span>{summary(u)}</span>
          <Icon name="chevron-up" size={16} />
        </button>
      )}
      <Sheet open={sheet} onClose={() => setSheet(false)} label="Bản hiểu nhu cầu">
        {u && <Panel u={u} preview={preview} busy={busy} onEdit={edit} onShow={show} />}
      </Sheet>
    </Page>
  )
}

function summary(u: Understanding) {
  const bits = u.trip.filter((r) => ['days', 'companions', 'mobility'].includes(r.target)).map((r) => valueText(r.target, r.value))
  if (u.hard.length) bits.push(hardText(u.hard[0]))
  if (u.soft.length) bits.push(`${u.soft.length} sở thích`)
  return bits.join(' · ') || 'Mình đang hiểu chuyến đi của bạn'
}

function QuestionCard({ card, busy, onAnswer }: { card: Card; busy: boolean; onAnswer: (chips: string[], value?: string | null, label?: string) => void }) {
  const [picked, setPicked] = useState<string[]>([])
  const [date, setDate] = useState('')
  const instant = !card.multi && card.input !== 'date'
  const rows: { row: string | null; chips: Chip[] }[] = []
  for (const c of card.chips) {
    const r = rows.find((x) => x.row === c.row)
    if (r) r.chips.push(c)
    else rows.push({ row: c.row, chips: [c] })
  }
  const toggle = (c: Chip) => {
    if (instant) return onAnswer([c.id])
    setPicked((p) => {
      if (p.includes(c.id)) return p.filter((x) => x !== c.id)
      const single = !card.multi || card.single_rows.includes(c.row ?? '')
      const rest = single ? p.filter((id) => card.chips.find((x) => x.id === id)?.row !== c.row) : p
      return [...rest, c.id]
    })
  }
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (busy || t.closest('input, textarea') || e.metaKey || e.ctrlKey || e.altKey) return
      const n = Number(e.key)
      if (n >= 1 && n <= card.chips.length) toggle(card.chips[n - 1])
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })
  let n = 0
  return (
    <section className={`qcard${card.tier === 1 ? ' qcard--must' : ''}`} aria-label="Câu hỏi">
      <p className="qcard__text">{card.text}</p>
      {card.reason && (
        <p className="qcard__why">
          <Icon name="info" size={14} /> {card.reason}
        </p>
      )}
      {rows.map((r) => (
        <div className="qcard__row" key={r.row ?? '_'}>
          {r.row && <span className="qcard__rowlabel">{r.row}</span>}
          <div className="chips">
            {r.chips.map((c) => {
              n += 1
              const on = picked.includes(c.id)
              return (
                <button key={c.id} type="button" className={`chip chip--lean${on ? ' is-on' : ''}`} aria-pressed={on} disabled={busy} onClick={() => toggle(c)}>
                  {n <= 9 && <kbd aria-hidden="true">{n}</kbd>}
                  {c.label}
                </button>
              )
            })}
          </div>
        </div>
      ))}
      {card.input === 'date' && (
        <label className="field">
          <span>Ngày đến</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
      )}
      {card.input === 'place' && <PlaceSearch placeholder="Tìm một nơi gần chỗ ở" onPick={(p) => onAnswer([], p.id, p.name)} />}
      <div className="qcard__foot">
        {(card.multi || card.input === 'date') && (
          <button className="btn" disabled={busy || (!picked.length && !date)} onClick={() => onAnswer(picked, date || null, date ? new Date(date + 'T00:00').toLocaleDateString('vi-VN') : undefined)}>
            Xong
          </button>
        )}
        {card.exits && (
          <span className="qcard__exits">
            <button className="link" disabled={busy} onClick={() => onAnswer(['unsure'])}>
              Không chắc
            </button>
            <button className="link" disabled={busy} onClick={() => onAnswer(['skip'])}>
              Bỏ qua
            </button>
          </span>
        )}
      </div>
    </section>
  )
}

function Composer({ busy, onSend }: { busy: boolean; onSend: (text: string) => void }) {
  const [text, setText] = useState('')
  const submit = () => {
    if (!text.trim() || busy) return
    onSend(text.trim())
    setText('')
  }
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }
  return (
    <form
      className="tu__composer"
      onSubmit={(e) => {
        e.preventDefault()
        submit()
      }}
    >
      <textarea
        rows={1}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKey}
        placeholder="Gõ thêm, hoặc dán tên / link nơi muốn đến…"
        aria-label="Tin nhắn cho trợ lý"
      />
      <button className="btn" type="submit" disabled={busy || !text.trim()} aria-label="Gửi">
        <Icon name="send" size={18} />
      </button>
    </form>
  )
}

function PlaceSearch({ onPick, placeholder }: { onPick: (p: { id: string; name: string }) => void; placeholder: string }) {
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<{ id: string; name: string; category: string | null }[]>([])
  useEffect(() => {
    if (q.trim().length < 2) return setHits([])
    const t = setTimeout(() => searchPlaces(q).then(setHits).catch(() => setHits([])), 180)
    return () => clearTimeout(t)
  }, [q])
  return (
    <div className="picker">
      <label className="search">
        <Icon name="search" size={16} />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} aria-label={placeholder} />
      </label>
      {hits.length > 0 && (
        <ul className="picker__list">
          {hits.map((p) => (
            <li key={p.id}>
              <button type="button" onClick={() => onPick(p)}>
                <b>{p.name}</b>
                <small>{p.category}</small>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Panel({ u, preview, busy, onEdit, onShow }: { u: Understanding; preview: Set<string>; busy: boolean; onEdit: (t: string, v: string | null) => void; onShow: () => void }) {
  const cls = (target: string, mark = false) => `urow${preview.has(target) ? ' is-preview' : ''}${mark ? ' urow--mark' : ''}`
  const trip = Object.fromEntries(u.trip.map((r) => [r.target, r])) as Record<string, Row>
  const [basePick, setBasePick] = useState(false)
  const companions: Who[] = trip.companions?.value ?? []
  const toggleWho = (w: Who) => onEdit('companions', (companions.includes(w) ? companions.filter((x) => x !== w) : [...companions, w]).join(','))
  return (
    <div className={`upanel${busy ? ' is-busy' : ''}`}>
      <h2 className="upanel__title">Mình đang hiểu</h2>

      <section className="usec">
        <h3>Mục đích</h3>
        <div className={cls('purpose', u.purpose?.mark)}>
          <Segmented label="Mục đích" value={u.purpose?.value ?? null} onChange={(v) => onEdit('purpose', v)} options={Object.entries(PURPOSE_LABEL).map(([value, label]) => ({ value, label }))} />
          {u.purpose?.mark && <Mark />}
        </div>
      </section>

      <section className="usec">
        <h3>Chuyến đi</h3>
        <div className={cls('days', trip.days?.mark)}>
          <span className="urow__k">{FIELD_LABEL.days}</span>
          <Segmented label="Số ngày" value={trip.days?.value ?? null} onChange={(v) => onEdit('days', String(v))} options={[1, 2, 3, 4, 5].map((d) => ({ value: d, label: `${d}` }))} />
        </div>
        <div className={cls('start_date', trip.start_date?.mark)}>
          <span className="urow__k">{FIELD_LABEL.start_date}</span>
          <input type="date" value={trip.start_date?.value ?? ''} onChange={(e) => onEdit('start_date', e.target.value || null)} aria-label="Ngày đi" />
          {!trip.start_date && trip.month && <small>{valueText('month', trip.month.value)}</small>}
        </div>
        <div className={cls('companions', trip.companions?.mark)}>
          <span className="urow__k">{FIELD_LABEL.companions}</span>
          <div className="chips">
            {(Object.keys(WHO_LABEL) as Who[]).map((w) => (
              <button key={w} type="button" className={`chip chip--lean${companions.includes(w) ? ' is-on' : ''}`} aria-pressed={companions.includes(w)} onClick={() => toggleWho(w)}>
                {WHO_LABEL[w]}
              </button>
            ))}
          </div>
        </div>
        <div className={cls('mobility', trip.mobility?.mark)}>
          <span className="urow__k">{FIELD_LABEL.mobility}</span>
          <Segmented label="Đi lại" value={trip.mobility?.value ?? null} onChange={(v) => onEdit('mobility', v)} options={[{ value: 'motorbike', label: 'Xe máy' }, { value: 'car', label: 'Ô tô' }, { value: 'ride', label: 'Grab' }]} />
        </div>
        <div className={cls('base', trip.base?.mark)}>
          <span className="urow__k">{FIELD_LABEL.base}</span>
          {trip.base && !basePick ? (
            <span className="urow__v">
              {valueText('base', trip.base.value)}{' '}
              <button className="link" onClick={() => setBasePick(true)}>
                Đổi
              </button>
            </span>
          ) : (
            <PlaceSearch
              placeholder="Chọn nơi gần chỗ ở"
              onPick={(p) => {
                setBasePick(false)
                onEdit('base', p.id)
              }}
            />
          )}
        </div>
        <div className="urow urow--times">
          {(['arrive_at', 'leave_at', 'day_end'] as const).map((t) => (
            <label key={t} className={cls(t, trip[t]?.mark)}>
              <span className="urow__k">{FIELD_LABEL[t]}</span>
              <input type="time" value={trip[t]?.value ?? ''} onChange={(e) => onEdit(t, e.target.value || null)} />
            </label>
          ))}
        </div>
      </section>

      {u.anchors.length > 0 && (
        <section className="usec">
          <h3>Nơi muốn đến</h3>
          <ul className="ulist">
            {u.anchors.map((a) => (
              <li key={a.target} className={cls(a.target)}>
                <Icon name={a.state === 'matched' ? 'flag' : 'alert'} size={14} />
                <span className="urow__v">
                  {a.name ?? a.text}
                  {a.state === 'missing' && <small> · chưa tìm thấy, không dùng để xếp lịch</small>}
                  {a.priority === 'want' && <small> · bỏ được nếu thiếu giờ</small>}
                </span>
                <Remove onClick={() => onEdit(a.target, null)} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {u.hard.length > 0 && (
        <section className="usec usec--rule">
          <h3>
            <Icon name="lock" size={14} /> Bắt buộc
          </h3>
          <ul className="ulist">
            {u.hard.map((h) => (
              <li key={h.target} className={cls(h.target)}>
                <span className="urow__v">
                  {hardText(h)}
                  <small>
                    {' '}
                    · {h.coverage.passed} nơi xác minh, {h.coverage.unknown} chưa rõ
                  </small>
                </span>
                <button type="button" className={`chip chip--rule${h.unknown_policy === 'flag' ? ' is-on' : ''}`} aria-pressed={h.unknown_policy === 'flag'} onClick={() => onEdit(h.target, h.unknown_policy === 'flag' ? 'exclude' : 'flag')}>
                  Xem cả nơi chưa rõ
                </button>
                <Remove onClick={() => onEdit(h.target, null)} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="usec">
        <h3>Sở thích</h3>
        {u.soft.length ? (
          <div className="chips">
            {u.soft.map((s) => (
              <span key={s.target} className={`chip chip--${s.mark ? 'profile' : 'lean'} is-on${preview.has('soft') ? ' is-preview' : ''}`}>
                <button type="button" className="chip__body" title="Chạm để đổi thích / tránh" onClick={() => onEdit(s.target, s.weight === 'love' ? 'avoid' : 'love')}>
                  {softText(s)}
                  {s.mark && <Mark />}
                </button>
                <Remove onClick={() => onEdit(s.target, null)} />
              </span>
            ))}
          </div>
        ) : (
          <p className="usec__empty">Chưa có. Kể thêm điều bạn muốn trải nghiệm.</p>
        )}
      </section>

      <section className="usec">
        <h3>Nhịp độ</h3>
        <div className={cls('pace', u.pace?.mark)}>
          <Segmented label="Nhịp độ" value={u.pace?.value ?? null} onChange={(v) => onEdit('pace', v)} options={Object.entries(PACE_LABEL).map(([value, label]) => ({ value, label }))} />
          {u.pace?.mark && <Mark />}
        </div>
        <div className={cls('max_leg_min', u.max_leg_min?.mark)}>
          <span className="urow__k">{FIELD_LABEL.max_leg_min}</span>
          <Segmented label="Mỗi chặng tối đa" value={u.max_leg_min?.value ?? null} onChange={(v) => onEdit('max_leg_min', String(v))} options={[15, 30, 60].map((m) => ({ value: m, label: `${m}′` }))} />
        </div>
        <div className={cls('crowd_tolerance', u.crowd_tolerance?.mark)}>
          <span className="urow__k">{FIELD_LABEL.crowd_tolerance}</span>
          <Segmented label="Chỗ đông" value={u.crowd_tolerance?.value ?? null} onChange={(v) => onEdit('crowd_tolerance', v)} options={Object.entries(CROWD_LABEL).map(([value, label]) => ({ value, label }))} />
        </div>
        <div className={cls('novelty', u.novelty?.mark)}>
          <span className="urow__k">{FIELD_LABEL.novelty}</span>
          <Segmented label="Mới hay quen" value={u.novelty?.value ?? null} onChange={(v) => onEdit('novelty', v)} options={Object.entries(NOVELTY_LABEL).map(([value, label]) => ({ value, label }))} />
        </div>
        {u.budget_vnd && (
          <div className={cls('budget_vnd', u.budget_vnd.mark)}>
            <span className="urow__k">{FIELD_LABEL.budget_vnd}</span>
            <span className="urow__v">{valueText('budget_vnd', u.budget_vnd.value)} · chưa kiểm được bằng dữ liệu</span>
            <Remove onClick={() => onEdit('budget_vnd', null)} />
          </div>
        )}
      </section>

      {(u.unknowns.length > 0 || u.unmapped.length > 0) && (
        <section className="usec usec--open">
          {u.unknowns.length > 0 && (
            <p>
              <b>Chưa rõ</b> {u.unknowns.map((k) => FIELD_LABEL[k] ?? k).join(', ')}
            </p>
          )}
          {u.unmapped.length > 0 && (
            <div>
              <b>Chưa kiểm được</b>
              <ul className="ulist">
                {u.unmapped.map((x) => (
                  <li key={x.target} className="urow">
                    <span className="urow__v">{x.phrase}</span>
                    <small>sẽ nêu trong lời giải thích, không dùng để chọn</small>
                    <Remove onClick={() => onEdit(x.target, null)} />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      <button className="btn upanel__go" disabled={busy} onClick={onShow}>
        {u.safety_pending ? 'Còn 1 câu an toàn cần trả lời' : 'Xem gợi ý'} <Icon name="arrow-right" size={16} />
      </button>
    </div>
  )
}

const Mark = () => (
  <span className="umark" title="Mình suy ra, bạn sửa được">
    ✎
  </span>
)

const Remove = ({ onClick }: { onClick: () => void }) => (
  <button type="button" className="iconbtn iconbtn--sm" aria-label="Bỏ" onClick={onClick}>
    <Icon name="x" size={12} />
  </button>
)
```

Check icon names used (`alert`, `info`, `lock`, `flag`, `x`, `search`, `send`, `chevron-up`, `arrow-right`) against `PATHS` in `web/src/ui/bits.tsx`; for any missing one add an SVG path to `PATHS` in the same style (24×24, stroke).

- [ ] **Step 4: Wire the route in `web/src/user/UserApp.tsx`**

- Remove imports of `Discover` and `Setup`; add `import { Understand } from './screens/Understand'`.
- `STEPS`: replace the first two entries with `{ path: '/app/understand', label: 'Hiểu chuyến đi' }`.
- `POSTER`: replace `'/app/setup'` / `'/app/discover'` keys with `'/app/understand': 'discover'`.
- Start: `<Start onHome={onHome} onDone={() => navigate('/app/understand')} />`.
- Routes: replace the `setup` and `discover` branches with `else if (base === '/app/understand') screen = <Understand />`.

- [ ] **Step 5: Append styles to `web/src/user/user.css`**

```css
/* ---------- Trip Understanding: conversation + understanding panel ---------- */

.tu {
  display: grid;
  gap: 24px;
  grid-template-columns: minmax(0, 1fr);
  padding-bottom: 72px;
}

.tu__panel {
  display: none;
}

@media (min-width: 960px) {
  .tu {
    grid-template-columns: minmax(0, 1fr) 380px;
    align-items: start;
    padding-bottom: 0;
  }
  .tu__panel {
    display: block;
    position: sticky;
    top: calc(var(--bar-h) + 16px);
    max-height: calc(100svh - var(--bar-h) - 32px);
    overflow: auto;
  }
  .tu__bar {
    display: none !important;
  }
}

.tu__chat {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.tu__log {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.msg {
  max-width: 85%;
  padding: 10px 14px;
  border-radius: 16px;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.msg--agent {
  align-self: flex-start;
  background: var(--card);
  border: 1px solid var(--line);
  border-bottom-left-radius: 6px;
}

.msg--user {
  align-self: flex-end;
  background: var(--pine);
  color: var(--paper);
  border-bottom-right-radius: 6px;
}

.msg.is-live::after {
  content: '▍';
  margin-left: 2px;
  color: var(--ink-3);
  animation: tu-blink 1s steps(2) infinite;
}

.msg--typing {
  color: var(--ink-3);
  letter-spacing: 0.2em;
  animation: tu-pulse 1.2s ease-in-out infinite;
}

.qcard {
  background: var(--card);
  border: 1.5px solid var(--line-2);
  border-radius: var(--r);
  box-shadow: var(--sh);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  animation: tu-rise 0.35s ease-out;
}

.qcard--must {
  border-color: var(--daquy);
}

.qcard__text {
  margin: 0;
  font-weight: 600;
  font-size: 1.05rem;
  line-height: 1.45;
}

.qcard__why {
  margin: 0;
  color: var(--ink-2);
  font-size: 0.9rem;
  display: flex;
  gap: 6px;
  align-items: flex-start;
}

.qcard__row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.qcard__rowlabel {
  font-size: 0.8rem;
  color: var(--ink-3);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.qcard .chip kbd {
  font: 600 0.7rem var(--mono);
  color: var(--ink-3);
  margin-right: 6px;
}

.qcard__foot {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.qcard__exits {
  display: flex;
  gap: 16px;
  margin-left: auto;
}

.tu__composer {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  position: sticky;
  bottom: 12px;
  background: var(--paper);
  padding-top: 6px;
}

.uapp .tu__composer textarea {
  margin: 0;
  min-height: 48px;
  max-height: 160px;
  resize: none;
}

.tu__composer .btn {
  min-width: 48px;
  min-height: 48px;
}

.tu__notice {
  margin: 0;
  color: var(--brick);
  font-size: 0.9rem;
}

.tu__offline {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 16px;
  border-radius: var(--r);
  background: var(--brick-soft);
  color: var(--brick);
}

.tu__bar {
  position: fixed;
  left: var(--gutter);
  right: var(--gutter);
  bottom: 12px;
  z-index: 30;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  min-height: 48px;
  padding: 10px 16px;
  border-radius: 999px;
  border: 1px solid var(--line-2);
  background: var(--card);
  box-shadow: var(--sh-lift);
  font: 500 0.9rem var(--sans);
  color: var(--ink);
  text-align: left;
}

.tu__bar span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upanel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  padding: 16px;
}

.upanel.is-busy {
  opacity: 0.85;
}

.upanel__title {
  margin: 0;
  font-size: 1.1rem;
}

.usec h3 {
  margin: 0 0 8px;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--ink-3);
  display: flex;
  gap: 6px;
  align-items: center;
}

.usec--rule h3 {
  color: var(--daquy-ink);
}

.usec__empty,
.usec--open p {
  margin: 0;
  color: var(--ink-2);
  font-size: 0.9rem;
}

.urow {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  padding: 6px 0;
  border-radius: 10px;
  transition: background 0.3s;
}

.urow__k {
  min-width: 110px;
  font-size: 0.85rem;
  color: var(--ink-2);
}

.urow__v {
  flex: 1;
  min-width: 0;
}

.urow small {
  color: var(--ink-3);
}

.urow--times {
  flex-direction: column;
  align-items: stretch;
}

.uapp .urow input[type='time'],
.uapp .urow input[type='date'] {
  width: auto;
  min-height: 40px;
}

.urow--mark .seg button[aria-checked='true'] {
  font-style: italic;
}

.is-preview {
  background: var(--daquy-soft);
  animation: tu-pulse 1.2s ease-in-out infinite;
}

.ulist {
  list-style: none;
  margin: 0;
  padding: 0;
}

.umark {
  color: var(--violet);
  font-size: 0.85rem;
  margin-left: 4px;
}

.chip .chip__body {
  all: unset;
  cursor: pointer;
}

.iconbtn--sm {
  width: 28px;
  height: 28px;
  min-width: 28px;
}

.upanel__go {
  width: 100%;
  justify-content: center;
}

@keyframes tu-rise {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
}

@keyframes tu-pulse {
  50% {
    opacity: 0.55;
  }
}

@keyframes tu-blink {
  50% {
    opacity: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .qcard,
  .is-preview,
  .msg--typing,
  .msg.is-live::after {
    animation: none;
  }
}
```

- [ ] **Step 6: Delete the old screens and build**

```bash
git rm web/src/user/screens/Setup.tsx web/src/user/screens/Discover.tsx
cd web && npm run build
```
Expected: build passes with no TypeScript errors.

- [ ] **Step 7: Run it for real (desktop + phone)**

Background: `python -m trip serve` and `cd web && npm run dev`. Drive `http://localhost:5173/app` with Chrome via `playwright-core` (same approach as `web/scripts/record_demo.mjs`): continue as guest → two start questions → `/app/understand`; type "Tháng 12 đi Đà Lạt 3 ngày với bố mẹ, mẹ đau gối, muốn chill"; check that the user bubble shows at once, the panel highlights, agent text streams, the `c_effort` card arrives; answer chips through to "Xem gợi ý" → lands on `/app/shortlist` with places. Reload mid-way → same conversation. Screenshot at 1280×800 and 390×844 into the scratchpad; no console errors. Stop the server → reload shows the offline banner.

- [ ] **Step 8: Commit**

```bash
git add web
git commit -m "feat(web): conversational Trip Understanding screen replaces Setup and Discover"
```

---

### Task 11: Docs merge and spec cleanup

**Files:**
- Modify: `docs/TRIP_UNDERSTANDING.md`, `docs/LLM_PROVIDER.md`, `docs/Role_Web_Functional_Design.md`, `docs/log/DEV_LOG.md`, `README.md`
- Delete: `docs/plans/TRIP_UNDERSTANDING_SPEC.md`, `docs/plans/TRIP_UNDERSTANDING_PLAN.md`

- [ ] **Step 1: Merge what the code now does into the official docs (Vietnamese, current state only)**

- `docs/TRIP_UNDERSTANDING.md`: new section "Bản chạy hiện tại": module `src/trip/` (one line per file), one agent call per typed turn + policy for chips/edits/fallback, guard table (from spec §5), events, `config/trip.yaml`, what is still design-only (span lexicon, anchor taste, gazetteer, profile, §16 eval).
- `docs/LLM_PROVIDER.md`: role `AGENT` (env vars, Gemma default, streamed, no retry, timeouts in `config/trip.yaml`).
- `docs/Role_Web_Functional_Design.md`: the User Web setup + preferences screens become `/app/understand` (chat + understanding panel).
- `docs/log/DEV_LOG.md`: new entry `trip-understanding` (file list, how to verify: `python -m pytest -q tests/trip`, `python -m pytest -m live tests/trip/test_live.py -s`, `python -m trip serve` + web), Hiện tại with today's measured live latency; Trước đó = _không có_.
- `README.md`: structure line `src/trip`, setup step `python -m trip serve` (port 8766) next to step 7.

- [ ] **Step 2: Delete the working spec and plan**

```bash
git rm docs/plans/TRIP_UNDERSTANDING_SPEC.md docs/plans/TRIP_UNDERSTANDING_PLAN.md
```

- [ ] **Step 3: Commit only if those docs had no other session's pending edits**

Run: `git diff --stat HEAD -- docs README.md`. These files already carried uncommitted edits from another session when this plan was written; if they still do, do **not** commit them — leave the doc edits in the working tree and tell the user which files mix both sessions' changes. Otherwise:

```bash
git add docs README.md
git commit -m "docs: Trip Understanding as built; drop the working spec and plan"
```
