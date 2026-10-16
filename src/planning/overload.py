"""One main plan; when the trip's days cannot hold every pick, three plans that each drop places by one criterion
the user understands (spec section 7): Giữ nơi hợp gu nhất, Ít đi lại, Tiết kiệm. A direction is a drop ORDER: drop the
next place until everything fits, then give back any dropped place that still fits. Must-go places never drop. Budget
never enters a place's score: prices only order the `cost` direction, and a place with no known price is never dropped
by it."""

from dataclasses import asdict, replace

from .backup import backups
from .build import Schedule, itinerary, schedule_trip, travel_load
from .composer import must_places, profile_metrics, selection_utilities
from .robustness import robustness
from .timefit import describe as time_description
from .traits import visit_minutes

DIRECTIONS = ("fit", "travel", "cost")
LABEL = {"main": "Lịch của bạn", "fit": "Giữ nơi hợp gu nhất", "travel": "Ít đi lại", "cost": "Tiết kiệm"}
GAIN = {"fit": "giữ những nơi khớp gu bạn nhất", "travel": "ít ngồi xe nhất", "cost": "rẻ nhất"}
ORDINAL = {2: "thứ hai", 3: "thứ ba", 4: "thứ tư"}
ALONE_MIN = 15              # spec section 7: "các nơi khác cách khách sạn < 15′", the dropped place off on its own
EXTEND_STEP = 15            # extend offers go up in quarter hours, to extend_max_min
OVERRUN = {"day_window", "departure"}   # a day past its end or its departure: only must-go places get laid out so
NEUTRAL_UTILITY = 1.0       # composer.selection_utilities' value for a place with no utility and no soft weights
UNAVAILABLE = {"protected": "Các nơi còn lại đều là nơi bạn chắc chắn đi, không bỏ được nơi nào.",
               "unpriced": "Các nơi còn lại chưa có giá, không xét để tiết kiệm.",
               "no_gain": "Bỏ thêm nơi theo hướng này cũng không làm lịch vừa."}


def _short(trip, sched: Schedule) -> int:
    """Minutes the trip is short by: the left-over places' shortest visits and how far must-go places overran a day."""
    return sum(trip.by_place[p].visit["short"] for p in sched.leftover) + \
        sum(v.minutes for v in sched.violations if v.kind in OVERRUN)


def _over(sched: Schedule) -> bool:
    """The days cannot hold every pick: a place is left over, or must-go places pushed a day past its end."""
    return bool(sched.leftover) or any(v.kind in OVERRUN for v in sched.violations)


def _gap(trip, sched: Schedule) -> tuple[int, bool]:
    """How far a schedule is from fitting, to compare two of them: fewer missing minutes first, then fitting at all
    (an overrun of 0 minutes is still an overrun). (0, False) = it fits."""
    return _short(trip, sched), _over(sched)


def _utility(values: dict, pid: str) -> float:
    return values.get(pid, NEUTRAL_UTILITY)


def _vnd(v: int) -> str:
    if v < 1000:
        return f"~{v}đ/người"
    return f"~{v // 1000}k/người" if v < 1_000_000 else f"~{v / 1_000_000:.1f}tr/người".replace(".", ",")


def _hm(minutes: int) -> str:
    return f"{minutes // 60}h{minutes % 60:02d}" if minutes >= 60 else f"{minutes}′"


class _Runs:
    """schedule_trip once per kept set within one plan_or_directions call: the directions often try the same sets."""

    def __init__(self, trip):
        self.trip, self.memo, self.calls = trip, {}, 0

    def __call__(self, kept) -> Schedule:
        key = frozenset(kept)
        if key not in self.memo:
            self.calls += 1
            self.memo[key] = schedule_trip(self.trip, kept=key)
        return self.memo[key]


def _saving(trip, sched: Schedule, pid: str, gone=frozenset()) -> int:
    """Minutes on the road saved by not going to pid, in the day order it has now (places in `gone` already left)."""
    leg = lambda a, b: trip.travel.leg(a, b)[0] if a and b else 0
    for cx, r in zip(sched.ctxs, sched.results):
        if pid in r.order:
            order = [p for p in r.order if p not in gone]
            k = order.index(pid)
            prev = order[k - 1] if k else cx.day.start_node
            nxt = order[k + 1] if k + 1 < len(order) else cx.day.end_node
            return max(0, leg(prev, pid) + leg(pid, nxt) - leg(prev, nxt))
    home = sched.ctxs[0].home if sched.ctxs else None
    return 2 * leg(home, pid)                     # not placed: the round trip from the lodging it would need


def _freed(trip, sched: Schedule, pid: str, gone) -> int:
    """Minutes dropping pid gives the other places (its visit and the road it saves); a left-over place frees none."""
    placed = any(pid in r.order for r in sched.results)
    if not placed:
        return 0
    visit = sum(i.end - i.start for r in sched.results for i in r.items if i.kind == "visit" and i.place_id == pid)
    return visit + _saving(trip, sched, pid, gone)


def _alone(trip, pid: str, kept) -> bool:
    """pid is off on its own: at least ALONE_MIN from the lodging while every other kept place is closer than that."""
    home = trip.ctxs[0].home if trip.ctxs else None
    others = [p for p in kept if p != pid]
    return bool(home and others) and trip.travel.leg(home, pid)[0] >= ALONE_MIN and \
        all(trip.travel.leg(home, p)[0] < ALONE_MIN for p in others)


def _next(trip, sched, candidates, direction, values, ranks, gone):
    """(place, its number on the criterion, the reason on the card) to drop next, or None when nothing can go."""
    if direction == "fit":
        pid = min(candidates, key=lambda p: (_utility(values, p), -_saving(trip, sched, p, gone), p))
        n = 1 + sum(_utility(values, q) < _utility(values, pid) for q in ranks)    # ties share a rank
        return pid, _utility(values, pid), "ít khớp gu nhất" if n == 1 else \
            f"khớp gu {ORDINAL.get(n, f'thứ {n}')} từ dưới lên"
    if direction == "travel":
        pid = max(candidates, key=lambda p: (_saving(trip, sched, p, gone), -_utility(values, p), p))
        s = _saving(trip, sched, pid, gone)
        reason = f"bớt {_hm(s)} đi xe" if s else "không bớt phút đi xe nào"
        if _alone(trip, pid, set(trip.by_place) - gone - {pid}):
            reason += f", các nơi khác cách chỗ ở < {ALONE_MIN}′"
        return pid, s, reason
    priced = [p for p in candidates if trip.by_place[p].cost_vnd is not None]
    if not priced:
        return None
    pid = max(priced, key=lambda p: (trip.by_place[p].cost_vnd, p))
    v = trip.by_place[pid].cost_vnd
    return pid, v, f"đắt nhất {_vnd(v)}" if v else "miễn phí"


def _direction(trip, run: _Runs, direction, protected, values):
    """(kept, dropped, schedule, why unavailable or None). A round drops a batch that frees about the missing minutes on
    the current layout (the criterion recomputed after each pick); if that does not bring the trip closer to fitting,
    it keeps dropping one more place at a time until it does. A round that cannot is taken back whole and dropping
    stops: a day with room never loses a place to an overrun dropping cannot fix (spec section 7). Then gives back,
    last dropped first, each place whose return leaves the trip no further from fitting, until a pass gives none
    back: a fitting trip stays fitting, one that still overruns keeps only the drops that helped."""
    kept = set(trip.by_place)
    sched = run(kept)
    ranks = sorted(set(trip.by_place) - protected)      # the places a fit reason ranks among
    dropped = []
    while _over(sched):
        gap = _gap(trip, sched)
        missing, gone, picks, trial = gap[0], set(), [], None
        while True:
            candidates = kept - protected - gone
            pick = _next(trip, sched, candidates, direction, values, ranks, gone) if candidates else None
            if pick is not None:
                pid, value, reason = pick
                picks.append({"place_id": pid, "name": trip.by_place[pid].name, "reason": reason, "value": value})
                missing -= trip.by_place[pid].visit["short"] if pid in sched.leftover else \
                    _freed(trip, sched, pid, gone)
                gone.add(pid)
                if missing > 0:
                    continue            # the batch: about the missing minutes, checked with one schedule_trip
            elif not gone:
                break                   # nothing this direction may drop
            trial = run(kept - gone)
            if _gap(trip, trial) < gap or pick is None:
                break                   # closer to fitting, or nothing more to try
        if trial is None or not _gap(trip, trial) < gap:
            break                       # nothing (more) to drop, or dropping stopped helping: the round is taken back
        kept -= gone
        dropped += picks
        sched = trial
    best = _gap(trip, sched)
    changed = True
    while changed:
        changed = False
        for d in list(reversed(dropped)):
            trial = run(kept | {d["place_id"]})
            if _gap(trip, trial) <= best:
                kept.add(d["place_id"])
                dropped.remove(d)
                sched, best, changed = trial, _gap(trip, trial), True
    if not _over(sched):
        return kept, dropped, sched, None
    left = kept - protected
    if not left:
        why = "protected"
    elif direction == "cost" and all(trip.by_place[p].cost_vnd is None for p in left):
        why = "unpriced"
    else:
        why = "no_gain"
    return kept, dropped, sched, why


def render_variant(trip, sched: Schedule, vid: str, dropped=(), available=True, why=None, day_parts=True) -> dict:
    """One plan card in the shape the engine reads (composer.render_profile's keys) plus the overload card fields.
    day_parts=False: robustness and backups are left None for a caller that has them per day already (the engine's
    cached day artifacts), so an edit does not work them out twice."""
    m = profile_metrics(trip, sched)
    kept = sorted({pid for r in sched.results for pid in r.order})
    days = [cx.day for cx in sched.ctxs]
    values = selection_utilities(trip)
    known = [trip.by_place[p].cost_vnd for p in kept if p in trip.by_place and trip.by_place[p].cost_vnd is not None]
    violations = [asdict(v) for v in sched.violations]
    confirmable = available and not violations
    return {"id": vid, "objective": vid, "preset": None, "label": LABEL[vid], "gain": GAIN.get(vid),
            "kept": kept, "dropped": list(dropped), "available": available, "left_over": list(sched.leftover),
            "unavailable_reason": None if available else UNAVAILABLE[why or "protected"],
            "compare": {"travel_min": m["travel_min"], "cost_known_vnd": sum(known),
                        "cost_unknown_n": len(kept) - len(known),
                        "fit": round(sum(_utility(values, p) for p in kept) / max(1e-9, sum(values.values())), 3)},
            "stars": [], "metrics": m, "violations": violations,
            "status": "available" if confirmable else "unavailable", "confirmable": confirmable,
            "itinerary": itinerary(days, sched.results), "travel_load": travel_load(days, sched.results),
            "time_suitability": time_description(sched.ctxs, sched.results), "recommendations": [],
            "robustness": robustness(sched.ctxs, sched.results, trip.travel.source) if day_parts else None,
            "backups": backups(sched.ctxs, sched.results, trip.decision, trip.by_id) if day_parts else None,
            "warnings": sched.warnings,
            "lodging": {"id": None, "name": None, "price_vnd": None}, "score": [m["travel_min"]],
            "_results": sched.results, "_ctxs": sched.ctxs, "_home": trip.days[0].start_node if trip.days else None}


def _extend(trip, run: _Runs, main: Schedule) -> dict | None:
    """The smallest earlier start / later end (quarter hours, at most extend_max_min a day) that holds every place.
    A start the user set (arrival, check-in), a fixed departure and a free day never move. A step whose added minutes
    cannot even cover the left-over visits is not tried (no schedule_trip call)."""
    last = len(trip.ctxs) - 1
    short = _short(trip, main)

    def movable(k, cx, side):
        day = cx.day
        if day.intensity == "free":
            return False
        if side == "start":
            return not day.start_by_user and not (k == 0 and day.start_node == "@entry")
        return day.depart_by is None and not (k == last and day.end_node == "@exit") and day.end < 24 * 60

    sides = {side: [movable(k, cx, side) for k, cx in enumerate(trip.ctxs)] for side in ("start", "end")}
    tried: dict = {}

    def fits(side, minutes):
        if (side, minutes) not in tried:
            ctxs = [cx if not ok else replace(cx, day=replace(cx.day, start=cx.day.start - minutes)) if side == "start"
                    else replace(cx, day=replace(cx.day, end=min(24 * 60, cx.day.end + minutes)))
                    for ok, cx in zip(sides[side], trip.ctxs)]
            run.calls += 1
            tried[side, minutes] = not _over(schedule_trip(replace(trip, ctxs=ctxs)))
        return tried[side, minutes]

    top = trip.cfg.realistic["extend_max_min"] // EXTEND_STEP * EXTEND_STEP
    # A side that cannot hold every place even moved by the most it may move is not tried step by step (a whole
    # schedule_trip a step): the steps below the most only matter on a side the most fits.
    open_sides = [side for side in ("start", "end") if top and top * sum(sides[side]) >= short and fits(side, top)]
    for minutes in range(EXTEND_STEP, top + 1, EXTEND_STEP):
        for side in open_sides:
            if minutes * sum(sides[side]) >= short and fits(side, minutes):
                return {"side": side, "per_day_min": minutes}
    return None


def plan_or_directions(trip, *, protected=()) -> dict:
    """The plan output for one trip: a fitting trip has one `main` plan and no overload; an overloaded one has up to
    three direction plans (two that keep the same places share one card, `merged`) and the overload card.
    protected: places the session also keeps whatever happens (locked days), on top of composer.must_places."""
    run = _Runs(trip)
    main = run(set(trip.by_place))
    if not _over(main):
        v = render_variant(trip, main, "main")
        return {"variants": [v], "overload": None, "ok": v["confirmable"], "warnings": [], "back_to_decision": None,
                "comparison": [], "leftover": (), "schedule_calls": run.calls}
    protected = (must_places(trip) | set(protected)) & set(trip.by_place)
    values = selection_utilities(trip)
    out, seen = [], {}
    for direction in DIRECTIONS:
        kept, dropped, sched, why = _direction(trip, run, direction, protected, values)
        key = frozenset(kept)
        if key in seen:
            seen[key].setdefault("merged", []).append(direction)
            seen[key]["label"] += " · " + LABEL[direction]
        else:
            seen[key] = render_variant(trip, sched, direction, dropped, not _over(sched), why)
            out.append(seen[key])
        if direction == "cost":     # spec section 7: "N nơi chưa có giá, không xét"
            seen[key]["unpriced_n"] = sum(p.cost_vnd is None for pid, p in trip.by_place.items()
                                          if pid not in protected)
    ranked = [v for v in out if v["available"]]
    for field, better in (("travel_min", min), ("cost_known_vnd", min), ("fit", max)):
        if len(ranked) > 1:
            best = better(v["compare"][field] for v in ranked)
            for v in ranked:
                if v["compare"][field] == best:
                    v["stars"].append(field)
    missing = sum(visit_minutes(trip.by_place[p], trip.cfg, trip.pace) for p in main.leftover) + \
        sum(v.minutes for v in main.violations if v.kind in OVERRUN)
    extend = _extend(trip, run, main)
    overload = {"missing_min": missing, "places": len(trip.by_place),
                "directions": [{k: x for k, x in v.items() if not k.startswith("_")} for v in out], "extend": extend}
    ok = any(v["confirmable"] for v in out)
    back = None if any(v["available"] for v in out) else \
        {"reason": "required_places_do_not_fit", "places": sorted(protected), "leftover": list(main.leftover)}
    return {"variants": out, "overload": overload, "ok": ok, "warnings": [], "comparison": [], "back_to_decision": back,
            "leftover": main.leftover, "schedule_calls": run.calls}
