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


@dataclass(frozen=True)
class Item:
    kind: str                       # visit | travel | wait | buffer | rest | meal_free
    start: int
    end: int
    place_id: str | None = None
    name: str | None = None
    from_id: str | None = None
    to_id: str | None = None
    mode: str | None = None         # travel: walk | motorbike | car | ride
    note: str | None = None


@dataclass(frozen=True)
class Violation:
    kind: str                       # hours | timed | overlap | day_window | travel | long_leg | anchor | budget
    day: int | None                 #        | hard | duplicate
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

    @property
    def key(self) -> tuple[int, int, int]:
        """Fewer violations first, then fewer skipped meals, then the earlier the day ends."""
        return (len(self.violations), sum(n.startswith("meal_missed") for n in self.notes), self.end)
