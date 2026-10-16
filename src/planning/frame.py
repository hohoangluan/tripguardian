"""The days of the trip: date, weekday and the usable window of each day."""

from datetime import date, timedelta

from .model import Day
from .settings import Settings, to_min

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
PRIOR_SOURCES = (None, "default", "profile")    # who filled a field when the user did not say it (spec section 4)


def user_set(sources: dict | None, key: str) -> bool:
    """The user gave this trip field (trip_context["sources"]): not a default and not a profile / pattern prior."""
    return (sources or {}).get(key) not in PRIOR_SOURCES


def start_said(ctx: dict, sources: dict | None, i: int, n: int) -> bool:
    """Day i's start in the CompiledFrame is one the user said: that day's own start, their check-in hour on day one,
    or their trip-wide day start, which Trip uses for every day but a longer trip's first (compile_frame)."""
    if user_set(sources, f"frame.days.{i}.start"):
        return True
    if (sources or {}).get(f"frame.days.{i}.start") is not None:
        return False                    # the day has a start of its own, from a prior
    if i == 0 and ctx.get("checkin_at") and user_set(sources, "checkin_at"):
        return True
    return user_set(sources, "frame.day_start") and not (i == 0 and n > 1)


def end_said(ctx: dict, sources: dict | None, i: int, n: int) -> bool:
    """Day i's end in the CompiledFrame is one the user said: that day's own end, or their check-out hour on the last
    day. Otherwise a leave day's end is Trip's ceiling (departure - buffer - fixed road), which Planning replaces."""
    if user_set(sources, f"frame.days.{i}.end"):
        return True
    if (sources or {}).get(f"frame.days.{i}.end") is not None:
        return False                    # the day has an end of its own, from a prior
    return i == n - 1 and bool(ctx.get("checkout_at")) and user_set(sources, "checkout_at")


def arrives_on(ctx: dict, d: date | None) -> bool:
    """The trip's arrival (frame.arrive, else arrive_at without a frame) falls on day d: day one cannot start earlier."""
    arrive = ((ctx.get("frame") or {}).get("arrive") or {}).get("at")
    if arrive:
        return d is not None and arrive[:10] == d.isoformat()
    return bool(ctx.get("arrive_at"))


def trip_days(ctx: dict, cfg: Settings, home: str | None, entry: str | None = None, exit_: str | None = None,
              sources: dict | None = None) -> list[Day]:
    """ctx: trip_context["context"]. Every day starts and ends at home (the lodging); with a CompiledFrame, day one
    opens at the entry point and the last day closes at the exit point when those are known. Without a frame: day one
    opens no earlier than checkin_at / arrive_at, the last day closes no later than checkout_at / leave_at. Days and
    dates the user never gave stay unknown: without a start date there is no weekday, so no weekday-based check.
    sources: trip_context["sources"] (field -> who set it); a day start the user set is marked start_by_user."""
    if frame := ctx.get("frame"):
        out = []
        n = len(frame["days"])
        for i, day in enumerate(frame["days"]):
            d = date.fromisoformat(day["date"]) if isinstance(day["date"], str) else day["date"]
            start = to_min(day["start"])
            free = day.get("intensity") == "free"
            busy = tuple((to_min(b["start"]), to_min(b["end"]), b["kinds"][0], b["labels"][0], b.get("where"))
                         for b in day.get("busy") or ())
            first, last = i == 0, i == n - 1
            by_user = start_said(ctx, sources, i, n) or first and arrives_on(ctx, d)
            out.append(Day(index=i, date=d, weekday=WEEKDAYS[d.weekday()], start=start,
                           end=start if free else to_min(day["end"]),
                           start_node=entry if first and entry else home,
                           end_node=exit_ if last and exit_ else home,
                           busy=busy, intensity=day.get("intensity") or "normal", start_by_user=by_user))
        return out
    n = ctx.get("days") or cfg.default_days
    start = cfg.day_start
    end = to_min(ctx["day_end"]) if ctx.get("day_end") else cfg.day_end
    first_at = ctx.get("checkin_at") or ctx.get("arrive_at")
    last_at = ctx.get("checkout_at") or ctx.get("leave_at")
    first = max(start, to_min(first_at)) if first_at else start
    last = min(end, to_min(last_at) if last_at else cfg.leave_at)
    first_day = date.fromisoformat(ctx["start_date"]) if ctx.get("start_date") and ctx.get("days") else None
    out = []
    for i in range(n):
        d = first_day + timedelta(days=i) if first_day else None
        out.append(Day(index=i, date=d, weekday=WEEKDAYS[d.weekday()] if d else None,
                       start=first if i == 0 else start, end=last if i == n - 1 else end,
                       start_node=home, end_node=home, start_by_user=i == 0 and (
                           arrives_on(ctx, d) or bool(ctx.get("checkin_at")) and user_set(sources, "checkin_at"))))
    return out
