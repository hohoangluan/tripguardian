"""Clock for one day: given the order of the stops, when each is reached, how long it waits, and where the buffers,
rests and meals go. route.py tries orders through simulate(); validate.py re-checks the result independently.
"""

from dataclasses import dataclass

from .model import Day, DayResult, Item, Place, Violation
from .places import windows_on
from .settings import Settings
from .travel import Travel

DAY_MINUTES = 1440


@dataclass(frozen=True)
class DayCtx:
    day: Day
    places: dict                    # id -> Place
    travel: Travel
    cfg: Settings
    pace: str
    sun: tuple[int, int] | None     # (sunrise, sunset) of the day; None when the date or place is unknown


def intervals_for(place: Place, ctx: DayCtx) -> list[tuple[int, int]]:
    """When the place is open that day. Unknown hours or an unknown weekday do not constrain: the whole day."""
    w = windows_on(place.hours, ctx.day.weekday)
    return [(0, DAY_MINUTES)] if w is None else w


def pin_window(place: Place, ctx: DayCtx) -> tuple[int, int]:
    """(earliest start, latest start) for a place known for a timed feature. A sun-based pin on a day with no known
    sun is ignored rather than guessed."""
    lo, hi = 0, DAY_MINUTES
    for fid in place.pins:
        pin = ctx.cfg.pins[fid]
        if pin["anchor"] == "clock":
            a, b = pin["from"], pin["to"]
        elif ctx.sun is None:
            continue
        else:
            base = ctx.sun[0] if pin["anchor"] == "sunrise" else ctx.sun[1]
            a, b = base + pin["from_min"], base + pin["to_min"]
        lo, hi = max(lo, a), min(hi, b)
    return lo, hi


def _meal_slots(order: list[str], ctx: DayCtx) -> tuple[dict, list[str]]:
    """Meal places take the day's meal windows in order; the windows left over get a free block."""
    names = list(ctx.cfg.meal_windows)[: ctx.cfg.meals_per_day]
    reachable = [n for n in names if ctx.cfg.meal_windows[n][1] >= ctx.day.start]    # a window already over is not claimed
    meal_ids = [pid for pid in order if ctx.places[pid].kind == "meal"]
    claimed = dict(zip(meal_ids, reachable))
    return claimed, [n for n in names if n not in claimed.values()]


def _breaks(t: int, active: int, items: list, free: list, served: set, notes: list, ctx: DayCtx) -> tuple[int, int]:
    """Put the meal blocks that are due at time t, and a rest when active minutes ran too long."""
    cfg = ctx.cfg
    for name in free:
        a, b = cfg.meal_windows[name]
        if name in served or t < a:
            continue
        served.add(name)
        if t <= b:
            items.append(Item("meal_free", t, t + cfg.meal_min, name=name, note="free"))
            t, active = t + cfg.meal_min, 0
        else:
            notes.append(f"meal_missed:{name}")
    if active >= cfg.max_consecutive_min[ctx.pace]:
        items.append(Item("rest", t, t + cfg.rest_min[ctx.pace]))
        t, active = t + cfg.rest_min[ctx.pace], 0
    return t, active


def simulate(order: list[str], ctx: DayCtx) -> DayResult:
    cfg, day, travel = ctx.cfg, ctx.day, ctx.travel
    claimed, free = _meal_slots(order, ctx)
    t, here, active = day.start, day.start_node, 0
    items: list[Item] = []
    viol: list[Violation] = []
    notes: list[str] = []
    served: set = set()
    travel_min = wait_min = 0

    def move(frm: str | None, to: str | None):
        nonlocal t, active, travel_min
        if frm is None or to is None or frm == to:
            return
        m, mode = travel.leg(frm, to)
        items.append(Item("travel", t, t + m, from_id=frm, to_id=to, mode=mode))
        t, active, travel_min = t + m, active + m, travel_min + m

    for idx, pid in enumerate(order):
        p = ctx.places[pid]
        t, active = _breaks(t, active, items, free, served, notes, ctx)
        move(here, pid)
        visit = p.visit[cfg.visit_key[ctx.pace]]
        lo, hi = pin_window(p, ctx)
        if pid in claimed:
            a, b = cfg.meal_windows[claimed[pid]]
            lo, hi = max(lo, a), min(hi, b)
            served.add(claimed[pid])
        pin_lo = pin_window(p, ctx)[0]
        start, why = None, "opening"
        for o, c in intervals_for(p, ctx):
            s = max(t, o, lo)
            if s <= hi and s + visit <= c:
                start = s
                why = "opening" if s == o and o > max(t, lo) else "meal" if pid in claimed and s == lo > pin_lo else "pin"
                break
        if start is None:
            viol.append(Violation("hours", day.index, pid, 0, False, "no feasible start"))
            start = t
        elif start > t:
            if here is not None:
                w_at = t
                for name in free:       # a meal that falls inside a long wait is eaten there, not skipped
                    a, b = cfg.meal_windows[name]
                    m = max(w_at, a)
                    if name not in served and m <= b and m + cfg.meal_min <= start:
                        if m > w_at:
                            items.append(Item("wait", w_at, m, place_id=pid, note=why))
                            wait_min += m - w_at
                        items.append(Item("meal_free", m, m + cfg.meal_min, name=name, note="free"))
                        served.add(name)
                        w_at, active = m + cfg.meal_min, 0
                if start > w_at:
                    items.append(Item("wait", w_at, start, place_id=pid, note=why))
                    wait_min += start - w_at
            t = start       # with no start point the day simply opens at the first stop: nothing is waited out
        items.append(Item("visit", start, start + visit, place_id=pid, name=p.name))
        t, active, here = start + visit, active + visit, pid
        nxt = order[idx + 1] if idx + 1 < len(order) else day.end_node
        if nxt is not None and nxt != pid:
            buffer = cfg.buffer_min[ctx.pace]
            if travel.leg(pid, nxt)[0] > cfg.long_leg_min:
                buffer += cfg.buffer_extra_long
            if p.hours_status in ("UNCERTAIN", "OUTDATED"):
                buffer += cfg.buffer_extra_uncertain
            items.append(Item("buffer", t, t + buffer))
            t += buffer
    if order and day.end_node not in (None, here):
        t, active = _breaks(t, active, items, free, served, notes, ctx)
        move(here, day.end_node)
    elif order:             # a day that just ends after its last stop needs no breaks, but a missed meal is still noted
        notes += [f"meal_missed:{n}" for n in free if n not in served and t > cfg.meal_windows[n][1]
                  and cfg.meal_windows[n][1] >= day.start]
    if t > day.end:
        viol.append(Violation("day_window", day.index, None, t - day.end, False, "the day runs past its end"))
    return DayResult(tuple(items), tuple(order), tuple(viol), travel_min, wait_min, t, tuple(notes), "single")
