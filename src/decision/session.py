"""A Place Decision session: Search Input + what the user did, versioned for undo; in memory, mirrored to
data/decision/sessions/<id>.json so a reload or a restart resumes."""

import json
import re
import threading
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from trip import SearchInput
from requirements import Activity

Reason = Literal["far", "crowded", "pricey", "dislike", "visited"]
SID = re.compile(r"[0-9a-f]{12}")


class SoftAdd(BaseModel):
    feature: str
    value: str
    weight: Literal[1, -1]


class Profile(BaseModel):
    """Session Profile (docs/Project_Context.md §8): this trip only, never the long-term profile."""
    travel_mult: float = 1.0
    crowd_tolerance: Literal["avoid", "ok_if_worth", "fine"] | None = None
    price_sensitivity: float = 0.0
    soft: list[SoftAdd] = Field(default_factory=list)
    visited: list[str] = Field(default_factory=list)


class Drop(BaseModel):
    place_id: str
    reason: Reason | None = None


class Chip(BaseModel):
    id: str
    label: str


class Pending(BaseModel):
    qid: str
    text: str
    reason: str
    chips: list[Chip]
    data: dict = Field(default_factory=dict)


class Lodging(BaseModel):
    """Where the user sleeps, picked at Lựa chọn when the trip has no booked lodging: a served `stay` record, or a
    point from the lodging search box. Planning starts and ends every day here."""
    kind: Literal["corpus", "live", "address"]
    id: str | None = Field(default=None, max_length=80)
    text: str = Field(min_length=1, max_length=200)
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lng: float = Field(ge=-180, le=180, allow_inf_nan=False)
    price_vnd: int | None = Field(default=None, ge=0)


class State(BaseModel):
    selected: list[str] = Field(default_factory=list)  # includes locked and anchors still in the trip
    locked: list[str] = Field(default_factory=list)
    dropped: list[Drop] = Field(default_factory=list)
    relaxed: list[tuple[str, str]] = Field(default_factory=list)  # (place id, feature) the user agreed to relax
    wishlist: list[str] = Field(default_factory=list)
    profile: Profile = Field(default_factory=Profile)
    answered: list[str] = Field(default_factory=list)  # question ids answered or declined
    unmapped: list[str] = Field(default_factory=list)
    suggest_group: str | None = None  # "Gợi ý nơi tương tự" was answered for this display group
    last: str | None = None  # type of the last action
    shown: dict[str, list[str]] = Field(default_factory=dict)  # tab -> ids on screen, in screen order
    page: dict[str, int] = Field(default_factory=dict)  # tab -> page on screen (0 = first)
    chunk_assignments: dict[str, int] = Field(default_factory=dict)
    free_time: bool = False
    activities: dict[str, Activity] = Field(default_factory=dict)
    lodging: Lodging | None = None


class Session(BaseModel):
    id: str
    trip_session: str | None = None
    search_input: SearchInput
    state: State = Field(default_factory=State)
    history: list[State] = Field(default_factory=list)
    log: list[dict] = Field(default_factory=list)
    first_shortlist: int = 0
    output: dict | None = None


class Store:
    def __init__(self, root: Path | None):
        self.root = root
        self._mem: dict[str, Session] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def new(self, si: SearchInput, trip_session: str | None, state: State) -> Session:
        s = Session(id=uuid.uuid4().hex[:12], trip_session=trip_session, search_input=si, state=state)
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

    def lock(self, sid: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(sid, threading.Lock())
