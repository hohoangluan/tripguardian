"""A Planning session: a Decision Output plus the user's edits, versioned for undo / redo
(docs/PLANNING.md §Vòng người dùng sửa và góp ý). Shaped like src/decision/session.py; in memory,
mirrored to data/planning/sessions/<id>.json so a reload or a restart resumes. Only State is persisted -- the laid
out Schedule is rebuilt by the engine (Task 6), never serialized here.
"""

import json
import re
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from requirements import Activity

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
    plan_dropped: list[str] = Field(default_factory=list)   # optimizer's exclusions; separate from user preference
    restored: list[str] = Field(default_factory=list)      # selection places explicitly restored by the user
    lodging_touched: bool = False       # False = still the chosen variant's own lodging
    lodging_id: str | None = None       # a candidate id, or None for "no lodging" once lodging_touched
    lodging_point: dict | None = None   # set_lodging(text): {"id","lat","lng","text","source","fetched_at"}
    budget_override: int | None = None
    assignment: dict[str, int] = Field(default_factory=dict)             # place id -> day index, user-placed
    activity_override: dict[str, Activity] = Field(default_factory=dict)
    visit_duration_override: dict[str, int] = Field(default_factory=dict)
    order_override: dict[int, list[str]] = Field(default_factory=dict)
    dropped: list[Drop] = Field(default_factory=list)
    locked: list[str] = Field(default_factory=list)
    pace_override: str | None = None
    objective_override: str | None = None
    day_window_override: dict[int, tuple[int, int]] = Field(default_factory=dict)
    relaxed: list[Relax] = Field(default_factory=list)
    dismissed: list[str] = Field(default_factory=list)   # faded suggestions the user hid (spec §6: this session only)
    keep_order_days: list[int] = Field(default_factory=list)   # days whose better_order hint the user turned off (§8)
    last: str | None = None


class ActionError(ValueError):
    """The action is malformed or does not fit the session; nothing changed."""


@dataclass(frozen=True)
class ActCtx:
    by_place: dict                  # id -> Place, places the trip currently schedules
    n_days: int
    variant_ids: set
    backup_ids: dict                # backup_pool id (and faded suggestion id) -> its entry ({"for", "reason", ...})
    day_members: list               # place ids of each day, in the schedule this act applies onto
    objective_names: set
    valid_paces: set
    activities: dict[str, Activity] = field(default_factory=dict)
    variant_kept: dict[str, set[str]] = field(default_factory=dict)
    selection_ids: set[str] = field(default_factory=set)
    protected_ids: set[str] = field(default_factory=set)
    duration_range: tuple[int, int] | None = None
    day_windows: list = field(default_factory=list)       # (start, end) of each day now, for extend_days
    fixed_edges: frozenset = frozenset()                   # (day, "start" | "end") that extend_days never moves
    extend_max: int = 60                                   # realistic.extend_max_min


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
    if pid in s.plan_dropped:
        s.plan_dropped = [i for i in s.plan_dropped if i != pid]
        if pid not in s.restored:
            s.restored.append(pid)
    s.assignment[pid] = day
    # pid may have had an explicit order on some OTHER day before this move (or still has one on its old day) --
    # an order_override that no longer matches its day's real membership would desync from reorder's own "order
    # must be a permutation of the day's current members" contract and from _relayout's simulate() of it.
    s.order_override = {d: [i for i in o if i != pid] for d, o in s.order_override.items()}
    s.order_override.pop(day, None)


def apply_act(state: State, action: dict, ctx: ActCtx) -> State:
    t = action.get("type")
    s = state.model_copy(deep=True)
    if t == "pick_variant":
        vid = action.get("id")
        if vid not in ctx.variant_ids:
            raise ActionError(f"unknown variant {vid!r}")
        if s.chosen_variant is not None and s.chosen_variant != vid:
            # a day's explicit order is tied to that variant's own day shape (different objectives can split days
            # differently) -- not safe to replay onto a different variant's days. Place-level edits (assignment /
            # dropped / locked) are keyed by place id, not day shape, and stay meaningful across the switch.
            s.order_override = {}
        if vid in ctx.variant_kept:
            selected = {i for i in ctx.by_place}
            s.plan_dropped = sorted(selected - ctx.variant_kept[vid] - set(s.restored))
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
        # a new order of the day is not the one the user said to keep: its hint may show again
        s.keep_order_days = [d for d in s.keep_order_days if d != day]
    elif t == "keep_my_order":
        day = action.get("day")
        if type(day) is not int or not 0 <= day < ctx.n_days:
            raise ActionError(f"day {day!r} out of range")
        if day not in s.keep_order_days:
            s.keep_order_days.append(day)
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
        source = ctx.by_place.get(ctx.backup_ids[pid].get("for"))
        activity = ctx.activities.get(pid) or (source.activity if source else None)
        if activity:
            s.activity_override[pid] = activity
    elif t == "swap":
        a, b = action.get("place"), action.get("with")
        from_backup = b in ctx.backup_ids
        if not from_backup and b not in ctx.selection_ids:
            raise ActionError(f"{b!r} is neither in the selection nor the backup pool")
        day = _day_of(ctx, a)
        if day is None:
            raise ActionError(f"{a!r} is not currently in the plan")
        if _day_of(ctx, b) is not None:
            raise ActionError(f"{b!r} is already in the plan")
        if a in s.locked:
            raise ActionError(f"{a!r} is locked to its day")
        _drop(s, a)
        _place(s, b, day)
        if from_backup:
            source = ctx.by_place.get(a)
            if source and source.activity:
                s.activity_override[b] = source.activity
    elif t == "reoptimize":
        plan_dropped = action.get("_plan_dropped")
        if not isinstance(plan_dropped, list) or any(pid not in ctx.selection_ids for pid in plan_dropped):
            raise ActionError("reoptimize needs a validated selection result")
        s.plan_dropped = sorted(set(plan_dropped) - set(s.restored))
    elif t == "make_room":
        edit, drop_places = action.get("edit"), action.get("drop_places")
        if not isinstance(edit, dict) or edit.get("type") not in {"move_place", "add_from_backup", "swap"}:
            raise ActionError("make_room needs a supported edit")
        if not isinstance(drop_places, list) or not 0 < len(drop_places) <= 3 or \
                len(set(drop_places)) != len(drop_places):
            raise ActionError("make_room needs one to three distinct places")
        s = apply_act(s, edit, ctx)
        newly_protected = {edit.get("place"), edit.get("with")}
        for pid in drop_places:
            if not _known(ctx, pid):
                raise ActionError(f"unknown place {pid!r}")
            if pid in ctx.protected_ids or pid in newly_protected or pid in s.locked or pid in s.restored:
                raise ActionError(f"{pid!r} is protected and cannot make room")
            _drop(s, pid)
    elif t == "dismiss_suggestion":
        pid = action.get("place")
        if not isinstance(pid, str) or not pid:
            raise ActionError("dismiss_suggestion needs a place id")
        if pid not in s.dismissed:
            s.dismissed.append(pid)
    elif t == "lock_slot":
        pid = action.get("place")
        day = _day_of(ctx, pid)
        if not _known(ctx, pid) or day is None:
            raise ActionError(f"{pid!r} is not currently in the plan")
        if pid not in s.locked:
            s.locked.append(pid)
        s.assignment[pid] = day   # "ghim ngày": locking pins the place's current day, not just refuses to drop it
    elif t == "unlock":
        s.locked = [x for x in s.locked if x != action.get("place")]
    elif t == "set_pace":
        level = action.get("level")
        if level not in ctx.valid_paces:
            raise ActionError(f"unknown pace {level!r}")
        s.pace_override = level
    elif t == 'set_visit_duration':
        pid, minutes = action.get('place'), action.get('minutes')
        if not _known(ctx, pid):
            raise ActionError(f'unknown place {pid!r}')
        if pid in s.locked:
            raise ActionError(f'{pid!r} is locked')
        if minutes is None:
            s.visit_duration_override.pop(pid, None)
        elif (type(minutes) is not int or ctx.duration_range is None
              or not ctx.duration_range[0] <= minutes <= ctx.duration_range[1]):
            raise ActionError('visit duration is outside the supported range')
        else:
            s.visit_duration_override[pid] = minutes
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
    elif t == "extend_days":
        # Spec section 7: every day starts earlier (or ends later) by the same minutes, and every pick is kept again --
        # the overload card's "Hoặc giữ đủ N nơi". A fixed edge (arrival, check-in, departure, a free day) never moves.
        side, minutes = action.get("side"), action.get("per_day_min")
        if side not in {"start", "end"} or type(minutes) is not int or not 0 < minutes <= ctx.extend_max:
            raise ActionError(f"extend_days needs side start|end and 1..{ctx.extend_max} minutes")
        moved = False
        for day, (lo, hi) in enumerate(ctx.day_windows):
            if (day, side) in ctx.fixed_edges:
                continue
            s.day_window_override[day] = (max(0, lo - minutes), hi) if side == "start" else (lo, min(24 * 60, hi + minutes))
            moved = True
        if not moved:
            raise ActionError(f"no day of this trip can {'start earlier' if side == 'start' else 'end later'}")
        s.chosen_variant, s.plan_dropped, s.order_override = "main", [], {}
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
    require_lodging: bool = False
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
        self._locks: dict[str, threading.RLock] = {}
        self._guard = threading.Lock()

    def new(self, decision: dict, decision_session_id: str | None) -> Session:
        s = Session(id=uuid.uuid4().hex[:12], decision_session_id=decision_session_id, decision=decision)
        with self._guard:
            self._mem[s.id] = s
        return s

    def restore(self, session: Session) -> None:
        if not SID.fullmatch(session.id):
            raise ValueError(session.id)
        with self._guard:
            self._mem[session.id] = session

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

    def lock(self, sid: str) -> threading.RLock:
        """Reentrant: Engine.load() holds this while calling _view(), which may call _ensure_base() ->
        _crawl_lodging(), which also takes this same per-session lock for its own write-back -- a plain Lock would
        deadlock a thread against itself the first time a session needed a lazy rebuild while already held."""
        with self._guard:
            return self._locks.setdefault(sid, threading.RLock())
