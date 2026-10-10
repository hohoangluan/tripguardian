"""The days of the trip: date, weekday and the usable window of each day."""

from datetime import date, timedelta

from trip import nights as nights_of
from trip import rents_bike

from .model import Day
from .settings import Settings, to_min

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def trip_days(ctx: dict, cfg: Settings, home: str | None, entry: str | None, exit_: str | None) -> list[Day]:
    """ctx: trip_context["context"]. Day one opens at the entry point (else home) no earlier than checkin_at; the last
    day closes at the exit point (else home) no later than checkout_at. Days and dates the user never gave stay unknown:
    without a start date there is no weekday, so no weekday-based check."""
    n = ctx.get("days") or cfg.default_days
    start = cfg.day_start
    end = to_min(ctx["day_end"]) if ctx.get("day_end") else cfg.day_end
    rent = rents_bike(ctx)   # arrived on foot, rides a rented motorbike: collect it first, return it before leaving
    first = max(start, to_min(ctx["checkin_at"]) + (cfg.rental["pickup_min"] if rent else 0)) if ctx.get("checkin_at") else start
    # a trip that sleeps the night after its last day does not leave that day: only a stated departure cuts it
    last = end if nights_of(ctx) >= n and not ctx.get("checkout_at") else \
        min(end, to_min(ctx["checkout_at"]) if ctx.get("checkout_at") else cfg.leave_at)
    if rent and ctx.get("checkout_at") and last == to_min(ctx["checkout_at"]):
        last -= cfg.rental["return_min"]
    first_day = date.fromisoformat(ctx["start_date"]) if ctx.get("start_date") and ctx.get("days") else None
    out = []
    for i in range(n):
        d = first_day + timedelta(days=i) if first_day else None
        out.append(Day(index=i, date=d, weekday=WEEKDAYS[d.weekday()] if d else None,
                       start=first if i == 0 else start, end=last if i == n - 1 else end,
                       start_node=(entry or home) if i == 0 else home, end_node=(exit_ or home) if i == n - 1 else home))
    return out
