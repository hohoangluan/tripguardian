"""A Planning session: a Decision Output plus the user's edits, versioned for undo / redo
(docs/P4_PLANNING.md §Vòng người dùng sửa và góp ý). Shaped like src/decision/session.py; in memory,
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
from typing_extensions import TypedDict

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


class VisitOverride(TypedDict):
    start: int | None
    duration_min: int | None


class LockedVisit(TypedDict):
    start: int
    duration_min: int


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
    visit_overrides: dict[str, VisitOverride] = Field(default_factory=dict)
    locked_visits: dict[str, LockedVisit] = Field(default_factory=dict)
    pace_override: str | None = None
    objective_override: str | None = None
    day_window_override: dict[int, tuple[int, int]] = Field(default_factory=dict)
    relaxed: list[Relax] = Field(default_factory=list)
    slots: dict[str, str] = Field(default_factory=dict)                 # place id -> dawn | sunset | evening | any
    last: str | None = None


class ActionError(ValueError):
    """The action is malformed or does not fit the session; nothing changed. `say`: the Vietnamese sentence for the
    user when the message alone cannot carry it (names, days); otherwise user_text() maps the message."""

    def __init__(self, message: str, say: str | None = None):
        super().__init__(message)
        self.say = say


# What the user reads for an ActionError (Tools maps them at the boundary): the first pattern that matches wins.
USER_TEXT = (
    (r"^nothing to undo", "Không còn bước nào để hoàn tác."),
    (r"^nothing to redo", "Không còn bước nào để làm lại."),
    (r"^pick a variant", "Bạn chọn một hành trình trước rồi hãy sửa lịch nhé."),
    (r"no-longer-offered lodging", "Chỗ ở này không còn trong danh sách gợi ý, bạn chọn chỗ khác nhé."),
    (r"^set_lodging needs non-empty text", "Bạn gõ tên hoặc địa chỉ chỗ ở giúp mình nhé."),
    (r"^set_lodging needs a resolved point", "Mình chưa tìm ra chỗ ở này trên bản đồ. Bạn chọn một gợi ý hiện ra khi "
                                             "gõ, hoặc gõ tên đường, địa chỉ cụ thể hơn nhé."),
    (r"^set_lodging lat", "Vị trí chỗ ở chưa đúng, bạn chọn lại trong danh sách gợi ý nhé."),
    (r"^bad max_per_night", "Mức giá mỗi đêm chưa đúng, bạn nhập lại một con số nhé."),
    (r"is locked to its day", "Nơi này đang được khóa vào ngày của nó. Bạn mở khóa trước rồi đổi nhé."),
    (r"^unknown place|is not currently in the plan", "Nơi này không có trong lịch hiện tại."),
    (r"out of range", "Ngày này nằm ngoài chuyến đi."),
    (r"^order must be", "Thứ tự mới phải gồm đúng các nơi của ngày đó."),
    (r"is not in the backup pool", "Nơi này không nằm trong danh sách dự phòng của chuyến nên mình chưa thêm vào lịch được."),
    (r"backup place has no record", "Mình chưa có đủ vị trí và thời gian ghé của nơi này để xếp vào lịch."),
    (r"^bad time", "Giờ chưa đúng, bạn nhập theo dạng 08:00 nhé."),
    (r"^start must be before end", "Giờ bắt đầu phải trước giờ kết thúc."),
    (r"physical constraint", "Đây là giới hạn về sức khỏe, đi lại nên mình không nới được."),
    (r"^slot .* is not possible", "Nơi này không xếp được vào buổi đó (giờ mở cửa hoặc khung giờ các ngày không cho phép)."),
)
FALLBACK_TEXT = "Thao tác này chưa áp dụng được cho lịch hiện tại. Bạn thử lại hoặc chọn cách khác nhé."


def user_text(message: str, say: str | None = None) -> str:
    """An ActionError's message as the Vietnamese sentence the user sees; never the developer text."""
    if say:
        return say
    return next((vi for pattern, vi in USER_TEXT if re.search(pattern, message)), FALLBACK_TEXT)


@dataclass(frozen=True)
class ActCtx:
    by_place: dict                  # id -> Place, places the trip currently schedules
    n_days: int
    variant_ids: set
    backup_ids: dict                # backup_pool id -> its entry ({"for", "reason", ...})
    day_members: list               # place ids of each day, in the schedule this act applies onto
    objective_names: set
    valid_paces: set
    slot_options: dict = field(default_factory=dict)    # place id -> the times of day it may be held to
    actual_visits: dict = field(default_factory=dict)


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
    elif t in ("set_visit", "clear_visit"):
        allowed = {"type", "place", "start", "duration_min"} if t == "set_visit" else {"type", "place"}
        if set(action) - allowed:
            raise ActionError("unknown visit field", say="Thông tin giờ ghé chưa đúng. Bạn chỉ nhập giờ và thời lượng nhé.")
        pid = action.get("place")
        day = _day_of(ctx, pid)
        if not _known(ctx, pid) or day is None:
            raise ActionError(f"{pid!r} is not currently in the plan")
        if t == "clear_visit":
            s.visit_overrides.pop(pid, None)
        else:
            if not {"start", "duration_min"} & set(action):
                raise ActionError("missing visit fields", say="Bạn nhập giờ ghé hoặc thời lượng muốn đổi nhé.")
            value = dict(s.visit_overrides.get(pid, {"start": None, "duration_min": None}))
            if "start" in action:
                start = action["start"]
                if start is not None and (not isinstance(start, str) or
                        re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", start) is None):
                    raise ActionError(f"bad time {start!r}")
                value["start"] = to_min(start) if start is not None else None
            if "duration_min" in action:
                duration = action["duration_min"]
                if duration is not None and (type(duration) is not int or not 1 <= duration <= 1440):
                    raise ActionError("bad visit duration", say="Thời lượng phải là số phút nguyên từ 1 đến 1440.")
                value["duration_min"] = duration
            if pid in s.locked_visits and any(v is not None and v != s.locked_visits[pid][k]
                                             for k, v in value.items()):
                raise ActionError("visit is locked", say="Nơi này đang khóa giờ và thời lượng. Bạn mở khóa trước khi sửa nhé.")
            if all(v is None for v in value.values()):
                s.visit_overrides.pop(pid, None)
            else:
                s.visit_overrides[pid] = value
    elif t == "lock_slot":
        pid = action.get("place")
        day = _day_of(ctx, pid)
        if not _known(ctx, pid) or day is None:
            raise ActionError(f"{pid!r} is not currently in the plan")
        if pid not in s.locked:
            s.locked.append(pid)
        if pid in ctx.actual_visits and pid not in s.locked_visits:
            s.locked_visits[pid] = dict(ctx.actual_visits[pid])
        s.assignment[pid] = day   # "ghim ngày": locking pins the place's current day, not just refuses to drop it
    elif t == "unlock":
        s.locked_visits.pop(action.get("place"), None)
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
    elif t == "set_slot":
        pid, slot = action.get("place_id"), action.get("slot")
        if not _known(ctx, pid):
            raise ActionError(f"unknown place {pid!r}")
        if slot not in ctx.slot_options.get(pid, ()):
            raise ActionError(f"slot {slot!r} is not possible for {pid!r}")
        s.slots[pid] = slot
    else:
        raise ActionError(f"unknown action {t!r}")
    s.last = t
    return s


def plan_key(state: State) -> dict:
    """What makes two versions the same plan: every edit, not which act was the last one."""
    return state.model_dump(mode="json", exclude={"last"})


class Session(BaseModel):
    id: str
    decision_session_id: str | None = None
    decision: dict
    states: list[State] = Field(default_factory=lambda: [State()])
    position: int = 0
    log: list[dict] = Field(default_factory=list)
    output: dict | None = None
    confirmed: dict | None = None       # the state confirm() turned into `output`; the plan is edited when it differs

    def edited(self) -> bool | None:
        """None before any confirm; else whether the current version differs from the confirmed one."""
        return None if self.confirmed is None else plan_key(self.state) != self.confirmed

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
