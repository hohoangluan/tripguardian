"""A Planning session: a Decision Output plus the user's edits, versioned for undo / redo
(docs/specs/PLANNING_SPEC.md §Vòng người dùng sửa và góp ý). Shaped like src/decision/session.py; in memory,
mirrored to data/planning/sessions/<id>.json so a reload or a restart resumes. Only State is persisted -- the laid
out Schedule is rebuilt by the engine (Task 6), never serialized here.
"""

import json
import re
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from corpus.ontology import load as load_ontology

from .settings import to_min

Reason = Literal["far", "crowded", "pricey", "dislike", "visited", None]
SID = re.compile(r"[0-9a-f]{12}")


class Drop(BaseModel):
    place_id: str
    reason: Reason = None


class Relax(BaseModel):
    place_id: str
    feature: str


class State(BaseModel):
    chosen_variant: str | None = None
    lodging_touched: bool = False       # False = still the chosen variant's own lodging
    lodging_id: str | None = None       # a candidate id, or None for "no lodging" once lodging_touched
    lodging_point: dict | None = None   # set_lodging(text): {"id","lat","lng","text","source","fetched_at"}
    budget_override: int | None = None
    assignment: dict[str, int] = Field(default_factory=dict)             # place id -> day index, user-placed
    order_override: dict[int, list[str]] = Field(default_factory=dict)
    dropped: list[Drop] = Field(default_factory=list)
    locked: list[str] = Field(default_factory=list)
    pace_override: str | None = None
    objective_override: str | None = None
    day_window_override: dict[int, tuple[int, int]] = Field(default_factory=dict)
    relaxed: list[Relax] = Field(default_factory=list)
    last: str | None = None


class ActionError(ValueError):
    """The action is malformed or does not fit the session; nothing changed."""


@dataclass(frozen=True)
class ActCtx:
    by_place: dict                  # id -> Place, places the trip currently schedules
    n_days: int
    variant_ids: set
    backup_ids: dict                # backup_pool id -> its entry ({"for", "reason", ...})
    day_members: list               # place ids of each day, in the schedule this act applies onto
    objective_names: set
    valid_paces: set


def _is_physical(feature: str) -> bool:
    f = load_ontology().features.get(feature)
    return f is not None and f.group == "effort"


def _known(ctx: ActCtx, pid) -> bool:
    return isinstance(pid, str) and pid in ctx.by_place


def _day_of(ctx: ActCtx, pid: str) -> int | None:
    return next((d for d, ids in enumerate(ctx.day_members) if pid in ids), None)


def _drop(s: State, pid: str, reason: str | None = None) -> None:
    s.assignment.pop(pid, None)
    s.dropped = [d for d in s.dropped if d.place_id != pid] + [Drop(place_id=pid, reason=reason)]
    s.order_override = {d: [i for i in o if i != pid] for d, o in s.order_override.items()}


def _place(s: State, pid: str, day: int) -> None:
    s.dropped = [d for d in s.dropped if d.place_id != pid]
    s.assignment[pid] = day
    s.order_override.pop(day, None)


def apply_act(state: State, action: dict, ctx: ActCtx) -> State:
    t = action.get("type")
    s = state.model_copy(deep=True)
    if t == "pick_variant":
        vid = action.get("id")
        if vid not in ctx.variant_ids:
            raise ActionError(f"unknown variant {vid!r}")
        s.chosen_variant = vid
    elif t == "pick_lodging":
        s.lodging_touched, s.lodging_id, s.lodging_point = True, action.get("id"), None
    elif t == "clear_lodging":
        s.lodging_touched, s.lodging_id, s.lodging_point = True, None, None
    elif t == "set_lodging":
        point = action.get("_point")
        if not point:
            raise ActionError("set_lodging needs a resolved point (geocode failed or text empty)")
        s.lodging_touched, s.lodging_id, s.lodging_point = True, point["id"], point
    elif t == "set_lodging_budget":
        n = action.get("max_per_night")
        if n is not None and (not isinstance(n, int) or n < 0):
            raise ActionError(f"bad max_per_night {n!r}")
        s.budget_override = n
    elif t == "move_place":
        pid, day = action.get("place"), action.get("day")
        if not _known(ctx, pid):
            raise ActionError(f"unknown place {pid!r}")
        if pid in s.locked:
            raise ActionError(f"{pid!r} is locked to its day")
        if not isinstance(day, int) or not 0 <= day < ctx.n_days:
            raise ActionError(f"day {day!r} out of range")
        _place(s, pid, day)
    elif t == "reorder":
        day, order = action.get("day"), action.get("order")
        if not isinstance(day, int) or not 0 <= day < ctx.n_days:
            raise ActionError(f"day {day!r} out of range")
        if sorted(order or []) != sorted(ctx.day_members[day]):
            raise ActionError("order must be a permutation of the day's current places")
        s.order_override[day] = list(order)
    elif t == "drop_place":
        pid = action.get("place")
        if not _known(ctx, pid):
            raise ActionError(f"unknown place {pid!r}")
        if pid in s.locked:
            raise ActionError(f"{pid!r} is locked to its day")
        reason = action.get("reason")
        if reason not in (None, "far", "crowded", "pricey", "dislike", "visited"):
            raise ActionError(f"unknown reason {reason!r}")
        _drop(s, pid, reason)
    elif t == "add_from_backup":
        pid, day = action.get("place"), action.get("day")
        if pid not in ctx.backup_ids:
            raise ActionError(f"{pid!r} is not in the backup pool")
        if not isinstance(day, int) or not 0 <= day < ctx.n_days:
            raise ActionError(f"day {day!r} out of range")
        _place(s, pid, day)
    elif t == "swap":
        a, b = action.get("place"), action.get("with")
        if b not in ctx.backup_ids:
            raise ActionError(f"{b!r} is not in the backup pool")
        day = _day_of(ctx, a)
        if day is None:
            raise ActionError(f"{a!r} is not currently in the plan")
        if a in s.locked:
            raise ActionError(f"{a!r} is locked to its day")
        _drop(s, a)
        _place(s, b, day)
    elif t == "lock_slot":
        pid = action.get("place")
        if not _known(ctx, pid) or _day_of(ctx, pid) is None:
            raise ActionError(f"{pid!r} is not currently in the plan")
        if pid not in s.locked:
            s.locked.append(pid)
    elif t == "unlock":
        s.locked = [x for x in s.locked if x != action.get("place")]
    elif t == "set_pace":
        level = action.get("level")
        if level not in ctx.valid_paces:
            raise ActionError(f"unknown pace {level!r}")
        s.pace_override = level
    elif t == "set_objective":
        name = action.get("name")
        if name not in ctx.objective_names:
            raise ActionError(f"unknown objective {name!r}")
        s.objective_override = name
    elif t == "set_day_window":
        day, start, end = action.get("day"), action.get("start"), action.get("end")
        if not isinstance(day, int) or not 0 <= day < ctx.n_days:
            raise ActionError(f"day {day!r} out of range")
        try:
            a, b = to_min(start), to_min(end)
        except (ValueError, AttributeError):
            raise ActionError(f"bad time {start!r} / {end!r}") from None
        if a >= b:
            raise ActionError("start must be before end")
        s.day_window_override[day] = (a, b)
    elif t == "relax":
        feature = action.get("feature")
        if feature not in load_ontology().features:
            raise ActionError(f"unknown feature {feature!r}")
        if _is_physical(feature):
            raise ActionError(f"{feature!r} is a physical constraint, it cannot be relaxed")
        ids = action.get("place_ids") or ([action["place_id"]] if action.get("place_id") else [])
        if not ids:
            raise ActionError("relax needs place_id or place_ids")
        have = {(r.place_id, r.feature) for r in s.relaxed}
        s.relaxed += [Relax(place_id=i, feature=feature) for i in ids if (i, feature) not in have]
    else:
        raise ActionError(f"unknown action {t!r}")
    s.last = t
    return s


class Session(BaseModel):
    id: str
    decision_session_id: str | None = None
    decision: dict
    states: list[State] = Field(default_factory=lambda: [State()])
    position: int = 0
    log: list[dict] = Field(default_factory=list)
    output: dict | None = None

    @property
    def state(self) -> State:
        return self.states[self.position]


class Store:
    def __init__(self, root: Path | None):
        self.root = root
        self._mem: dict[str, Session] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def new(self, decision: dict, decision_session_id: str | None) -> Session:
        s = Session(id=uuid.uuid4().hex[:12], decision_session_id=decision_session_id, decision=decision)
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
            s = Session.model_validate_json(path.read_text(encoding="utf-8"))
            self._mem[sid] = s
            return s

    def save(self, s: Session) -> None:
        if not self.root:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.root / f"{s.id}.json.tmp"
        tmp.write_text(json.dumps(s.model_dump(mode="json"), ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.root / f"{s.id}.json")

    def lock(self, sid: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(sid, threading.Lock())
