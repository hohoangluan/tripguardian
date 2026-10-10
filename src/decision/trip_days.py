"""The days of the trip: date, weekday, day type and the usable window of each day (minutes after midnight)."""

from dataclasses import dataclass
from datetime import date, timedelta

from trip import nights as nights_of

from .geo import to_min

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


@dataclass(frozen=True)
class TripDay:
    index: int
    date: date | None
    weekday: str | None  # None when only the month is known
    day_type: str | None  # weekday | weekend
    start: int
    end: int


def trip_days(ctx, cfg) -> list[TripDay]:
    """ctx: trip.SearchInput.context. Missing days -> cfg.default_days (the caller flags it)."""
    n = ctx.days or cfg.default_days
    start, end = to_min(cfg.day_start), to_min(ctx.day_end or cfg.day_end)
    first = max(start, to_min(ctx.checkin_at)) if ctx.checkin_at else start
    # a trip that sleeps the night after its last day does not leave that day: only a departure the user stated cuts it
    sleeps_after = nights_of(ctx) >= n and not ctx.checkout_at
    last_end = end if sleeps_after else min(end, to_min(ctx.checkout_at or cfg.leave_at))
    out = []
    for i in range(n):
        # without a stated number of days the days are assumed: no dates, so no weekday-based checks
        d = ctx.start_date + timedelta(days=i) if ctx.start_date and ctx.days else None
        wd = DAYS[d.weekday()] if d else None
        out.append(TripDay(i, d, wd, ("weekend" if wd in ("sat", "sun") else "weekday") if wd else None,
                           first if i == 0 else start, last_end if i == n - 1 else end))
    return out


def month_of(ctx) -> int | None:
    return ctx.start_date.month if ctx.start_date else ctx.month
