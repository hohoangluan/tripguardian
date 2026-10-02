"""The days of the trip: date, weekday and the usable window of each day."""

from datetime import date, timedelta

from .model import Day
from .settings import Settings, to_min

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def trip_days(ctx: dict, cfg: Settings, home: str | None, entry: str | None, exit_: str | None) -> list[Day]:
    """ctx: trip_context["context"]. Day one opens at the entry point (else home) no earlier than arrive_at; the last
    day closes at the exit point (else home) no later than leave_at. Days and dates the user never gave stay unknown:
    without a start date there is no weekday, so no weekday-based check."""
    n = ctx.get("days") or cfg.default_days
    start = cfg.day_start
    end = to_min(ctx["day_end"]) if ctx.get("day_end") else cfg.day_end
    first = max(start, to_min(ctx["arrive_at"])) if ctx.get("arrive_at") else start
    last = min(end, to_min(ctx["leave_at"]) if ctx.get("leave_at") else cfg.leave_at)
    first_day = date.fromisoformat(ctx["start_date"]) if ctx.get("start_date") and ctx.get("days") else None
    out = []
    for i in range(n):
        d = first_day + timedelta(days=i) if first_day else None
        out.append(Day(index=i, date=d, weekday=WEEKDAYS[d.weekday()] if d else None,
                       start=first if i == 0 else start, end=last if i == n - 1 else end,
                       start_node=(entry or home) if i == 0 else home, end_node=(exit_ or home) if i == n - 1 else home))
    return out
