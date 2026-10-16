"""Compile the trip's physical day windows once, before handing them downstream."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field as PydanticField, field_validator, model_validator

from .state import Evidence, Field, Frozen, Source

if TYPE_CHECKING:
    from .state import TripState

Clock = Annotated[str, PydanticField(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
Intensity = Literal["light", "normal", "full", "free"]
BusyKind = Literal["rest", "nap", "sleep", "work", "event"]


class FrameDefaults(Frozen):
    day_start: Clock = "08:00"
    day_end: Clock = "21:00"
    first_start: Clock = "14:00"
    last_end: Clock = "12:00"


class Moment(Frozen):
    at: str
    how: Literal["self", "bus", "plane"] | None = None  # None: the user gave the hour, not how they come

    @field_validator("at")
    @classmethod
    def _time(cls, value):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T([01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("moment must be YYYY-MM-DDTHH:MM")
        datetime.fromisoformat(value)
        return value


class DayPlan(Frozen):
    index: int = PydanticField(ge=0)
    start: Clock | None = None
    end: Clock | None = None
    intensity: Intensity | None = None
    source: Source = "user"
    evidence: tuple[Evidence, ...] = ()


class Busy(Frozen):
    label: str
    kind: BusyKind
    where: str
    start: Clock
    end: Clock
    on: Literal["all", "weekdays", "weekend"] | tuple[Annotated[int, PydanticField(ge=0)], ...] = "all"
    source: Source = "user"
    evidence: tuple[Evidence, ...] = ()

    @model_validator(mode="after")
    def _window(self):
        if self.start == self.end or (self.end < self.start and self.kind != "sleep"):
            raise ValueError("busy needs a positive window; only sleep can cross midnight")
        return self


class Meals(Frozen):
    skip: tuple[Literal["breakfast", "lunch", "dinner"], ...] = ()
    breakfast_at_lodging: bool = False
    snacks: bool = False
    shift_min: int = 0


class Rest(Frozen):
    every_min: int = PydanticField(gt=0)
    rest_min: int = PydanticField(gt=0)


class Period(Frozen):
    period: Literal["morning", "midday", "afternoon", "evening", "daytime", "sunrise", "sunset"]
    kinds: tuple[str, ...] = ()
    activity: str | None = None
    weight: int = PydanticField(default=1, ge=1, le=3)


class TripFrame(Frozen):
    arrive: Field[Moment] = Field[Moment]()
    leave: Field[Moment] = Field[Moment]()
    day_start: Field[Clock] = Field[Clock]()
    days: tuple[DayPlan, ...] = ()
    busy: tuple[Busy, ...] = ()
    drive_day_min: Field[Annotated[int, PydanticField(gt=0)]] = Field[Annotated[int, PydanticField(gt=0)]]()
    meals: Field[Meals] = Field[Meals]()
    rest: Field[Rest] = Field[Rest]()
    pattern: Field[Literal["interleave_kids"]] = Field[Literal["interleave_kids"]]()
    visit: dict[str, Annotated[int, PydanticField(gt=0)]] = {}
    periods: tuple[Period, ...] = ()


class BusyBlock(Frozen):
    start: Clock
    end: Clock
    kinds: tuple[BusyKind, ...]
    labels: tuple[str, ...]
    where: str | None


class DayFrame(Frozen):
    date: date
    start: Clock
    end: Clock
    busy: tuple[BusyBlock, ...] = ()
    intensity: Intensity = "normal"


class FrameIssue(Frozen):
    code: Literal["start_before_arrival", "end_after_departure", "arrive_not_on_first_day", "day_has_no_time"]
    day: int


class CompiledFrame(Frozen):
    days: tuple[DayFrame, ...]
    arrive: Moment | None = None
    leave: Moment | None = None
    drive_day_min: int | None = None
    periods: tuple[Period, ...] = ()
    visit: dict[str, int] = {}
    meals: Meals = Meals()
    rest: Rest | None = None
    pattern: Literal["interleave_kids"] | None = None
    issues: tuple[FrameIssue, ...] = ()


def _minutes(clock: str) -> int:
    h, m = map(int, clock.split(":"))
    return h * 60 + m


def _clock(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _applies(block: Busy, index: int, day: date) -> bool:
    if block.on == "all":
        return True
    if block.on == "weekdays":
        return day.weekday() < 5
    if block.on == "weekend":
        return day.weekday() >= 5
    return index in block.on


def _blocks(blocks: list[Busy], start: int, end: int) -> tuple[BusyBlock, ...]:
    clipped = []
    for block in blocks:
        # Overnight sleep closes the evening and blocks the following morning.
        spans = [(_minutes(block.start), _minutes(block.end))]
        if block.end < block.start:
            spans = [(_minutes(block.start), 1440), (0, _minutes(block.end))]
        for lo, hi in spans:
            lo, hi = max(start, lo), min(end, hi)
            if lo < hi:
                clipped.append((lo, hi, block))
    merged = []
    for lo, hi, block in sorted(clipped, key=lambda item: (item[0], item[1])):
        if merged and lo <= merged[-1][1]:
            old = merged[-1]
            old[1] = max(old[1], hi)
            old[2].append(block)
        else:
            merged.append([lo, hi, [block]])
    return tuple(BusyBlock(start=_clock(lo), end=_clock(hi),
                           kinds=tuple(dict.fromkeys(b.kind for b in members)),
                           labels=tuple(dict.fromkeys(b.label for b in members)),
                           where=members[0].where if all(b.where == members[0].where for b in members) else None)
                 for lo, hi, members in merged)


def compile_frame(state: TripState, arrival_buffer_min: int = 45, entry_min: int = 30,
                  defaults: FrameDefaults | None = None) -> CompiledFrame | None:
    """Physical arrival/departure bounds override wishes, never the other way around."""
    if not state.start_date.known or not state.days.known:
        return None
    if arrival_buffer_min < 0 or entry_min < 0:
        raise ValueError("arrival buffer and entry road minutes must be nonnegative")
    defaults = defaults or FrameDefaults()
    frame = state.frame
    first_date, count = state.start_date.value, state.days.value
    arrive = frame.arrive.value
    if arrive is None and state.inbound.value:
        arrive = Moment(at=state.inbound.value.arrive_at, how=state.inbound.value.mode)
    leave = frame.leave.value
    if leave is None and state.outbound.value:
        leave = Moment(at=state.outbound.value.depart_at, how=state.outbound.value.mode)
    buffer = timedelta(minutes=arrival_buffer_min + entry_min)
    ready = datetime.fromisoformat(arrive.at) + buffer if arrive else None
    done = datetime.fromisoformat(leave.at) - buffer if leave else None
    issues = []
    if arrive and datetime.fromisoformat(arrive.at).date() != first_date:
        issues.append(FrameIssue(code="arrive_not_on_first_day", day=0))
    plans = {plan.index: plan for plan in frame.days}
    days = []
    for index in range(count):
        day = first_date + timedelta(days=index)
        midnight = datetime.combine(day, time())
        plan = plans.get(index)
        start_wish = plan.start if plan and plan.start else state.checkin_at.value if index == 0 else None
        end_wish = plan.end if plan and plan.end else state.checkout_at.value if index == count - 1 else None
        start = _minutes(start_wish or (defaults.first_start if index == 0 and count > 1 else
                                       frame.day_start.value or defaults.day_start))
        end = _minutes(end_wish or (defaults.last_end if index == count - 1 and count > 1 else
                                   state.day_end.value or defaults.day_end))
        if ready:
            floor = int((ready - midnight).total_seconds() // 60)
            if start_wish and start < floor:
                issues.append(FrameIssue(code="start_before_arrival", day=index))
            if index == 0 and not start_wish and ready.date() == day:
                start = floor
            else:
                start = max(start, floor)
        if done:
            ceiling = int((done - midnight).total_seconds() // 60)
            if end_wish and end > ceiling:
                issues.append(FrameIssue(code="end_after_departure", day=index))
            if index == count - 1 and not end_wish and done.date() == day:
                end = ceiling
            else:
                end = min(end, ceiling)
        active = [block for block in frame.busy if _applies(block, index, day)]
        for block in active:
            if block.kind == "sleep" and block.end < block.start:
                end = min(end, _minutes(block.start))
                start = max(start, _minutes(block.end))
        # A date outside the physical interval has no representable playing time.
        # Equal bounds cannot turn a midnight overflow into a fake final minute.
        if start >= 1440 or end <= 0:
            start = end = 0
        busy = _blocks(active, start, end)
        intensity = plan.intensity if plan and plan.intensity else "normal"
        occupied = sum(_minutes(b.end) - _minutes(b.start) for b in busy)
        if end - start <= occupied:
            intensity = "free"
            issues.append(FrameIssue(code="day_has_no_time", day=index))
        days.append(DayFrame(date=day, start=_clock(start), end=_clock(end), busy=busy, intensity=intensity))
    return CompiledFrame(days=tuple(days), arrive=arrive, leave=leave, drive_day_min=frame.drive_day_min.value,
                         meals=frame.meals.value or Meals(), rest=frame.rest.value, pattern=frame.pattern.value,
                         visit=frame.visit, periods=frame.periods, issues=tuple(issues))
