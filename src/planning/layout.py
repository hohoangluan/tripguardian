"""Places -> days (spec section 6). Each day is cut into stretches free of the user's fixed-time blocks; a stretch holds
the minutes left after its meals and rests. Hard places go first (a time of day, few open days, far from the lodging),
then every place takes the stretch and position that add the fewest minutes of road (plus how full the day gets, a day
out in another area, the day's rain or crowd for the objective), and single moves between days improve it. A place
left over may still get in when a day hands all it holds to the others, or two days trade. Whatever cannot fit is
returned, never dropped silently; a place the user must go to is put even where it does not fit (its check says so)."""

from dataclasses import dataclass, field, replace

from .conditions import crowd_sensitive, hazard, queue_minutes
from .roles import ROLE_SLOTS, takes_meal_slot
from .schedule import DayCtx, busy_place, day_meals, intervals_for, meal_slot, meal_visit_fits, pin_window
from .traits import exposure, visit_minutes

# A day pulled to dawn rests at the lodging at midday (spec section 6, "ngày bình minh").
DAWN_REST = (12 * 60, 14 * 60 + 30, "rest", "Nghỉ trưa bù dậy sớm", "lodging")
LUGGAGE_MOBILITY = {"motorbike", "walk"}      # the last day after check-out with the bags on: only places near the way
BALANCE_MIN = 60          # a full day weighs like an hour of extra road: near-equal roads spread over the days
AREA_MIN = 15             # a day with no place of the same area weighs like this much extra road (a far place sets a
                          # day's area; a day with no lodging to start from is not free to open)


def must_places(trip) -> set[str]:
    """The places the user must go to (role anchor / locked, a must anchor): never left over (spec section 7)."""
    tc = trip.decision["trip_context"]
    return {c["id"] for c in trip.decision["confirmed"] if c.get("role") in {"anchor", "locked"}} | \
        {a["place_id"] for a in tc.get("anchors") or [] if a.get("priority") == "must"}


def pull_early(cx: DayCtx, day_ids, by_place: dict, travel) -> tuple[DayCtx, str | None]:
    """A sunrise place pulls the day's start forward: (the day, the place that pulled it, or None). A start the user set
    (their day start, arrival, check-in) is never moved earlier; a default one is, on day one too. A pulled day also
    rests at the lodging at midday, unless the user already rests then. The layout, the scheduler and every later check
    of a laid-out day use this one rule, so a plan shown as valid passes the check at confirm."""
    if cx.day.start_by_user:
        return cx, None
    early = [(lo, i) for i in day_ids if i in by_place and 0 < (lo := pin_window(by_place[i], cx)[0]) < cx.day.start]
    if not early:
        return cx, None
    lo, pid = min(early)
    first = cx.day.start_node
    start = max(0, lo - (travel.leg(first, pid)[0] if first else 0))
    busy = cx.day.busy
    if not any(b[2] in {"rest", "nap"} for b in busy):
        busy = busy + (DAWN_REST,)
    return replace(cx, day=replace(cx.day, start=start, busy=busy)), pid


@dataclass
class _Stretch:
    """Time between two fixed points of the day: from `first` at `start` to `last` at `end`."""
    start: int
    end: int
    first: str | None
    last: str | None
    room: int = 0                                   # minutes for visits and the road between them
    stops: list = field(default_factory=list)

    def seq(self) -> list:
        return [self.first, *self.stops, self.last]


def _leg(travel, a, b) -> int:
    return travel.leg(a, b)[0] if a and b and a != b else 0


def _tour(travel, seq: list) -> int:
    return sum(_leg(travel, a, b) for a, b in zip(seq, seq[1:]))


def _insert_cost(travel, seq: list, pid: str, max_leg: int | None = None) -> tuple[int, int] | None:
    """(added minutes, index in seq) of the cheapest place for pid in seq = [first, *stops, last]; None when every
    place for it needs a leg longer than the user's max_leg_min."""
    best = None
    for k in range(1, len(seq)):
        a, b = seq[k - 1], seq[k]
        there, back = _leg(travel, a, pid), _leg(travel, pid, b)
        if max_leg and max(there, back) > max_leg:
            continue
        add = there + back - _leg(travel, a, b)
        if best is None or add < best[0]:
            best = (add, k)
    return best


def _stretches(cx: DayCtx) -> tuple[list[_Stretch], dict]:
    """The day's stretches with their room, and meal name -> index of the stretch its slot falls in. A block at a known
    place (the lodging, a known node) ends the stretch before it there and opens the next one there; a block with no
    place (online) leaves the person where they are, so its minutes come out of the stretch it falls in."""
    d, cfg = cx.day, cx.cfg
    if d.intensity == "free" or d.end <= d.start:
        return [], {}
    start, first = d.start, d.start_node
    if cx.drop_bags and cx.home and first not in (None, cx.home):       # day one stops at the lodging first
        start += _leg(cx.travel, first, cx.home) + cfg.realistic["drop_bags_min"]
        first = cx.home
    out, lost, s, node = [], [], start, first
    for a, b, _, _, where in sorted(d.blocks):
        at = busy_place(where, cx)
        if at is None:
            lost.append((a, b))
            continue
        if a > s:
            out.append(_Stretch(s, a, node, at))
        s, node = max(s, b), at
    if d.end > s:
        out.append(_Stretch(s, d.end, node, d.end_node))
    meals: dict = {}
    taken = [0] * len(out)
    for n in day_meals(cx):
        at, length = meal_slot(n, cx, max(d.start, cfg.meal_windows[n][0]))
        k = next((k for k, st in enumerate(out) if st.start <= at < st.end), None)
        if k is not None and length:
            meals[n] = k
            taken[k] += length
    every, rest = cx.rest or (cfg.max_consecutive_min[cx.pace], cfg.rest_min[cx.pace])
    light = cfg.realistic["light_factor"] if d.intensity == "light" else 1.0
    early = DAWN_REST in d.busy
    for k, st in enumerate(out):
        span = st.end - st.start - taken[k] - sum(max(0, min(b, st.end) - max(a, st.start)) for a, b in lost)
        span -= (max(0, span) // max(1, every)) * rest
        factor = light * (cfg.realistic["early_day_factor"] if early and st.start >= DAWN_REST[1] else 1.0)
        st.room = max(0, int(span * factor))
    return out, meals


def capacity(cx: DayCtx) -> int:
    """Minutes a day has for visits and the road between them: its window less the user's blocks, the meals, the rests
    (spec section 6); a light day holds light_factor of that, a free day nothing."""
    return sum(st.room for st in _stretches(cx)[0])


def _need(p, cx: DayCtx) -> int:
    return min(p.visit[cx.cfg.visit_key[cx.pace]], p.visit["short"])


def _hosts(p, cx: DayCtx, st: _Stretch, pinned: bool) -> bool:
    """The place can be visited inside the stretch: open then for its shortest visit (and at its time of day)."""
    need = _need(p, cx)
    lo, hi = pin_window(p, cx) if pinned else (0, 10 ** 6)
    return any(max(st.start, o, lo) <= min(hi, c - need, st.end - need) for o, c in intervals_for(p, cx))


def _risk(p, cx: DayCtx) -> float:
    """What the day's conditions cost this place, in the objective's weights: rain on a place open to the weather, a
    crowd day on a place that draws crowds (more for a user who avoids them). 0 with no forecast and no signal."""
    w, cfg = cx.cfg.weights, cx.cfg
    risk = w.get("exposed", 0) * (exposure(p) == "exposed") * (cx.wet or 0.0)
    if cx.cond is not None and cx.cond.crowd != "normal" and crowd_sensitive(p, cx.cond, cfg):
        risk += w.get("crowd", 0) * (2 if cx.cond.crowd == "peak" else 1) * (
            cfg.conditions["crowd_avoid_factor"] if cx.crowd_tol == "avoid" else 1.0)
    return risk


def _timed(p, cx: DayCtx) -> tuple[int, int] | None:
    """The place's time-of-day window that day when it has one."""
    if not p.pins:
        return None
    lo, hi = pin_window(p, cx)
    return None if (lo, hi) == (0, 1440) else (lo, hi)


class _Day:
    """One day being filled: its context (pulled to dawn once a sunrise place is on it), stretches, meal slots left."""

    def __init__(self, k: int, cx0: DayCtx, cx: DayCtx, layout: "_Layout"):
        self.k, self.cx0, self.cx, self.lay = k, cx0, cx, layout
        self.stretches, self.slots = _stretches(cx)
        self.cap = sum(st.room for st in self.stretches)
        self.loads: dict = {}            # pid -> minutes it takes besides the road
        self.where: dict = {}            # pid -> stretch index
        self.meal: dict = {}             # pid -> meal slot it takes
        self.order: list = []            # pids in the order they were placed

    def used(self, i: int | None = None) -> int:
        sts = self.stretches if i is None else [self.stretches[i]]
        travel = self.lay.travel
        return sum(_tour(travel, st.seq()) + sum(self.loads[p] for p in st.stops) for st in sts)

    def tour(self) -> int:
        return sum(_tour(self.lay.travel, st.seq()) for st in self.stretches)

    def _slots_for(self, p) -> list[str]:
        """Free meal slots in role preference order, open for the visit and its pin."""
        cx, cfg = self.cx, self.cx.cfg
        return [n for n in ROLE_SLOTS.get(p.meal_kind, tuple(cfg.meal_windows))
                if n in self.slots and meal_visit_fits(p, n, cx)]

    def _load(self, p, slot: str | None, shrink: bool = False) -> int:
        cx = self.cx
        visit = visit_minutes(p, cx.cfg, cx.pace, cx.prefs)
        if shrink and cx.allow_shrink:  # the clock shortens a visit toward its short estimate when a day is tight
            visit = min(visit, p.visit["short"])
        visit += queue_minutes(p, visit, cx.cond, cx.cfg)
        if slot:                        # the meal slot is already reserved: only what the visit takes beyond it
            visit = max(0, visit - meal_slot(slot, cx, max(cx.day.start, cx.cfg.meal_windows[slot][0]))[1])
        return visit + cx.cfg.buffer_min[cx.pace]

    def option(self, pid: str, force: int = 0, shrink: bool = False):
        """The best way to put pid on this day as it stands, or None: (key, stretch, index, slot, load). force, for a
        place the user must go to: 1 = even where the minutes or the user's longest leg run out, 2 = even on a day the
        hard rules refuse (the plan then fails its check and says why)."""
        p, lay = self.lay.places[pid], self.lay
        if force < 2 and not lay.allowed(p, self):
            return None
        slot = None
        if takes_meal_slot(p):
            slots = self._slots_for(p)
            if not slots:
                return None
            cands = [(self.slots[slot], slot) for slot in slots]
        else:
            cands = [(i, None) for i, st in enumerate(self.stretches) if _hosts(p, self.cx, st, False)] or \
                ([(i, None) for i in range(len(self.stretches))] if force == 2 else [])
        win = _timed(p, self.cx)
        clash = bool(win) and any(w and max(w[0], win[0]) <= min(w[1], win[1])
                                  for q in self.order if q != pid for w in (_timed(lay.places[q], self.cx),))
        away = (AREA_MIN if p.area and all(lay.places[q].area != p.area for q in self.order if q != pid) else 0) \
            + _risk(p, self.cx)
        best = None
        for i, slot in cands:
            if best is not None and best[3] != slot:
                break                      # keep the preferred feasible meal; try later slots when its stretch is full
            load = self._load(p, slot, shrink)
            st = self.stretches[i]
            got = _insert_cost(lay.travel, st.seq(), pid, None if force else lay.max_leg)
            if got is None:
                continue
            add, at = got
            if self.used(i) + load + add > st.room and not force:
                continue
            miss = bool(win) and not _hosts(p, self.cx, st, True)
            fill = (self.used() + load + add) / max(1, self.cap)
            key = (miss, clash, add + BALANCE_MIN * fill + away, add, self.k, i)
            if best is None or key < best[0]:
                best = (key, i, at, slot, load)
        return best

    def put(self, pid: str, opt) -> None:
        _, i, at, slot, load = opt
        self.stretches[i].stops.insert(at - 1, pid)
        self.loads[pid], self.where[pid] = load, i
        if slot:
            self.meal[pid] = slot
            self.slots.pop(slot)
        self.order.append(pid)

    def take(self, pid: str) -> None:
        self.stretches[self.where.pop(pid)].stops.remove(pid)
        self.loads.pop(pid)
        if pid in self.meal:
            slot = self.meal.pop(pid)
            self.slots[slot] = _stretches(self.cx)[1][slot]
        self.order.remove(pid)

    def ids(self) -> list[str]:
        return [p for st in self.stretches for p in st.stops]

    def copy(self) -> "_Day":
        out = _Day.__new__(_Day)
        out.__dict__.update(self.__dict__)
        out.stretches = [replace(st, stops=list(st.stops)) for st in self.stretches]
        out.slots, out.loads, out.where, out.meal = dict(self.slots), dict(self.loads), dict(self.where), dict(self.meal)
        out.order = list(self.order)
        return out


class _Layout:
    def __init__(self, trip, ctxs: list[DayCtx]):
        self.places, self.travel = trip.by_place, trip.travel
        self.home = next((cx.home for cx in ctxs if cx.home), None)
        self.days = [_Day(k, cx, cx, self) for k, cx in enumerate(ctxs)]
        self.luggage = trip.decision["trip_context"]["context"].get("mobility") in LUGGAGE_MOBILITY
        self.max_leg = (trip.decision["trip_context"].get("pace") or {}).get("max_leg_min")
        self.musts = must_places(trip)

    def allowed(self, p, day: _Day) -> bool:
        """Hard rules: not on a hazard day, open that weekday long enough, and, on a last day carried out with the bags
        by motorbike or on foot, near the lodging or the way out (spec section 4)."""
        cx = day.cx
        if hazard(p, cx.cond) and any(not hazard(p, d.cx.cond) for d in self.days):
            return False            # a hazard on every day is not solved by leaving it out: its check refuses the plan
        need = _need(p, cx)
        lo = pin_window(p, cx)[0]
        floor = lo if 0 < lo < cx.day.start and not cx.day.start_by_user else cx.day.start    # a dawn pull opens it
        if not any(max(floor, o) + need <= min(c, cx.day.end) for o, c in intervals_for(p, cx)):
            return False
        r = cx.cfg.realistic["luggage_radius_min"]
        if self.luggage and cx.day.end_node == "@exit" and cx.day.index == len(self.days) - 1 \
                and _leg(self.travel, p.id, "@exit") > r and _leg(self.travel, self.home, p.id) > r:
            return False
        return True

    def option(self, day: _Day, pid: str, shrink: bool = False):
        """pid on the day, pulling the day to dawn first when pid is a sunrise place (the day is laid out again)."""
        pulled, who = pull_early(day.cx0, [*day.order, pid], self.places, self.travel)
        if pulled.day == day.cx.day:
            opt = day.option(pid, shrink=shrink)
            return (opt[0], day, opt) if opt else None
        trial = _Day(day.k, day.cx0, pulled, self)
        for q in [*day.order, pid]:
            opt = trial.option(q) or (trial.option(q, shrink=True) if q == pid and shrink else None)
            if opt is None:
                return None
            trial.put(q, opt)
        key = trial.where[pid], trial.stretches[trial.where[pid]]
        miss = bool(_timed(self.places[pid], pulled)) and not _hosts(self.places[pid], pulled, key[1], True)
        add = trial.tour() - day.tour()
        return ((miss, False, add + BALANCE_MIN * trial.used() / max(1, trial.cap), add, day.k, key[0]), trial, None)

    def place(self, pid: str, skip: int | None = None) -> bool:
        best = None
        for day in self.days:
            if day.k == skip:
                continue
            got = self.option(day, pid)
            if got and (best is None or got[0] < best[0]):
                best = got
        if best is None:                # no day holds the pace's visit: one that holds it shortened, as the clock would
            for day in self.days:
                if day.k != skip and (got := self.option(day, pid, shrink=True)) and (best is None or got[0] < best[0]):
                    best = got
        for force in (1, 2):            # a must-go place is never left over: its check says what goes wrong instead
            if best is None and pid in self.musts and skip is None:
                forced = [(opt[0], day, opt) for day in self.days if (opt := day.option(pid, force))]
                best = min(forced, key=lambda x: x[0], default=None)
        if best is None:
            return False
        _, day, opt = best
        if opt is None:                          # a whole new layout of that day (pulled to dawn)
            self.days[day.k] = day
        else:
            day.put(pid, opt)
        return True

    def evict(self, left: list) -> list:
        """Make room for a place left over: a day hands all it holds to the other days, when they take every one of
        them and the place then fits. Returns what is still left over."""
        for pid in list(left):
            for k in sorted(range(len(self.days)), key=lambda j: (len(self.days[j].order), j)):
                day = self.days[k]                  # read after each restore: a failed try never leaks into the next
                if not day.order:
                    continue
                was = [d.copy() for d in self.days]
                moving = list(day.order)
                self.days[k] = _Day(k, day.cx0, day.cx0, self)
                if all(self.place(q, skip=k) for q in moving) and self.place(pid):
                    left.remove(pid)
                    break
                self.days = was
        return left

    def swap(self, left: list) -> list:
        """Two days trade all they hold when that lets a place left over in (a group of far places that took the longer
        day first, say). Returns what is still left over."""
        for a in range(len(self.days)):
            for b in range(a + 1, len(self.days)):
                if not left:
                    return left
                was = self.days[a], self.days[b]
                ta, tb = _refill(self, was[0], was[1].order), _refill(self, was[1], was[0].order)
                if ta is None or tb is None:
                    continue
                self.days[a], self.days[b] = ta, tb
                still = [pid for pid in left if not self.place(pid)]
                if len(still) < len(left):
                    left = still
                else:
                    self.days[a], self.days[b] = was     # nothing came in, so nothing else changed
        return left

    def improve(self, passes: int) -> None:
        """Move one place to another stretch (any day) while that costs less than where it is, by the measure the places
        were put by (road added, plus how full the day gets); ties keep the layout."""
        for _ in range(passes):
            moved = False
            for day in self.days:
                for pid in list(day.order):
                    p = self.places[pid]
                    if takes_meal_slot(p) or p.pins:
                        continue
                    before, used, i = day.tour(), day.used(), day.where[pid]
                    spot = (None, i, day.stretches[i].stops.index(pid) + 1, None, day.loads[pid])
                    day.take(pid)
                    here = before - day.tour() + BALANCE_MIN * used / max(1, day.cap) + _risk(p, day.cx) + (
                        AREA_MIN if p.area and all(self.places[q].area != p.area for q in day.order) else 0)
                    best = None
                    for other in self.days:
                        opt = other.option(pid)
                        if opt and opt[0][2] < here and (best is None or opt[0] < best[1][0]):
                            best = (other, opt)
                    if best is None or best[0] is day and best[1][1] == i:
                        day.put(pid, spot)              # nothing better: back where it was
                        continue
                    best[0].put(pid, best[1])
                    moved = True
            if not moved:
                break


def _refill(lay, day: _Day, order: list) -> _Day | None:
    """The day laid out again holding `order` (pulled to dawn when one of them is a sunrise place), or None."""
    cx, _ = pull_early(day.cx0, order, lay.places, lay.travel)
    trial = _Day(day.k, day.cx0, cx, lay)
    for pid in order:
        opt = trial.option(pid)
        if opt is None:
            return None
        trial.put(pid, opt)
    return trial


def _hardness(lay: _Layout, ids: list[str]):
    """Hard places first: a time of day, then not a meal stop, then few days open, then far out (from the lodging, or,
    with none known, from the other places)."""
    def far(pid):
        if lay.home:
            return _leg(lay.travel, lay.home, pid)
        others = [q for q in ids if q != pid]
        return sum(_leg(lay.travel, pid, q) for q in others) / len(others) if others else 0

    def key(pid):
        p = lay.places[pid]
        open_days = sum(lay.allowed(p, d) for d in lay.days)
        return (not p.pins, takes_meal_slot(p), open_days, -far(pid), pid)
    return key


def allowed(trip, ctxs: list[DayCtx]):
    """(day index, place id) -> whether the hard rules let the place on that day at all (open long enough, no hazard,
    near the way out on a last day with the bags): for a check outside the layout's own estimate."""
    lay = _Layout(trip, ctxs)
    return lambda k, pid: lay.allowed(lay.places[pid], lay.days[k])


def assign(trip, ctxs: list[DayCtx], ids: list[str]) -> tuple[list[list[str]], list[str]]:
    """(place ids of each day, the places no day has room for). Deterministic: the same input gives the same layout."""
    lay = _Layout(trip, ctxs)
    left = [pid for pid in sorted(ids, key=_hardness(lay, ids)) if not lay.place(pid)]
    lay.improve(trip.cfg.improve_passes)
    left = [pid for pid in left if not lay.place(pid)]          # a move may have made room
    left = lay.swap(lay.evict(left))
    return [day.ids() for day in lay.days], left
