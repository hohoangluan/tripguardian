"""The realism checks (spec §11 and round-3 pace regression). Each takes a Run and returns failure messages. The oracle here is independent of
the engine's own code: it reads the served records and the itinerary the user would see."""

from datetime import date

from realistic_cases import by_id
from plan_fixtures import CFG

R = CFG.realistic
SUNRISE, SUNSET = 6 * 60, 17 * 60 + 30          # plan_fixtures.fixed_sun
MAIN_MEALS = {"lunch": (11 * 60, 13 * 60 + 30), "dinner": (17 * 60 + 30, 20 * 60)}


def m(clock: str) -> int:
    h, mi = clock.split(":")
    return int(h) * 60 + int(mi)


def group(pid: str) -> str:
    return by_id()[pid]["identity"].get("category_group")


def present(pid: str, fid: str) -> bool:
    rec = by_id()[pid]
    for g in ("experience", "environment", "service", "effort", "suitability"):
        f = (rec.get(g) or {}).get(fid)
        if f and f.get("value") == "present":
            return True
    return False


def visits(run):
    for d in run.days:
        for i in d["items"]:
            if i["kind"] == "visit":
                yield d, i


def no_long_wait(run):
    return [f"day {d['day']} waits {m(i['end']) - m(i['start'])}′ at {i['start']}"
            for d in run.days for i in d["items"] if i["kind"] == "wait" and m(i["end"]) - m(i["start"]) > R["wait_max"]]


def _needed(run, d) -> list[str]:
    meals = run.case["frame"]["meals"]
    lo, hi = m(d["window"][0]), m(d["window"][1])
    return [n for n, (a, b) in MAIN_MEALS.items() if n not in meals["skip"] and lo <= b and max(lo, a) + 60 <= hi]


def meals(run):
    out = []
    for d in run.days:
        if not any(i["kind"] == "visit" for i in d["items"]):
            continue
        for name in _needed(run, d):
            a, b = MAIN_MEALS[name]
            covered = any(i["kind"] == "meal_free" and i.get("name") == name for i in d["items"]) or any(
                i["kind"] == "visit" and group(i["place_id"]) in {"restaurant", "market"} and a <= m(i["start"]) <= b
                for i in d["items"])
            if not covered:
                out.append(f"day {d['day']} has no {name}")
        for i in d["items"]:
            if i["kind"] == "visit" and group(i["place_id"]) in R["light_groups"] and \
                    MAIN_MEALS["dinner"][0] <= m(i["start"]) <= MAIN_MEALS["dinner"][1] and \
                    not any(j["kind"] == "meal_free" and j.get("name") == "dinner" or
                            j["kind"] == "visit" and group(j["place_id"]) == "restaurant" and
                            MAIN_MEALS["dinner"][0] <= m(j["start"]) <= MAIN_MEALS["dinner"][1] for j in d["items"]):
                out.append(f"day {d['day']}: {i['name']} stands in for dinner")
    return out


def every_pick_accounted(run):
    seen = {i["place_id"] for _, i in visits(run)}
    return [f"{n} is neither on the plan nor in the unplaced tray" for n, p in run.ids.items()
            if p not in seen and p not in run.unplaced]


def experience_window(run, d, place_id):
    """(lo, hi) start window of the visit's experience time of day (sunrise / sunset / evening), as the case's
    soft weights and the place's own hours make it applicable; None when the place has none that day."""
    from planning.roles import pin_order
    from planning.places import build_places, windows_on
    rec = by_id()[place_id]
    p = build_places({"confirmed": [{"id": place_id}], "trip_context": {}}, {place_id: rec}, CFG)[0][0]
    if not p.pins:
        return None
    wants = {w["feature"] for w in run.case.get("soft", []) if w.get("weight", 0) > 0}
    pins = pin_order(p.pins, wants)
    if "live_music" not in wants and p.activity not in {"nightlife", "drinking"} and group(p.id) not in {"bar", "market"}:
        pins = tuple(f for f in pins if f != "live_music")
    wd = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[date.fromisoformat(d["date"]).weekday()]
    opening = windows_on(p.hours, wd)
    windows = []
    for fid in pins:
        pin = CFG.pins[fid]
        if pin["anchor"] == "clock":
            lo, hi = pin["from"], pin["to"]
        else:
            base = SUNRISE if pin["anchor"] == "sunrise" else SUNSET
            lo, hi = base + pin["from_min"], base + pin["to_min"]
        if opening is None or any(max(lo, a) <= hi and max(lo, a) + p.visit["short"] <= b for a, b in opening):
            windows.append((lo, hi))
    if not windows:
        return None
    inside = [(lo, hi) for lo, hi in windows if max(lo, m(d["window"][0])) <= hi and
              max(lo, m(d["window"][0])) + p.visit["short"] <= m(d["window"][1])]
    return (inside or windows)[0]


def timed(run):
    """Spec §11 #4 / S8b: every experience time of day (sunrise / sunset / evening) is kept, or the day says it was
    given up (pin_dropped naming the place) for a physical limit the warning names."""
    out = []
    reasons = {"hours", "day_window", "departure", "meal_window", "meal_missing", "busy"}
    for d, i in visits(run):
        window = experience_window(run, d, i["place_id"])
        if window is None:
            continue
        lo, hi = window
        if lo <= m(i["start"]) <= hi:
            continue
        warnings = [w for w in run.view.get("warnings", []) if w.get("code") == "pin_dropped" and
                    w.get("day") == d["day"] and (w.get("place_id") == i["place_id"] or i["name"] in w.get("text", ""))]
        if not any(w.get("reason") in reasons and w.get("physical_conflicts") for w in warnings):
            out.append(f"day {d['day']}: {i['name']} at {i['start']} outside {lo // 60:02d}:{lo % 60:02d}-"
                       f"{hi // 60:02d}:{hi % 60:02d} without a physical pin_dropped reason")
    return out


def open_hours(run):
    from planning.places import parse_hours, windows_on
    out = []
    for d, i in visits(run):
        h = (by_id()[i["place_id"]]["operation"].get("hours") or {}).get("value")
        if not h or not d.get("date"):
            continue
        wd = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[date.fromisoformat(d["date"]).weekday()]
        spans = windows_on(parse_hours(h), wd) or []
        if not any(o <= m(i["start"]) and m(i["end"]) <= c for o, c in spans):
            out.append(f"{i['name']} at {i['start']}-{i['end']} outside its hours on {wd}")
    return out


def frame_kept(run):
    out = []
    days = run.case["frame"]["days"]
    for d, fd in zip(run.days, days):
        lo, hi = m(fd["start"]), m(fd["end"])
        dawn = any(present(i["place_id"], "cloud_hunting") for i in d["items"] if i["kind"] == "visit")
        for i in d["items"]:
            if m(i["end"]) > hi or (m(i["start"]) < lo and not dawn):
                out.append(f"day {d['day']}: {i['kind']} {i['start']}-{i['end']} outside {fd['start']}-{fd['end']}")
            for b in fd["busy"]:
                if i["kind"] in {"visit", "travel"} and m(i["start"]) < m(b["end"]) and m(b["start"]) < m(i["end"]):
                    out.append(f"day {d['day']}: {i['kind']} {i['start']} overlaps {b['labels'][0]}")
    leave = run.case["frame"].get("leave")
    if leave and run.days:
        last = run.days[-1]["items"]
        limit = m(leave["at"][11:]) - R["leave_buffer_min"]
        if last and m(last[-1]["end"]) > limit:
            out.append(f"last day ends {last[-1]['end']}, needs to be at the {leave['how']} by {limit // 60:02d}:{limit % 60:02d}")
    return out


def kids(run):
    if "kids" not in run.case["companions"]:
        return []
    out = []
    for d in run.days:
        stops = [i for i in d["items"] if i["kind"] == "visit"]
        if len(stops) >= 3 and not any(i["kind"] in {"rest", "busy"} for i in d["items"]):
            out.append(f"day {d['day']}: {len(stops)} stops with kids and no rest")
        for i in d["items"]:
            if (i["kind"] == "meal_free" and i.get("name") == "dinner" or i["kind"] == "visit" and
                    group(i["place_id"]) == "restaurant" and m(i["start"]) >= 17 * 60) and m(i["start"]) > 19 * 60:
                out.append(f"day {d['day']}: dinner at {i['start']} with kids")
    return out


def _ghost_covers(run, day: int, start: int, end: int) -> bool:
    """Spec §6: a free gap >= fill_min_gap that is not a rest at the lodging gets a faded suggestion; a gap the view's
    ghosts cover (same day, overlapping time, at least one real place offered) is offered, not idle."""
    return any(g["day"] == day - 1 and g["items"] and g["start"] < end and start < g["end"] for g in run.ghosts)


def no_idle_with_leftover(run):
    if not run.unplaced:
        return []
    out = []
    for d in run.days:
        items = d["items"]
        for a, b in zip(items, items[1:]):
            gap = m(b["start"]) - m(a["end"])
            if gap >= R["fill_min_gap"] and not _ghost_covers(run, d["day"], m(a["end"]), m(b["start"])):
                out.append(f"day {d['day']}: {gap}′ empty at {a['end']} while places are unplaced")
        for i in items:
            if (i["kind"] in {"wait", "free"} and m(i["end"]) - m(i["start"]) >= R["fill_min_gap"]
                    and not _ghost_covers(run, d["day"], m(i["start"]), m(i["end"]))):
                out.append(f"day {d['day']}: {i['kind']} {i['start']}-{i['end']} while places are unplaced")
    return out


def forced_by_time_of_day(run, d, item):
    """Controller ruling (round 4): the time of day wins over pace. A visit shorter than pace is not idle-funded
    when it starts at the opening of its experience window and nothing but meals, rests and the road follows it:
    no other stop took its minutes; the day's end did."""
    window = experience_window(run, d, item["place_id"])
    if window is None or not window[0] <= m(item["start"]) <= window[1]:
        return False
    if m(item["start"]) > max(window[0], m(d["window"][0])):
        return False
    after = [i for i in d["items"] if m(i["start"]) >= m(item["end"])]
    return not any(i["kind"] == "visit" for i in after)


def pace_kept(run):
    """Spec §6: pace estimates survive on days with a fill_min_gap free/wait/gap; user durations win.

    Category defaults use the configured activity range and breakfast-slot estimate (§5), just as other
    estimates do. This oracle reads records/config/frame, never the scheduler's chosen durations.
    """
    out = []
    for d in run.days:
        items = d["items"]
        slack = any(i["kind"] in {"free", "wait"} and m(i["end"]) - m(i["start"]) >= R["fill_min_gap"]
                    for i in items) or any(m(b["start"]) - m(a["end"]) >= R["fill_min_gap"]
                                          for a, b in zip(items, items[1:]))
        if not slack:
            continue
        for i in items:
            if i["kind"] != "visit":
                continue
            rec = by_id()[i["place_id"]]
            group_ = rec["identity"].get("category_group")
            user = ((run.view.get("state") or {}).get("visit_duration_override") or {}).get(i["place_id"]) or (
                run.case["frame"].get("visit") or {}).get(group_)
            if user:
                actual = m(i["end"]) - m(i["start"])
                if actual < user:
                    out.append(f"day {d['day']}: {i['name']} {actual}′ < user duration {user}′")
                continue
            from planning.places import build_places
            from planning.traits import visit_minutes
            from planning.build import breakfast_estimate
            place = breakfast_estimate(build_places({"confirmed": [{"id": i["place_id"]}], "trip_context": {}},
                                                    {i["place_id"]: rec}, CFG)[0][0], CFG)
            weights = run.case.get("soft", [])
            from planning.traits import preference
            expected = visit_minutes(place, CFG, run.case["pace"], {place.id: preference(place, weights)})
            actual = m(i["end"]) - m(i["start"])
            if expected is not None and actual < expected and forced_by_time_of_day(run, d, i):
                continue
            if expected is not None and actual < expected:
                out.append(f"day {d['day']}: {i['name']} {actual}′ < pace {expected}′ with idle >= {R['fill_min_gap']}′")
    return out


def travel_vs_nn(run):
    """Spec §11 check 9, controller round-3 ruling: compare the same stops under the same time constraints.
    Keep a sunrise/dawn-pinned first stop first and an evening/sunset-pinned last stop last, when the item's
    start actually lies in that pin's window. NN orders only the middle; legs and the 1.15 * NN + 5 margin stay.
    """
    from planning.travel import km
    def leg(a, b):
        return max(1, round(km(a, b) * 1.4 / 25 * 60))
    out = []
    for d in run.days:
        stops = [i["place_id"] for i in d["items"] if i["kind"] == "visit"]
        pts = {p: (by_id()[p]["identity"]["lat"], by_id()[p]["identity"]["lng"]) for p in stops}
        def tour(order):
            seq = [run.home, *(pts[p] for p in order), run.home]
            return sum(leg(a, b) for a, b in zip(seq, seq[1:]))
        day_visits = [i for i in d["items"] if i["kind"] == "visit"]

        def pinned(item, anchors):
            for fid, pin in CFG.pins.items():
                if pin["anchor"] not in anchors or not present(item["place_id"], fid):
                    continue
                if pin["anchor"] == "clock":
                    if pin["from"] < 17 * 60:
                        continue
                    lo, hi = pin["from"], pin["to"]
                else:
                    base = SUNRISE if pin["anchor"] == "sunrise" else SUNSET
                    lo, hi = base + pin["from_min"], base + pin["to_min"]
                if lo <= m(item["start"]) <= hi:
                    return True
            return False

        first = stops[:1] if stops and pinned(day_visits[0], {"sunrise"}) else []
        last = stops[-1:] if stops and pinned(day_visits[-1], {"sunset", "clock"}) else []
        left, nn = set(stops) - set(first) - set(last), list(first)
        here = pts[first[0]] if first else run.home
        while left:
            nxt = min(sorted(left), key=lambda p: leg(here, pts[p]))
            nn.append(nxt)
            left.remove(nxt)
            here = pts[nxt]
        nn.extend(p for p in last if p not in nn)
        if stops and tour(stops) > tour(nn) * 1.15 + 5:
            out.append(f"day {d['day']}: {tour(stops)}′ on the road, nearest-neighbour does {tour(nn)}′")
    return out


def overload_explained(run):
    from dataclasses import replace
    from planning.build import prepare, schedule_trip
    from planning.lodging import with_booked_base
    from realistic_cases import decision, records
    from plan_fixtures import FakeLive, fake_matrix, fixed_sun, no_geocode

    # Case expectations are independent ground truth; the scheduler only verifies offered extensions below.
    trip = prepare(with_booked_base(decision(run.case)), records(), CFG, FakeLive(), no_geocode, fake_matrix, fixed_sun)
    overrun = {"day_window", "departure"}
    fits = lambda sched: not sched.leftover and not any(v.kind in overrun for v in sched.violations)
    ov = run.view.get("overload")
    if not run.case["expect"].get("overload"):
        return [] if not ov else ["overload shown for a case expected to fit"]
    if not ov:
        return ["no overload shown for a case expected to overload"]
    out = []
    dirs = ov.get("directions") or []
    if not {x["id"] for x in dirs} <= {"fit", "travel", "cost"} or not dirs:
        out.append(f"directions are {[x.get('id') for x in dirs]}")
    if ov.get("missing_min", 0) <= 0:
        out.append("overload does not name the missing minutes")
    for x in dirs:
        for dropped in x.get("dropped") or []:
            reason = dropped.get("reason", "")
            zero = dropped.get("value") == 0 and reason in {"miễn phí", "không bớt phút đi xe nào"}
            if not any(ch.isdigit() for ch in reason) and x["id"] != "fit" and not zero:
                out.append(f"{x['id']}: reason without a number: {reason}")
        if any(p in {d["place_id"] for d in x.get("dropped") or []} for p in (run.ids[n] for n in run.case["must"])):
            out.append(f"{x['id']} drops a must-go place")

    def wider(side, minutes):
        ctxs = []
        for k, cx in enumerate(trip.ctxs):
            day = cx.day
            fixed = day.intensity == "free" or (
                day.start_by_user or k == 0 and day.start_node == "@entry" if side == "start" else
                day.depart_by is not None or k == len(trip.ctxs) - 1 and day.end_node == "@exit")
            if not fixed:
                day = replace(day, start=day.start - minutes) if side == "start" else replace(
                    day, end=min(24 * 60, day.end + minutes))
            ctxs.append(replace(cx, day=day))
        return schedule_trip(replace(trip, ctxs=ctxs))

    ext = ov.get("extend")
    if run.case["expect"].get("extend") and not ext:
        out.append("the case requires an extension but none is offered")
    if ext:
        if ext["side"] not in {"start", "end"} or not 0 < ext["per_day_min"] <= R["extend_max_min"]:
            out.append(f"invalid extension: {ext}")
        elif not fits(wider(ext["side"], ext["per_day_min"])):
            out.append("the offered extension does not hold the full selection")
    else:
        # An extension is required only when <=60 minutes really keeps every pick, with physical edges preserved.
        if any(fits(wider(side, minutes)) for minutes in range(15, R["extend_max_min"] + 1, 15)
               for side in ("start", "end")):
            out.append("the full selection fits within an hour a day but no extension is offered")
    return out


def user_said_kept(run):
    out = []
    for d, fd in zip(run.days, run.case["frame"]["days"]):
        dawn = any(present(i["place_id"], "cloud_hunting") for i in d["items"] if i["kind"] == "visit")
        if d["window"][1] != fd["end"] or (d["window"][0] != fd["start"] and not dawn):
            out.append(f"day {d['day']}: window {d['window']} but the user's day is {fd['start']}-{fd['end']}")
    return out


def reorder_kept(run):
    out = []
    for e in run.case["edits"]:
        if e["type"] != "reorder":
            continue
        want = [run.ids[n] for n in e["order"]]
        got = [i["place_id"] for i in run.days[e["day"]]["items"] if i["kind"] == "visit" and i["place_id"] in want]
        if got != want:
            out.append(f"day {e['day']}: user order {e['order']} became {got}")
    return out


CHECKS = {f.__name__: f for f in (no_long_wait, meals, every_pick_accounted, timed, open_hours, frame_kept, kids,
                                  no_idle_with_leftover, pace_kept, travel_vs_nn, overload_explained, user_said_kept, reorder_kept)}
