"""The values Planning passes between its steps. All times are minutes after midnight."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    kind: str                       # experience | meal
    role: str                       # anchor | locked | selected (from Place Decision)
    lat: float
    lng: float
    area: str | None
    dup_group: int | None           # places sharing it are near duplicates
    hours: dict | None              # weekday -> [(open, close)]; None = the record has no hours
    hours_status: str | None
    visit: dict                     # short / typical / long minutes
    cost_vnd: int | None            # estimated per person; None = unknown, never guessed
    pins: tuple[str, ...]           # timed features the place is known for
    flags: tuple[str, ...]          # warning texts Place Decision attached
    relaxed: tuple[str, ...]        # hard filters the user relaxed for this place
    rec: dict                       # the serving record, for the hard-constraint check
    activity: str | None = None
    activity_explicit: bool = False
    meal_kind: str | None = None    # roles.meal_kind: main | breakfast | light | night_meal


@dataclass(frozen=True)
class Unplaced:
    id: str
    name: str
    reason: str                     # no_record | not_plannable | no_coordinates | no_visit_time


@dataclass(frozen=True)
class Point:
    lat: float
    lng: float
    text: str
    source: str                     # corpus | nominatim
    fetched_at: str | None


@dataclass(frozen=True)
class Day:
    index: int
    date: date | None
    weekday: str | None             # None when the trip has no dates
    start: int
    end: int
    start_node: str | None          # where the day opens: home, or the entry point on day one
    end_node: str | None            # where it closes: home, or the exit point on the last day
    busy: tuple = ()                # (start, end, kind, label, where): what the user does at fixed times, as Trip
                                    # compiled them; `blocks` is the part inside the day's current window
    intensity: str = "normal"       # light | normal | full | free (Trip frame)
    start_by_user: bool = False     # the start is the user's (their day start, arrival, check-in): never moved earlier
    depart_by: int | None = None    # last day: at the departure point by then (leave - leave_buffer_min); physical

    @property
    def blocks(self) -> tuple:
        """The fixed-time blocks inside the day's window, clipped to it. The window moves (arrival, departure, an
        edit, a dawn start) while `busy` keeps the user's blocks whole, so no move can lose one."""
        return tuple((max(self.start, a), min(self.end, b), *rest) for a, b, *rest in self.busy
                     if max(self.start, a) < min(self.end, b))


@dataclass(frozen=True)
class Item:
    kind: str                       # visit | travel | wait | free | rest | meal_free | busy
    start: int
    end: int
    place_id: str | None = None
    name: str | None = None
    from_id: str | None = None
    to_id: str | None = None
    mode: str | None = None         # travel: walk | motorbike | car
    note: str | None = None         # travel: "+N" = N buffer minutes inside the leg; free: the stop it is spent around;
                                    # busy: its kind (name = the user's label); rest: home | drop_bags | None (pace)

    @property
    def road_min(self) -> int:
        """Minutes of the leg itself: its length without the buffer that rides on it."""
        extra = int(self.note[1:]) if self.kind == "travel" and self.note and self.note.startswith("+") else 0
        return self.end - self.start - extra


@dataclass(frozen=True)
class Violation:
    kind: str                       # hours | timed | overlap | day_window | travel | long_leg | anchor | budget
    day: int | None                 #        | hard | duplicate | hazard | busy | departure | drive_day
    place_id: str | None
    minutes: int
    physical: bool                  # a physical constraint is never relaxed
    detail: str


@dataclass(frozen=True)
class DayResult:
    items: tuple[Item, ...]
    order: tuple[str, ...]
    violations: tuple[Violation, ...]   # what the simulation tripped over; validate.py decides pass / fail
    travel_min: int
    wait_min: int
    end: int
    notes: tuple[str, ...] = ()
    method: str = ""                # exact | heuristic | single
    unpinned: tuple[str, ...] = ()  # places whose time-of-day pin was given up to fit the day (the user is told)
    time_penalty: float = 0.0
    time_details: tuple[dict, ...] = ()
    pin_conflicts: tuple[tuple[str, tuple[str, ...]], ...] = ()

    @property
    def key(self) -> tuple[int, int, float]:
        """Validity and meals precede soft timing and elapsed time."""
        route_end = max((it.end for it in self.items if it.note != 'optional'), default=self.end)
        return (len(self.violations), sum(n.startswith("meal_missed") for n in self.notes), route_end + self.time_penalty)
