"""Clock for one day: given the order of the stops, when each is reached, how long it waits, and where the buffers,
rests and meals go. route.py tries orders through simulate(); validate.py re-checks the result independently.
"""

from dataclasses import dataclass, fields, replace

from .cache import put
from .conditions import DayCond, queue_minutes, crowd_sensitive
from .details import official_last_entry
from .model import Day, DayResult, Item, Place, Violation
from .places import windows_on
from .roles import DAWN_FIRST, ROLE_SLOTS, takes_meal_slot
from .settings import Settings
from .travel import Travel
from .timefit import visit_score, windows_for
from .traits import visit_minutes

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
    purpose: str | None = None
    time_preferences: tuple = ()
    allow_shrink: bool = True
    mobility: str | None = None     # how the trip gets around (motorbike | car | walk); None = not known
    require_meals: bool = False     # full itineraries enforce coverage; standalone timeline fragments may omit meals
    home: str | None = None         # the lodging node; None = not known
    meal_skip: frozenset = frozenset()       # meals the user skips (or eats at the lodging)
    rest: tuple[int, int] | None = None      # (every_min, rest_min) the user said; None = the pace's
    drop_bags: bool = False                  # day one reaches the city before check-in: stop at the lodging first
    compact_estimates: bool = False          # recover earlier estimate ranges when laying out a full frame
    meal_cuts: dict | None = None            # replay-local free-meal minutes, never a change to Settings

    @property
    def wet(self) -> float | None:
        """Rain probability as the day's planning treats it: a heavy day counts as at least rain_high, a severe one as
        certain. None only when there is neither a forecast nor a heavy / severe signal."""
        level = self.cond.weather if self.cond else "none"
        if level == "none":
            return self.rain
        return max(self.rain or 0.0, self.cfg.rain_high if level == "heavy" else 1.0)


def intervals_for(place: Place, ctx: DayCtx) -> list[tuple[int, int]]:
    """When the place is open that day. Unknown hours or an unknown weekday do not constrain: the whole day."""
    w = windows_on(place.hours, ctx.day.weekday)
    return [(0, DAY_MINUTES)] if w is None else w


def pin_window(place: Place, ctx: DayCtx, *, _intervals: list[tuple[int, int]] | None = None) -> tuple[int, int]:
    """(earliest start, latest start) for a place known for a timed feature or with an official last entry. One timed feature is reason enough to be
    there: a place known for both sunrise and sunset is pinned to one of them, not to their (empty) overlap. The pin
    taken is the first one the place's own opening hours can host for a visit of this pace, preferring one inside the
    day; a pin the place itself can never host (live music after closing time) does not pin it at all. A sun-based
    pin on a day with no known sun is ignored rather than guessed."""
    wins, fids = [], []
    for fid in place.pins:
        pin = ctx.cfg.pins[fid]
        if pin["anchor"] == "clock":
            wins.append((pin["from"], pin["to"]))
            fids.append(fid)
        elif ctx.sun is not None:
            base = ctx.sun[0] if pin["anchor"] == "sunrise" else ctx.sun[1]
            wins.append((base + pin["from_min"], base + pin["to_min"]))
            fids.append(fid)
    visit = min(place.visit[ctx.cfg.visit_key[ctx.pace]], place.visit["short"])
    open_ = intervals_for(place, ctx) if _intervals is None else _intervals
    hosted = [(a, b) for a, b in wins if any(max(a, o) <= b and max(a, o) + visit <= c for o, c in open_)]
    in_day = [(a, b) for a, b in hosted if max(a, ctx.day.start) <= b and max(a, ctx.day.start) + visit <= ctx.day.end]
    # A place known for dawn and for sunset is a dawn place (spec section 5): the dawn window is kept even when it starts
    # before the day, because build.pull_early then moves the day's start to it. A start the user set is never moved
    # (spec section 4), so on such a day the place takes the pin that fits inside it (see dawn_swapped).
    if not ctx.day.start_by_user and fids and fids[0] in DAWN_FIRST and wins[0] in hosted:
        in_day = [wins[0]]
    lo, hi = (in_day or hosted or [(0, DAY_MINUTES)])[0]
    last = official_last_entry(place)  # the place's own site: nobody is let in after it
    return (lo, hi if last is None else min(hi, last))


def dawn_swapped(place: Place, ctx: DayCtx) -> bool:
    """A dawn-first place that took a later time of day because the day's start is the user's (pin_window)."""
    if not (ctx.day.start_by_user and ctx.sun and len(place.pins) > 1 and place.pins[0] in DAWN_FIRST):
        return False
    pin = ctx.cfg.pins[place.pins[0]]
    base = ctx.sun[0] if pin["anchor"] == "sunrise" else ctx.sun[1]
    return pin_window(place, ctx)[0] > base + pin["to_min"]


_FLOORS: dict = {}       # pin_duration_floor memo: identity key -> (the objects keyed on, minutes)


def pin_duration_floor(place: Place, ctx: DayCtx) -> int:
    """Memoized _pin_duration_floor. The key is the identity of the place and of every other field of the day
    context (contexts are frozen and built with dataclasses.replace, so a day relaid or re-tried with other places
    released shares these objects); the entry holds the objects, so an id is never reused while it lives. A binary
    search of single-stop clocks per pinned stop per clock was a quarter of an edit's time."""
    refs = (place,) + tuple(getattr(ctx, f.name) for f in fields(ctx) if f.name != "places")
    key = tuple(map(id, refs))
    hit = _FLOORS.get(key)
    if hit is not None and all(a is b for a, b in zip(hit[0], refs)):
        return hit[1]
    if len(_FLOORS) >= 4096:
        _FLOORS.clear()
    minutes = _pin_duration_floor(place, ctx)
    _FLOORS[key] = (refs, minutes)
    return minutes


def _pin_duration_floor(place: Place, ctx: DayCtx) -> int:
    """How short a full-frame visit with a time of day may get: its pace length, unless even this place alone on the
    day cannot keep its time of day at pace (the day's end, the road home, a fixed meal at its shortest); then the
    longest length that does fit. Spec section 5: the time of day wins over pace, but other stops move (or shrink)
    before this visit gives up minutes it could keep. Outside full frames, the short estimate as before."""
    full = visit_minutes(place, ctx.cfg, ctx.pace, ctx.prefs)
    low = min(full, place.visit["short"])
    if not ctx.compact_estimates or not place.pins or low == full:
        return low
    from .validate import validate
    cfg = replace(ctx.cfg, meal_durations={n: min(m, ctx.cfg.realistic["meal_min"])
                                          for n, m in ctx.cfg.meal_durations.items()})

    def fits(minutes):
        p = replace(place, visit={**place.visit, **dict.fromkeys(("short", "typical", "long"), minutes)})
        one = replace(ctx, places={p.id: p}, cfg=cfg)     # full-frame meal rules, no minute recovery (shrink=False)
        return not validate([one], [simulate([p.id], one, shrink=False)], [], set(), None, None)

    if not fits(full):
        high = full - 1
        while low < high:
            middle = (low + high + 1) // 2
            if fits(middle):
                low = middle
            else:
                high = middle - 1
        full = low
    return full


class _SimulationCache:
    """Inputs and repeated interval scores for one route search, never shared across contexts."""

    def __init__(self, ids: list[str], ctx: DayCtx):
        self.ctx = ctx
        self.intervals = {pid: intervals_for(ctx.places[pid], ctx) for pid in ids}
        self.pins = {pid: pin_window(ctx.places[pid], ctx, _intervals=self.intervals[pid]) for pid in ids}
        self.rules = {pid: windows_for(ctx.places[pid], ctx) for pid in ids}
        self.scores: dict = {}
        self.legs: dict = {}
        self.meals: dict = {}            # allocation depends on meal order, not on the intervening sight visits
        self.simulations: dict = {}      # local-search moves often revisit an order within this context
        self.durations = {}
        for pid in ids:
            p = ctx.places[pid]
            visit = visit_minutes(p, ctx.cfg, ctx.pace, ctx.prefs)
            short = pin_duration_floor(p, ctx) if ctx.compact_estimates and p.pins else min(visit, p.visit["short"])
            self.durations[pid] = (visit + queue_minutes(p, visit, ctx.cond, ctx.cfg),
                                   short + queue_minutes(p, short, ctx.cond, ctx.cfg))

    def score(self, place: Place, start: int, end: int) -> tuple[float, dict]:
        key = (place.id, start, end)
        if key in self.scores:
            return self.scores[key]
        return put(self.scores, key, visit_score(place, start, end, self.ctx, _rules=self.rules[place.id]),
                   self.ctx.cfg.cache_entries)

    def leg(self, frm: str, to: str) -> tuple[int, str]:
        key = (frm, to)
        if key in self.legs:
            return self.legs[key]
        return put(self.legs, key, self.ctx.travel.leg(frm, to), self.ctx.cfg.cache_entries)


def _role_fits(place: Place, slot: str) -> bool:
    """A breakfast place takes breakfast or lunch, a hot-pot place lunch or dinner, a night market dinner; a place with
    no role fits any slot."""
    return place.meal_kind not in ROLE_SLOTS or slot in ROLE_SLOTS[place.meal_kind]


def meal_visit_fits(place: Place, slot: str, ctx: DayCtx, cache: _SimulationCache | None = None) -> bool:
    """A selected meal needs its whole shortest visit and the road to each fixed block, not just a free-meal floor.
    Slot windows constrain the start; opening hours and the day end constrain the entire visit."""
    lo, hi = cache.pins[place.id] if cache else pin_window(place, ctx)
    need = min(place.visit[ctx.cfg.visit_key[ctx.pace]], place.visit["short"])
    wa, wb = ctx.cfg.meal_windows[slot]
    for o, c in (cache.intervals[place.id] if cache else intervals_for(place, ctx)):
        start = max(ctx.day.start, lo, wa, o)
        for a, b, _, _, where in ctx.day.blocks:
            at = busy_place(where, ctx)
            back = ctx.travel.leg(place.id, at)[0] if at and at != place.id else 0
            if start < b and start + need + back > a:
                road = ctx.travel.leg(at, place.id)[0] if at and at != place.id else 0
                start = b + road
        if start <= min(hi, wb, c - need, ctx.day.end - need):
            return True
    return False


def _meal_slots(order: list[str], ctx: DayCtx, cache: _SimulationCache | None = None) -> tuple[dict, list[str]]:
    """Meal places take the day's meal windows in order; the windows left over get a free block."""
    meal_ids = [p for p in order if takes_meal_slot(ctx.places[p])]
    breakfast_role = any(ctx.places[pid].meal_kind == 'breakfast' for pid in meal_ids)
    key = tuple(order) if breakfast_role else tuple(meal_ids)
    if cache is not None and key in cache.meals:
        claimed, free = cache.meals[key]
        return dict(claimed), list(free)       # reclaim() may move a claim after a busy block
    names = meal_names(ctx)
    reachable = day_meals(ctx)
    claimed: dict = {}
    earliest = {}
    if breakfast_role:
        # A lower bound ignores waits, buffers and breaks: even this arrival must reach a breakfast claim in time.
        clock, here = ctx.day.start, ctx.day.start_node
        for pid in order:
            if here is not None and here != pid:
                clock += ctx.travel.leg(here, pid)[0]
            earliest[pid] = clock
            p = ctx.places[pid]
            clock += min(p.visit[ctx.cfg.visit_key[ctx.pace]], p.visit['short'])
            here = pid
    slots = reachable if len(meal_ids) >= len(reachable) else sorted(reachable, key=lambda n: n == 'breakfast')
    for pid in meal_ids:
        p = ctx.places[pid]
        # a meal window the place can host: open then (an afternoon-only place never takes lunch) and at its pin
        # Prefer the principal meals; breakfast-only opening hours still take breakfast.
        preferred = ROLE_SLOTS.get(p.meal_kind, slots)
        fits = [n for n in preferred if n in reachable and n not in claimed.values() and _role_fits(p, n)
                and (n != 'breakfast' or not breakfast_role or earliest[pid] <= ctx.cfg.meal_windows[n][1])
                and meal_visit_fits(p, n, ctx, cache)]
        if fits:
            claimed[pid] = fits[0]
        # An unclaimed meal venue fails validation; it cannot become an ordinary visit silently.
    free = [n for n in names if n not in claimed.values()
            and (n in reachable or n != 'breakfast' and ctx.cfg.meal_windows[n][1] < ctx.day.start)]
    if cache is not None:
        put(cache.meals, key, (dict(claimed), tuple(free)), ctx.cfg.cache_entries)
    return claimed, free


def meal_names(ctx: DayCtx) -> list[str]:
    """The meals the day plans for: the configured ones, less those the user skips (or eats at the lodging)."""
    return [n for n in list(ctx.cfg.meal_windows)[: ctx.cfg.meals_per_day] if n not in ctx.meal_skip]


def day_meals(ctx: DayCtx) -> list[str]:
    """The meals the day can hold: of meal_names, those whose window the day reaches with room for the meal around the
    user's fixed-time blocks (meal_slot). One rule for the scheduler's meal slots and the day layout's reservations."""
    if not ctx.day.busy:
        return [n for n in meal_names(ctx) if ctx.cfg.meal_windows[n][1] >= ctx.day.start
                and max(ctx.day.start, ctx.cfg.meal_windows[n][0]) + meal_floor(n, ctx) <= ctx.day.end]
    return [n for n in meal_names(ctx) if ctx.cfg.meal_windows[n][1] >= ctx.day.start
            and meal_slot(n, ctx, max(ctx.day.start, ctx.cfg.meal_windows[n][0]))[1]]


def busy_place(where: str | None, ctx: DayCtx) -> str | None:
    """The node of a fixed-time block: the lodging when it is there or says no place (spec section 4), the place
    itself when the travel matrix knows it, else None: the person stays where they are (an online block, or a place
    the plan does not know, for which build warns event_location_unknown; nothing is geocoded)."""
    return ctx.home if where in (None, "lodging") else where if where in ctx.travel.index else None


def free_until(ctx: DayCtx, start: int, here: str | None = None) -> int:
    """When the time free from `start` runs out: the first fixed-time block not over yet (less the way to it from
    `here`), else the day's end."""
    cut = ctx.day.end
    if not ctx.day.busy:
        return cut
    for a, b, _, _, where in ctx.day.blocks:
        if b > start:
            at = busy_place(where, ctx)
            cut = min(cut, a - (ctx.travel.leg(here, at)[0] if here and at and here != at else 0))
    return cut


def meal_minutes(name: str, ctx: DayCtx) -> int:
    return ctx.cfg.meal_durations.get(name, ctx.cfg.meal_min) - (ctx.meal_cuts or {}).get(("meal_free", name), 0)


def meal_floor(name: str, ctx: DayCtx) -> int:
    """The shortest a meal block may be: realistic.meal_min, or the meal's own length when that is shorter."""
    return min(meal_minutes(name, ctx), ctx.cfg.realistic["meal_min"])


def meal_fit(name: str, ctx: DayCtx, start: int, back: int = 0, here: str | None = None) -> int:
    """The minutes a meal gets on this day when it starts at `start`: its full length, or what the day's end leaves
    when that is at least realistic.meal_min (a meal slot shrinks to fit the day's end, never below it); 0 = no meal.
    `back` is what must still fit after the meal (the way to the day's end node and its buffer): see end_back.
    A fixed-time block of the user ends the free time like the day's end does, with the way to it from `here`."""
    full = meal_minutes(name, ctx)
    room = min(ctx.day.end - back, free_until(ctx, start, here)) - start
    return full if room >= full else room if room >= meal_floor(name, ctx) else 0


def meal_slot(name: str, ctx: DayCtx, start: int, here: str | None = None, to_end: bool = False) -> tuple[int, int]:
    """Where a meal can go from `start` on, one rule for the scheduler and the validator: (start, minutes) at `start`
    when the room fits it (meal_fit); else right after the fixed-time block that cuts the room, eaten where the block
    is, while that is still inside the meal's window; (start, 0) when it fits nowhere. to_end: the way from where the
    meal is eaten to the day's end node, and its buffer, must still fit (end_back)."""
    last = ctx.cfg.meal_windows[name][1]
    s, at = start, here
    while s <= last:
        length = meal_fit(name, ctx, s, end_back(ctx, at) if to_end else 0, at)
        if length:
            return s, length
        block = min(((a, b, where) for a, b, _, _, where in ctx.day.blocks if b > s), default=None)
        if block is None:
            break
        s, at = block[1], busy_place(block[2], ctx) or at
    return start, 0


def buffer_after(p: Place, ctx: DayCtx, leg_min: int) -> int:
    """The buffer that follows a stop before a leg of leg_min minutes."""
    cfg = ctx.cfg
    buffer = cfg.buffer_min[ctx.pace]
    if leg_min > cfg.long_leg_min:
        buffer += cfg.buffer_extra_long
    if p.hours_status in ("UNCERTAIN", "OUTDATED"):
        buffer += cfg.buffer_extra_uncertain
    if ctx.wet is not None and ctx.wet >= cfg.rain_high:
        buffer += cfg.buffer_extra_rain
    if crowd_sensitive(p, ctx.cond, cfg):
        buffer += cfg.conditions["crowd_buffer_min"][ctx.cond.crowd]
    if ctx.cond and ctx.cond.closure_risk and p.kind == "meal":
        buffer += cfg.conditions["closure_buffer_min"]
    return buffer


def end_leg(ctx: DayCtx, loc: str | None) -> int:
    """Minutes of road from `loc` to the day's end node (0 when there is none or we are already there)."""
    end = ctx.day.end_node
    return 0 if end is None or loc is None or loc == end else ctx.travel.leg(loc, end)[0]


def end_back(ctx: DayCtx, loc: str | None) -> int:
    """What a meal eaten at `loc` still has to leave room for: the buffer after that stop and the road to the end node."""
    leg = end_leg(ctx, loc)
    return leg + (buffer_after(ctx.places[loc], ctx, leg) if leg and loc in ctx.places else 0)


def place_at(items, ctx: DayCtx, time: int) -> str | None:
    """Where the day stands at `time`: the last stop started before it (a leg still running stays at its origin),
    else the day's start node."""
    here = ctx.day.start_node
    for it in sorted(items, key=lambda i: (i.start, i.end)):
        if it.start >= time:
            break
        if it.kind == "visit":
            here = it.place_id
        elif it.kind == "travel" and it.end <= time:
            here = it.to_id
    return here


def meals_needed(items, ctx: DayCtx) -> list[str]:
    """The meals a finished day is missing and could have held: one rule for the scheduler and the validator.
    A meal is placed when the day has a meal block of that name, or a visit to a meal place inside its window (a visit
    takes the first window it falls in that no earlier block claimed). A meal that is not placed is needed iff it fits
    from the earliest time the plan lets the person start it: the later of the window opening and the moment they are
    free, i.e. the end of the unbroken run of visits, legs, meals and blocks in progress then (a run that crosses the
    whole window waives the meal: the scheduler eats at the first gap in a run, and the day layout reserves each meal's
    minutes so a day is not filled through it), with the way from where they are to the end node, and its buffer, still
    to leave room for; the room must reach realistic.meal_min (see meal_fit)."""
    cfg = ctx.cfg
    names = meal_names(ctx)
    ordered = sorted(items, key=lambda i: (i.start, i.end))
    placed = {i.name for i in ordered if i.kind == "meal_free" and i.name in names}
    for it in ordered:
        if it.kind == "visit" and takes_meal_slot(ctx.places[it.place_id]):
            slot = next((n for n in names if n not in placed and cfg.meal_windows[n][0] <= it.start <= cfg.meal_windows[n][1]), None)
            if slot:
                placed.add(slot)
    if ctx.compact_estimates:
        # Full frames reserve fixed meals before fitting visits and the return leg, rather than waiving a meal
        # because those activities consumed its window. Fragments retain their existing coverage rule below.
        return [name for name in day_meals(ctx) if name not in placed]
    out = []
    for name in names:
        a, b = cfg.meal_windows[name]
        if name in placed or b < ctx.day.start:
            continue
        at, here = max(a, ctx.day.start), ctx.day.start_node
        for it in ordered:
            if it.kind in ("visit", "travel", "meal_free", "busy") and it.start <= at < it.end:
                at = it.end
            if it.kind == "visit" and it.start < at:
                here = it.place_id
            elif it.kind == "travel" and it.end <= at:
                here = it.to_id
        if at <= b and meal_slot(name, ctx, at, here, True)[1]:
            out.append(name)
    return out


def _breaks(t: int, active: int, items: list, free: list, served: set, notes: list, ctx: DayCtx,
            ahead: int = 0, at: str | None = None, last: bool = False, defer_rest: bool = False, recover_fn=None) -> tuple[int, int, int]:
    """Put the meal blocks that are due at time t, and a rest when active minutes ran too long. `ahead` is the buffer
    still riding on the next leg: a meal whose window opens within it is due now and starts as soon as it may, and
    the minutes it waited for the window count as buffer already spent (a short wait, or free time around `at` when
    longer than wait_max, so no stretch of the day is left without an item). `last` = nothing is left but the way to the
    end node: a meal then has to leave room for that road (see end_back). Returns (t, active, buffer left)."""
    cfg = ctx.cfg
    for name in free:
        a, b = cfg.meal_windows[name]
        if name in served or t + ahead < a:
            continue
        start = max(t, a)
        slot, length = meal_slot(name, ctx, start, at, last)
        if slot > start:
            continue                # a fixed-time block takes the room now: the meal comes right after it
        if last and start <= b and not length and meal_slot(name, ctx, start, at)[1]:
            continue                # the way home takes the room this meal needs: left for the end node (or a later stop)
        served.add(name)
        if start <= b and length:
            if start > t:
                items.append(Item("free", t, start, note=at) if start - t > cfg.realistic["wait_max"]
                             else Item("wait", t, start, note="meal"))
            items.append(Item("meal_free", start, start + length, name=name, note="free"))
            ahead = max(0, ahead - (start - t))
            t, active = start + length, 0
        else:
            if recover_fn is not None:
                limit = min(b, free_until(ctx, start, at) - meal_floor(name, ctx) - (end_back(ctx, at) if last else 0))
                recover_fn(max(1, start - limit))
            notes.append(f"meal_missed:{name}")
    every, rest = ctx.rest or (cfg.max_consecutive_min[ctx.pace], cfg.rest_min[ctx.pace])
    if active >= every and not defer_rest:
        items.append(Item("rest", t, t + rest))
        t, active = t + rest, 0
    return t, active, ahead


def _starves(free: list, served: set, ctx: DayCtx, t: int, done: int, here: str | None, stop: str, block) -> bool:
    """A stop squeezed in before a fixed-time block (start, where) would take the only time a meal had before it: the
    meal fits from `t` where the person is, but once the stop is `done` it fits neither there nor where the block is
    (meal_slot, which also tries after the block), so the block and the meal come first and the stop after them."""
    start, where = block
    at = busy_place(where, ctx)
    road = ctx.travel.leg(stop, at)[0] if at and at != stop else 0
    back = done + road + (buffer_after(ctx.places[stop], ctx, road) if road else 0)
    for name in free:
        a, b = ctx.cfg.meal_windows[name]
        if name in served or a >= start or max(t, a) > b or not meal_slot(name, ctx, max(t, a), here)[1]:
            continue
        if (max(done, a) > b or not meal_slot(name, ctx, max(done, a), stop)[1]) and \
                (max(back, a) > b or not meal_slot(name, ctx, max(back, a), at or stop)[1]):
            return True
    return False


def _gaps(start: int, stop: int, meals: list[Item], at: str | None, plain: Item, wait_max: int) -> list[Item]:
    """The time from start to stop around the meal blocks: free time around `at`, or a short wait."""
    out, cursor = [], start
    for m in [*meals, Item("meal_free", stop, stop)]:
        if m.start > cursor:
            out.append(Item("free", cursor, m.start, note=at) if m.start - cursor > wait_max
                       else Item("wait", cursor, m.start, place_id=plain.place_id, note=plain.note))
        if m.start < stop:
            out.append(m)
        cursor = max(cursor, m.end)
    return out


def humanize(items: list[Item], ctx: DayCtx) -> list[Item]:
    """A wait longer than wait_max is not a plan. Between a leg and the next visit: rest at the lodging when the
    free time is long and the lodging is near; else stay free around the previous stop and leave later, so the leg
    ends when it is needed. Meal blocks keep their time; the time around them becomes free time."""
    r = ctx.cfg.realistic
    out: list[Item] = []
    k = 0
    while k < len(items):
        it = items[k]
        j = k + 1
        while it.kind == "travel" and j < len(items) and items[j].kind in ("wait", "meal_free"):
            j += 1
        run = items[k + 1:j]
        if it.kind != "travel" or not any(x.kind == "wait" and x.end - x.start > r["wait_max"] for x in run):
            out.append(it)
            k += 1
            continue
        leg_min = it.end - it.start
        target = run[-1].end if run[-1].kind == "wait" else run[-1].start       # where the leg has to end
        meals = [m for m in run if m.kind == "meal_free" and m.start < target]
        after = [x for x in run if x.start >= target]
        resume = max([it.start, *(m.end for m in meals)])                       # the last stretch before the leg
        home = ctx.home
        if home and it.from_id and it.from_id != home and target - resume - leg_min >= r["rest_home_min"]:
            to_home, from_home = ctx.travel.leg(it.from_id, home)[0], ctx.travel.leg(home, it.to_id)[0]
            if to_home <= r["rest_home_road_max"] and from_home <= r["rest_home_road_max"]:
                back = target - from_home
                out.extend(_gaps(it.start, resume, meals, it.from_id, run[-1], r["wait_max"]))
                out.append(Item("travel", resume, resume + to_home, from_id=it.from_id, to_id=home, mode=it.mode))
                out.append(Item("rest", resume + to_home, back, note="home"))
                out.append(Item("travel", back, target, from_id=home, to_id=it.to_id, mode=it.mode))
                out.extend(after)
                k = j
                continue
        leave = target - leg_min
        if leave < resume:                  # no room to move the leg: the leg stays, the long waits become free time
            out.append(it)
            out.extend(Item("free", x.start, x.end, note=it.to_id) if x.kind == "wait"
                       and x.end - x.start > r["wait_max"] else x for x in run)
        else:
            out.extend(_gaps(it.start, leave, meals, it.from_id, run[-1], r["wait_max"]))
            out.append(Item("travel", leave, target, from_id=it.from_id, to_id=it.to_id, mode=it.mode, note=it.note))
            out.extend(after)
        k = j
    return out


def simulate(order: list[str], ctx: DayCtx, shrink: bool = True, *, _cache: _SimulationCache | None = None) -> DayResult:
    """shrink=False keeps every visit at the pace's length: robustness asks whether the day survives a delay as
    planned, not whether it survives by cutting visits short."""
    if _cache is not None and _cache.ctx is not ctx:
        raise ValueError("simulation cache belongs to another context")
    shrink = shrink and ctx.allow_shrink
    key = (tuple(order), shrink)
    if _cache is not None and key in _cache.simulations:
        return _cache.simulations[key]
    changed = []
    initial_shrink = shrink and not ctx.compact_estimates
    preferred = _simulate(order, ctx, initial_shrink, True, _cache, changed=changed)
    if preferred.violations or any(n.startswith("meal_missed") for n in preferred.notes):
        # Only the first breakfast and a preferred-time choice differ between the two clocks.
        earliest = _simulate(order, ctx, initial_shrink, False, _cache) if changed else preferred
        best = earliest if earliest.key < preferred.key else preferred
        # An unallocated meal venue already failed the shortest-visit/road lower bound in _meal_slots.
        # Minute recovery cannot give that order a meal slot; a different order/day or soft pin must change.
        if best.violations and shrink and ctx.compact_estimates and not any(
                v.kind == "meal_window" for v in best.violations):
            cuts = {}
            while True:
                try:
                    compact = _simulate(order, ctx, shrink, False, _cache, compact=True, cuts=cuts)
                    break
                except _Reclock:
                    continue
                except _SlackDay:
                    compact = best
                    break
            # A visit held to its time of day shrinks only as far as pin_duration_floor lets it (the time of day
            # wins over pace); any other visit cut short while the day has idle time means a stop should move.
            shortened = any(i.kind == "visit" and i.end - i.start < visit_minutes(ctx.places[i.place_id], ctx.cfg, ctx.pace, ctx.prefs)
                            and not ctx.places[i.place_id].pins for i in compact.items)
            idle = any(i.kind in {"free", "wait"} and i.end - i.start >= ctx.cfg.realistic["fill_min_gap"]
                       for i in compact.items) or any(b.start - a.end >= ctx.cfg.realistic["fill_min_gap"]
                                                    for a, b in zip(compact.items, compact.items[1:]))
            if compact.key < best.key and not (shortened and idle):
                if cuts and not compact.violations and compact.end < ctx.day.end:
                    # A minute cut can also remove a pace rest. Give back that surplus instead of keeping an
                    # unnecessarily shortened visit; replay without recovery so a new deficit rejects the trial.
                    for cut_key in reversed(cuts):
                        low, high = 0, cuts[cut_key]
                        kept = compact
                        while low < high:
                            give = (low + high + 1) // 2
                            trial_cuts = {**cuts, cut_key: cuts[cut_key] - give}
                            trial = _simulate(order, ctx, shrink, False, _cache, compact=True,
                                              cuts=trial_cuts, recovery=False)
                            if not trial.violations and not any(n.startswith("meal_missed") for n in trial.notes):
                                low, kept = give, trial
                            else:
                                high = give - 1
                        cuts[cut_key] -= low
                        compact = kept
                best = compact
        result = best
    else:
        result = preferred
    return put(_cache.simulations, key, result, ctx.cfg.cache_entries) if _cache is not None else result


class _Reclock(Exception):
    """Earlier estimates changed at a tight point: replay this order with those minute cuts only."""


class _SlackDay(Exception):
    """A completed idle stretch cannot fund later cuts or disappear on a later replay."""


def _simulate(order: list[str], ctx: DayCtx, shrink: bool, prefer_time: bool,
              cache: _SimulationCache | None = None, *, compact: bool = False, changed: list | None = None,
              cuts: dict | None = None, recovery: bool = True) -> DayResult:
    cfg, day, travel = ctx.cfg, ctx.day, ctx.travel
    claimed, free = _meal_slots(order, ctx, cache)
    leg = cache.leg if cache else travel.leg
    score = cache.score if cache else lambda place, a, b: visit_score(place, a, b, ctx)
    t, here, active = day.start, day.start_node, 0
    items: list[Item] = []
    viol: list[Violation] = []
    notes: list[str] = []
    served: set = set()
    if order:
        notes.extend(f'meal_missed:{name}' for name in free if cfg.meal_windows[name][1] < day.start)
        served.update(name for name in free if cfg.meal_windows[name][1] < day.start)
    travel_min = wait_min = 0
    pending_buffer = 0              # the buffer after a stop rides on the next leg, never as a row of its own
    details = []
    time_penalty = 0.0

    cuts = cuts if cuts is not None else {}

    def short_minutes(pid):
        """The visit's floor: its short estimate (never above the visit itself) plus its queue."""
        if cache is not None:
            return cache.durations[pid][1]
        p = ctx.places[pid]
        floor = pin_duration_floor(p, ctx) if compact and p.pins else min(visit_minutes(p, cfg, ctx.pace, ctx.prefs),
                                                                          p.visit["short"])
        return floor + queue_minutes(p, floor, ctx.cond, cfg)

    def duration(pid):
        if cache is not None:
            full = cache.durations[pid][0]
        else:
            p = ctx.places[pid]
            full = visit_minutes(p, cfg, ctx.pace, ctx.prefs)
            full += queue_minutes(p, full, ctx.cond, cfg)
        return full - cuts.get(("visit", pid), 0)

    def recover(need):
        """Recover exactly a deficit from the preceding uninterrupted stretch, latest estimates first.
        Waiting, free time, home rests and fixed blocks absorb earlier savings: never reclaim across them.
        User durations and the short estimate (including its queue) are immutable floors.
        """
        if not compact or not recovery or need <= 0:
            return
        options = []
        cursor = items[-1].end if items else t
        for it in reversed(items):
            if it.end < cursor or it.kind in {"wait", "free", "busy"} or it.kind == "rest" and it.note:
                break
            cursor = it.start
            if it.kind == "visit":
                p = ctx.places[it.place_id]
                if p.visit.get("source") == "user":
                    continue
                floor = short_minutes(it.place_id)
                key = ("visit", it.place_id)
                full = duration(it.place_id) + cuts.get(key, 0)
            elif it.kind == "meal_free":
                floor, key = meal_floor(it.name, ctx), ("meal_free", it.name)
                full = meal_minutes(it.name, ctx) + cuts.get(key, 0)
            else:
                continue
            room = max(0, it.end - it.start - floor)
            if room:
                options.append((key, room, max(cuts.get(key, 0), full - (it.end - it.start))))
        need = min(need, sum(room for _, room, _ in options))
        if not need:
            return
        for key, room, already in options:
            take = min(need, room)
            cuts[key] = already + take
            need -= take
            if not need:
                gap = cfg.realistic["fill_min_gap"]
                shorter = any(it.kind == "visit" and min(it.end - it.start, duration(it.place_id))
                              < visit_minutes(ctx.places[it.place_id], cfg, ctx.pace, ctx.prefs) for it in items)
                if shorter and (any(it.kind in {"wait", "free"} and it.end - it.start >= gap for it in items)
                                or any(b.start - a.end >= gap for a, b in zip(items, items[1:]))):
                    visible = humanize(items, ctx)
                    spans = [(it.start, it.end) for it in visible if it.kind in {"wait", "free"}
                             and it.end - it.start >= gap]
                    spans += [(a.end, b.start) for a, b in zip(visible, visible[1:]) if b.start - a.end >= gap]
                    non_pin_cut = any(key[0] == "visit" and amount and not ctx.places[key[1]].pins
                                      for key, amount in cuts.items())
                    if non_pin_cut and any(not any(max(a, cfg.meal_windows[n][0]) <= min(
                                       b, cfg.meal_windows[n][1] + cfg.meal_durations.get(n, cfg.meal_min))
                                   for n in free) for a, b in spans):
                        # A later meal cut can move that meal into an earlier wait on replay. Prune only idle
                        # that no free meal can fill; meal-only cuts also remain eligible for recovery.
                        raise _SlackDay
                raise _Reclock

    def breaks(*args, **kwargs):
        return _breaks(*args, **kwargs, recover_fn=recover)

    if cuts:
        # Only meals in the tight stretch change; a later free meal keeps its preferred duration.
        ctx = replace(ctx, meal_cuts=cuts)

    def move(frm: str | None, to: str | None):
        nonlocal t, active, travel_min, pending_buffer
        extra, pending_buffer = pending_buffer, 0
        if frm is None or to is None or frm == to:
            t += extra
            return
        m, mode = leg(frm, to)
        items.append(Item("travel", t, t + m + extra, from_id=frm, to_id=to, mode=mode,
                          note=f"+{extra}" if extra else None))
        t, active, travel_min = t + m + extra, active + m, travel_min + m

    done_busy: set = set()
    blocks = day.blocks                 # the user's fixed times inside this day's window

    def busy_due(need: int, nxt: str | None = None):
        """Keep each fixed-time block of the user that would start before the next stop `nxt` is done and the way
        from it to the block is made: go to it (the lodging, for one there or with no place given), eat a meal that
        falls before it there, and resume from it."""
        nonlocal t, here, active, pending_buffer
        handled = False
        for k, (a, b, kind, label, where) in enumerate(blocks):
            at = busy_place(where, ctx)
            back = leg(nxt, at)[0] if nxt and at and nxt != at else 0
            if k in done_busy or t + need + back <= a or a >= day.end:
                continue
            done_busy.add(k)
            handled = True
            road = leg(here, at)[0] if at and here is not None and here != at else 0
            last = items[-1] if items else None
            if last and last.kind == "rest" and last.note is None and last.end > a - road:
                # the block itself is the break: a pace rest before it shrinks (or goes) so the block is reached in time
                items.pop()
                t = max(last.start, min(last.end, a - road))
                if t > last.start:
                    items.append(Item("rest", last.start, t))
            if road:
                pending_buffer = min(pending_buffer, max(0, a - t - road))   # slack never makes it late
                move(here, at)
                here = at
            active = 0                  # the block is a break from going around: no rest is squeezed in before it
            if t < a:
                t, active, pending_buffer = breaks(t, active, items, free, served, notes, ctx, a - t, here)
            if t < a:
                r = cfg.realistic
                gap = a - t
                items.append(Item("rest", t, a, note="home") if at and here == at and gap >= r["rest_home_min"]
                             else Item("free", t, a, note=here) if gap > r["wait_max"] else Item("wait", t, a, note="busy"))
            if t < b:                   # a block the look-ahead reached late keeps only what is left of it: the
                items.append(Item("busy", max(t, a), b, name=label, note=kind))     # validator flags the overlap
            t, active, pending_buffer = max(t, b), 0, 0
        return handled

    def reclaim(pid: str, at: int):
        """A meal place reached only at `at`, after its meal's window (a block came first): a later meal its role
        allows, still free, takes it, and the meal it gave up becomes a free block like any other."""
        p = ctx.places[pid]
        if pid not in claimed or at <= cfg.meal_windows[claimed[pid]][1]:
            return
        lo, hi = cache.pins[pid] if cache else pin_window(p, ctx)
        need = min(p.visit[cfg.visit_key[ctx.pace]], p.visit["short"])
        later = next((n for n in free if n not in served and _role_fits(p, n) and any(
            max(at, o, lo, cfg.meal_windows[n][0]) <= min(hi, cfg.meal_windows[n][1], c - need)
            for o, c in (cache.intervals[pid] if cache else intervals_for(p, ctx)))), None)
        if later:
            free[free.index(later)] = claimed[pid]
            claimed[pid] = later

    # Day one from the arrival point: drop the bags at the lodging first (spec section 4).
    if day.index == 0 and day.start_node == "@entry" and ctx.home and ctx.drop_bags and order:
        m, mode = leg("@entry", ctx.home)
        stop = cfg.realistic["drop_bags_min"]
        items.append(Item("travel", t, t + m, from_id="@entry", to_id=ctx.home, mode=mode))
        items.append(Item("rest", t + m, t + m + stop, note="drop_bags"))
        t, here, active = t + m + stop, ctx.home, 0

    for idx, pid in enumerate(order):
        p = ctx.places[pid]
        last_breakfast = idx == 0 and 'breakfast' in free and t + (
            leg(here, pid)[0] if here else 0) > cfg.meal_windows['breakfast'][1]
        due = [name for name in free if name != 'breakfast'] if idx == 0 and not prefer_time and not last_breakfast else free
        first_breakfast = (idx == 0 and prefer_time and not last_breakfast and 'breakfast' in free
                           and 'breakfast' not in served)
        if compact and here is not None:
            # Check the next physical deadline before a free meal can introduce a wait in this stretch.
            reach = t + pending_buffer + (leg(here, pid)[0] if here != pid else 0)
            short = short_minutes(pid)
            lo, hi = cache.pins[pid] if cache else pin_window(p, ctx)
            latest = max((min(hi, c - short, day.end - short)
                          for o, c in (cache.intervals[pid] if cache else intervals_for(p, ctx))
                          if max(o, lo) <= min(hi, c - short, day.end - short)), default=reach)
            recover(reach - latest)
        if compact and here is not None:
            reach = t + pending_buffer + (leg(here, pid)[0] if here != pid else 0)
            done = min((max(reach, o, (cache.pins[pid] if cache else pin_window(p, ctx))[0]) + duration(pid)
                        for o, c in (cache.intervals[pid] if cache else intervals_for(p, ctx))
                        if max(reach, o) + duration(pid) <= c), default=DAY_MINUTES)
            due = [n for n in due if not (t < cfg.meal_windows[n][0] <= t + pending_buffer
                                         and done <= cfg.meal_windows[n][1] and not takes_meal_slot(p))]
        rest_meal = None
        if compact and ctx.rest is None and active >= cfg.max_consecutive_min[ctx.pace] and not takes_meal_slot(p):
            road = leg(here, pid)[0] if here else 0
            reach = t + pending_buffer + road
            # A meal just after this short leg provides the pace rest at the next stop. Do not add a separate rest
            # that pushes both past the meal's room; an explicit user rest is never deferred.
            rest_meal = next((name for name in due if road <= cfg.realistic['wait_max'] and name not in served
                              and t + pending_buffer < cfg.meal_windows[name][0]
                              and max(reach, cfg.meal_windows[name][0]) - reach <= cfg.realistic['wait_max']
                              and max(reach, cfg.meal_windows[name][0]) <= cfg.meal_windows[name][1]
                              and meal_slot(name, ctx, max(reach, cfg.meal_windows[name][0]), pid)[1]
                              >= cfg.rest_min[ctx.pace]), None)
        t, active, pending_buffer = breaks(t, active, items, due, served, notes, ctx, pending_buffer, here,
                                          defer_rest=rest_meal is not None)
        if first_breakfast and 'breakfast' in served and changed is not None:
            changed.append(True)     # only an actual first breakfast can differ in the earliest clock
        if blocks:              # when the stop can really start: after the road, its opening and its time of day
            reach = t + (leg(here, pid)[0] if here else 0) + pending_buffer
            pin_lo = (cache.pins[pid] if cache else pin_window(p, ctx))[0]
            starts = [max(reach, o, pin_lo) for o, c in (cache.intervals[pid] if cache else intervals_for(p, ctx))
                      if max(reach, o, pin_lo) < c]
            stay = duration(pid)
            done = min(starts, default=reach) + stay
            nxt = min(((a, where) for k, (a, _, _, _, where) in enumerate(blocks) if k not in done_busy and a >= t),
                      default=None)
            starved = nxt is not None and done < nxt[0] and _starves(due, served, ctx, t, done, here, pid, nxt)
            if starved:
                done = nxt[0] + 1       # the stop would eat the meal before the block: the block (and the meal) first
            at = busy_place(nxt[1], ctx) if nxt is not None else None
            if nxt is not None and not starved:
                recover(done + (leg(pid, at)[0] if at and at != pid else 0) - nxt[0])
            if nxt is not None and done + (leg(pid, at)[0] if at and at != pid else 0) > nxt[0]:
                # the block comes first (busy_due below): the meal place may have to take a later meal
                reclaim(pid, next(b for k, (a, b, *_) in enumerate(blocks) if k not in done_busy and a == nxt[0]))
            if busy_due(done - t, pid):
                # a meal the block held back is due now, before the next stop takes its window
                t, active, pending_buffer = breaks(t, active, items, due, served, notes, ctx, pending_buffer, here)
        move(here, pid)
        if rest_meal is not None and rest_meal not in served:
            t, active, _ = breaks(t, active, items, free, served, notes, ctx,
                                   max(0, cfg.meal_windows[rest_meal][0] - t), pid)
        visit = duration(pid)
        lo, hi = cache.pins[pid] if cache else pin_window(p, ctx)
        open_ = cache.intervals[pid] if cache else intervals_for(p, ctx)
        reclaim(pid, t)
        if pid in claimed:
            a, b = cfg.meal_windows[claimed[pid]]
            lo, hi = max(lo, a), min(hi, b)
            served.add(claimed[pid])
        elif takes_meal_slot(p):
            viol.append(Violation('meal_window', day.index, pid, 0, False, 'no available meal window'))
        pin_lo = cache.pins[pid][0] if cache else pin_window(p, ctx)[0]
        start, why = None, "opening"
        short = min(visit, short_minutes(pid))
        shortest = min(visit, short) if shrink else visit
        for o, c in open_:
            s = max(t, o, lo)
            # The visit is an estimate range: when the pace's length does not fit the opening block or what is
            # left of the day, it shrinks toward the short estimate, never below it.
            room = min(c, day.end) - s
            if s <= hi and room >= shortest:
                start, visit = s, min(visit, room)
                why = "opening" if s == o and o > max(t, lo) else "meal" if pid in claimed and s == lo > pin_lo else "pin"
                break
        if start is None and open_:
            deficits = [max(t, o, lo) - min(hi, c - shortest, day.end - shortest)
                        for o, c in open_ if max(o, lo) <= min(hi, c - shortest, day.end - shortest)]
            if deficits:
                recover(max(0, min(deficits)))
        # Reserve an unclaimed meal before a visit can consume its whole window.
        if start is not None and not takes_meal_slot(p):
            for name in free:
                a, b = cfg.meal_windows[name]
                if name in served or start > b or start + visit <= b:
                    continue
                before = (b if ctx.compact_estimates else a) - start
                if shrink and before >= shortest:
                    visit = min(visit, before)
                elif start <= b:
                    meal_start = max(t, a)
                    length = meal_fit(name, ctx, meal_start)
                    if length:
                        if meal_start > t and here is not None:
                            items.append(Item('wait', t, meal_start, place_id=pid, note='meal'))
                            wait_min += meal_start - t
                        items.append(Item('meal_free', meal_start, meal_start + length, name=name, note='free'))
                        served.add(name)
                        t, active = meal_start + length, 0
                        start = None
                        for o, c in open_:
                            s = max(t, o, lo)
                            room = min(c, day.end) - s
                            if s <= hi and room >= shortest:
                                start, visit = s, min(visit, room)
                                why = 'opening'
                                break
                        if start is None:
                            break
        if start is not None and prefer_time:
            choices = [(start, visit, why)]
            earliest_choice = choices[0]
            for rule in (cache.rules[pid] if cache else windows_for(p, ctx)):
                for a, b in rule.windows:
                    for o, c in open_:
                        s = max(t, o, lo, a)
                        room = min(c, day.end) - s
                        if s <= hi and room >= shortest:
                            length = min(visit, room)
                            choices.append((s, length, "preferred_time"))
                            if shrink and not ctx.compact_estimates and shortest <= b - s < length:
                                choices.append((s, b - s, "preferred_time"))
            # a preferred time is soft: it never runs the stop into a fixed-time block the plan has not reached yet
            cut = min((a - (leg(pid, at)[0] if at and at != pid else 0)
                       for k, (a, _, _, _, where) in enumerate(blocks) if k not in done_busy and t <= a < day.end
                       for at in (busy_place(where, ctx),)), default=None)
            if cut is not None and any(x[0] + x[1] <= cut for x in choices):
                choices = [x for x in choices if x[0] + x[1] <= cut]
            start, visit, why = min(choices, key=lambda x: (
                x[0] + x[1] + score(p, x[0], x[0] + x[1])[0], x[0]))
            if changed is not None and (start, visit, why) != earliest_choice:
                changed.append(True)
        if start is None:
            viol.append(Violation("hours", day.index, pid, 0, False, "no feasible start"))
            start = t
        elif start > t:
            if here is None:
                for name in free:
                    a, b = cfg.meal_windows[name]
                    m = max(t, a)
                    length = meal_minutes(name, ctx)
                    if name not in served and m <= b and m + length <= start:
                        items.append(Item("meal_free", m, m + length, name=name, note="free"))
                        served.add(name)
                        active = 0
            if here is not None:
                w_at = t
                for name in free:       # a meal that falls inside a long wait is eaten there, not skipped
                    a, b = cfg.meal_windows[name]
                    m = max(w_at, a)
                    length = meal_minutes(name, ctx)
                    if name not in served and m <= b and m + length <= start:
                        if m > w_at:
                            items.append(Item("wait", w_at, m, place_id=pid, note=why))
                            wait_min += m - w_at
                        items.append(Item("meal_free", m, m + length, name=name, note="free"))
                        served.add(name)
                        w_at, active = m + length, 0
                if start > w_at:
                    items.append(Item("wait", w_at, start, place_id=pid, note=why))
                    wait_min += start - w_at
            t = start       # with no start point the day simply opens at the first stop: nothing is waited out
        items.append(Item("visit", start, start + visit, place_id=pid, name=p.name))
        penalty, detail = score(p, start, start + visit)
        time_penalty += penalty
        details.append(detail)
        t, active, here = start + visit, active + visit, pid
        nxt = order[idx + 1] if idx + 1 < len(order) else day.end_node
        if nxt is not None and nxt != pid:
            pending_buffer = buffer_after(p, ctx, leg(pid, nxt)[0])
    # A day with no stop still shows the user's blocks and the meals around them (a meeting day the layout left empty).
    if (order or blocks) and any(k not in done_busy and a < day.end for k, (a, *_) in enumerate(blocks)):
        t, active, pending_buffer = breaks(t, active, items, free, served, notes, ctx, pending_buffer, here)
        if busy_due(10 ** 6) and here == day.end_node:
            t, active, pending_buffer = breaks(t, active, items, free, served, notes, ctx, pending_buffer, here, True)
    if order and day.end_node not in (None, here):
        t, active, pending_buffer = breaks(t, active, items, free, served, notes, ctx, pending_buffer, here, True)
        move(here, day.end_node)
    if order or blocks:
        for name in free:
            if name in served:
                continue
            a, b = cfg.meal_windows[name]
            m = max(t, a)
            length = meal_fit(name, ctx, m)
            if m <= b and length:
                items.append(Item('meal_free', m, m + length, name=name, note='optional'))
                served.add(name)
            else:
                if name in day_meals(ctx):
                    recover(max(1, t - min(b, day.end - meal_floor(name, ctx))))
                if t > b:
                    notes.append(f'meal_missed:{name}')
    if t > day.end:
        recover(t - day.end)
        viol.append(Violation("day_window", day.index, None, t - day.end, False, "the day runs past its end"))
    if not order:
        notes = [n for n in notes if not n.startswith("meal_missed")]   # no stop: a meal that does not fit is no news
    items = humanize(items, ctx)
    if order and ctx.require_meals:         # judged on the finished timeline, the one the validator sees
        for name in meals_needed(items, ctx):
            viol.append(Violation('meal_missing', day.index, None, 0, False, f'missing {name}'))
    travel_min = sum(ctx.travel.leg(i.from_id, i.to_id)[0] for i in items if i.kind == "travel")
    wait_min = sum(i.end - i.start for i in items if i.kind == "wait")
    end = max((it.end for it in items), default=t)
    return DayResult(tuple(items), tuple(order), tuple(viol), travel_min, wait_min, end, tuple(notes), "single",
                     time_penalty=time_penalty, time_details=tuple(details))
