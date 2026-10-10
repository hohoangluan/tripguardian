"""Clock for one day: given the order of the stops, when each is reached, how long it waits, and where the buffers,
rests and meals go. route.py tries orders through simulate(); validate.py re-checks the result independently.
"""

from dataclasses import dataclass

from .conditions import DayCond, queue_minutes, crowd_sensitive
from .model import Day, DayResult, Item, Place, Violation
from .places import windows_on
from .personalization import duration, preferred_start, suitability
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
    rain: float | None = None       # rain probability of the day; None = no forecast, rain is not considered
    prefs: dict | None = None       # place id -> how much the trip's soft weights want it (traits.preference)
    cond: DayCond | None = None     # what the date itself changes (conditions.py); None = nothing known, nothing changes
    crowd_tol: str | None = None    # the user's crowd tolerance: avoid | ok_if_worth | fine

    soft_weights: list | None = None
    allow_shrink: bool = True

    @property
    def wet(self) -> float | None:
        """Rain probability as the day's planning treats it: a heavy day counts as at least rain_high, a severe one as
        certain. None only when there is neither a forecast nor a heavy / severe signal."""
        level = self.cond.weather if self.cond else "none"
        if level == "none":
            return self.rain
        return max(self.rain or 0.0, self.cfg.rain_high if level == "heavy" else 1.0)


def intervals_for(place: Place, ctx: DayCtx) -> list[tuple[int, int]]:
    """When the place is open that day. Unknown hours or an unknown weekday do not constrain: the whole day, except
    that a shop-like place (a cafe, a restaurant) is never planned before unknown_hours_from on a guess."""
    w = windows_on(place.hours, ctx.day.weekday)
    if w is not None:
        return w
    shop = place.rec.get("identity", {}).get("category_group") in ctx.cfg.unknown_hours_groups
    return [(ctx.cfg.unknown_hours_from if shop else 0, DAY_MINUTES)]


def visit_minutes(place: Place, ctx: DayCtx, *, minimum: bool = False) -> int:
    """Automatic estimates include queues; exact durations already specify the whole visit block."""
    visit = duration(place, ctx.cfg, ctx.pace, ctx.soft_weights, minimum=minimum)
    return visit if place.requested_duration is not None else visit + queue_minutes(place, visit, ctx.cond, ctx.cfg)


def pin_window(place: Place, ctx: DayCtx) -> tuple[int, int]:
    """(earliest start, latest start) for a place known for a timed feature. One timed feature is reason enough to be
    there: a place known for both sunrise and sunset is pinned to one of them, not to their (empty) overlap. The pin
    taken is the first one the place's own opening hours can host for a visit of this pace, preferring one inside the
    day; a pin the place itself can never host (live music after closing time) does not pin it at all. A sun-based
    pin on a day with no known sun is ignored rather than guessed."""
    if place.requested_start is not None:
        return place.requested_start, place.requested_start
    wins = []
    for fid in place.pins:
        pin = ctx.cfg.pins[fid]
        if pin["anchor"] == "clock":
            wins.append((pin["from"], pin["to"]))
        elif ctx.sun is not None:
            base = ctx.sun[0] if pin["anchor"] == "sunrise" else ctx.sun[1]
            wins.append((base + pin["from_min"], base + pin["to_min"]))
    visit = visit_minutes(place, ctx, minimum=True)
    open_ = intervals_for(place, ctx)
    hosted = [(a, b) for a, b in wins if any(max(a, o) <= b and max(a, o) + visit <= c for o, c in open_)]
    in_day = [(a, b) for a, b in hosted if max(a, ctx.day.start) <= b and max(a, ctx.day.start) + visit <= ctx.day.end]
    return (in_day or hosted or [(0, DAY_MINUTES)])[0]


def _meal_slots(order: list[str], ctx: DayCtx) -> tuple[dict, list[str]]:
    """Meal places take the day's meal windows in order; the windows left over get a free block."""
    names = list(ctx.cfg.meal_windows)[: ctx.cfg.meals_per_day]
    reachable = [n for n in names if ctx.cfg.meal_windows[n][1] >= ctx.day.start]    # a window already over is not claimed
    claimed: dict = {}
    for pid in (p for p in order if ctx.places[p].kind == "meal"):
        p = ctx.places[pid]
        lo, hi = pin_window(p, ctx)                     # a dinner place known for evening music takes dinner
        need = visit_minutes(p, ctx, minimum=True)
        # a meal window the place can host: open then (an afternoon-only place never takes lunch) and at its pin
        fits = [n for n in reachable if n not in claimed.values()
                and any(max(lo, o, ctx.cfg.meal_windows[n][0]) <= min(hi, ctx.cfg.meal_windows[n][1], c - need)
                        for o, c in intervals_for(p, ctx))]
        if fits:
            claimed[pid] = fits[0]
        # no window fits: the place is visited like any other stop, the meals stay free blocks
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


def _evening(t: int, items: list, free: list, served: set, notes: list, ctx: DayCtx) -> int:
    """After the last stop the traveller is still in town until the day's end: a meal window the day still reaches
    gets its free block (no rest is needed after the last stop). A window already over is noted as missed."""
    cfg, day = ctx.cfg, ctx.day
    for name in free:
        a, b = cfg.meal_windows[name]
        if name in served or b < day.start:
            continue
        m = max(t, a)
        if m <= b and m + cfg.meal_min <= day.end:
            items.append(Item("meal_free", m, m + cfg.meal_min, name=name, note="free"))
            served.add(name)
            t = m + cfg.meal_min
        elif t > b:
            notes.append(f"meal_missed:{name}")
    return t


def simulate(order: list[str], ctx: DayCtx, shrink: bool = True) -> DayResult:
    """shrink=False keeps every visit at the pace's length: robustness asks whether the day survives a delay as
    planned, not whether it survives by cutting visits short."""
    cfg, day, travel = ctx.cfg, ctx.day, ctx.travel
    shrink = shrink and ctx.allow_shrink
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
        visit = visit_minutes(p, ctx)
        lo, hi = pin_window(p, ctx)
        if pid in claimed and p.requested_start is None:
            a, b = cfg.meal_windows[claimed[pid]]
            lo, hi = max(lo, a), min(hi, b)
        if pid in claimed:
            served.add(claimed[pid])
        pin_lo = pin_window(p, ctx)[0]
        start, why = None, "opening"
        shortest = visit_minutes(p, ctx, minimum=True)
        shortest = min(visit, shortest) if shrink else visit
        for o, c in intervals_for(p, ctx):
            s = max(t, o, lo)
            if idx == len(order) - 1 and p.requested_duration is None:
                for name in free:
                    a, b = cfg.meal_windows[name]
                    if name not in served and a <= s <= b and a + cfg.meal_min <= day.end:
                        c = min(c, b, day.end - cfg.meal_min)
            # The visit is an estimate range: when the pace's length does not fit the opening block or what is
            # left of the day, it shrinks toward the short estimate, never below it.
            room = min(c, day.end) - s
            if s <= hi and room >= shortest:
                if p.requested_start is None:
                    s = preferred_start(p, s, min(hi, c - visit, day.end - visit), cfg, ctx.soft_weights)
                    room = min(c, day.end) - s
                start, visit = s, min(visit, room)
                why = "opening" if s == o and o > max(t, lo) else "meal" if pid in claimed and s == lo > pin_lo else "pin"
                break
        if start is None:
            viol.append(Violation("hours", day.index, pid, 0, False, "no feasible start"))
            start = t
        elif start > t:
            # A meal that falls inside a long wait is eaten there, not skipped. With no start point the day simply
            # opens at the first stop: nothing is waited out, but a meal the traveller is already in town for (an
            # arrival at noon, a sunset stop as the first one) still gets its block from the day's start.
            w_at = t
            for name in free:
                a, b = cfg.meal_windows[name]
                m = max(w_at, a)
                if name not in served and m <= b and m + cfg.meal_min <= start:
                    if m > w_at and here is not None:
                        items.append(Item("wait", w_at, m, place_id=pid, note=why))
                        wait_min += m - w_at
                    items.append(Item("meal_free", m, m + cfg.meal_min, name=name, note="free"))
                    served.add(name)
                    w_at, active = m + cfg.meal_min, 0
            if start > w_at and here is not None:
                items.append(Item("wait", w_at, start, place_id=pid, note=why))
                wait_min += start - w_at
            t = start
        items.append(Item("visit", start, start + visit, place_id=pid, name=p.name))
        t, active, here = start + visit, active + visit, pid
        nxt = order[idx + 1] if idx + 1 < len(order) else day.end_node
        if nxt is not None and nxt != pid:
            buffer = cfg.buffer_min[ctx.pace]
            if travel.leg(pid, nxt)[0] > cfg.long_leg_min:
                buffer += cfg.buffer_extra_long
            if p.hours_status in ("UNCERTAIN", "OUTDATED"):
                buffer += cfg.buffer_extra_uncertain
            if ctx.wet is not None and ctx.wet >= cfg.rain_high:
                buffer += cfg.buffer_extra_rain
            if crowd_sensitive(p, ctx.cond, cfg):
                buffer += cfg.conditions["crowd_buffer_min"][ctx.cond.crowd]
            if ctx.cond and ctx.cond.closure_risk and p.kind == "meal":
                buffer += cfg.conditions["closure_buffer_min"]
            items.append(Item("buffer", t, t + buffer))
            t += buffer
    if order and day.end_node not in (None, here):
        t, active = _breaks(t, active, items, free, served, notes, ctx)
        move(here, day.end_node)
    if t > day.end:
        viol.append(Violation("day_window", day.index, None, t - day.end, False, "the day runs past its end"))
    end = t                 # when the stops are done: what an order is judged on, the evening meals aside
    if order:
        _evening(t, items, free, served, notes, ctx)
    fit = sum(suitability(ctx.places[it.place_id], it.start, cfg, ctx.soft_weights)
              for it in items if it.kind == "visit")
    penalty = -cfg.personalization.get("time_weight_min", 60) * fit
    return DayResult(tuple(items), tuple(order), tuple(viol), travel_min, wait_min, end, tuple(notes), "single",
                     timing_penalty=penalty)
