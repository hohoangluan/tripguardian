from dataclasses import replace

from plan_fixtures import CENTRE, SOUTH, prepared, decision, spot, rec

from planning.build import schedule_trip
from planning.layout import assign, capacity


def trip_of(recs, **kw):
    d = decision([r["id"] for r in recs], base={"place_id": None, "text": "home", "lat": CENTRE[0], "lng": CENTRE[1]},
                 **kw)
    return prepared(d, recs)


def test_near_places_share_a_day_and_far_ones_get_their_own():
    recs = [spot("c1", CENTRE, 0), spot("c2", CENTRE, 1), spot("s1", SOUTH, 0), spot("s2", SOUTH, 1)]
    trip = trip_of(recs, days=2)
    per_day, left = assign(trip, trip.ctxs, sorted(trip.by_place))
    assert not left
    assert {frozenset(d) for d in per_day} == {frozenset({"c1", "c2"}), frozenset({"s1", "s2"})}


def test_more_than_fits_leaves_the_rest_over_and_no_day_is_empty():
    recs = [spot(f"c{i}", CENTRE, i, visit=(120, 180, 240)) for i in range(12)]
    trip = trip_of(recs, days=2)
    per_day, left = assign(trip, trip.ctxs, sorted(trip.by_place))
    assert left and all(per_day)


def test_a_free_day_takes_no_place():
    recs = [spot("c1", CENTRE, 0), spot("c2", CENTRE, 1)]
    trip = trip_of(recs, days=2)
    ctxs = [trip.ctxs[0], replace(trip.ctxs[1], day=replace(trip.ctxs[1].day, intensity="free"))]
    per_day, _ = assign(trip, ctxs, sorted(trip.by_place))
    assert per_day[1] == [] and capacity(ctxs[1]) == 0


def test_a_place_closed_that_weekday_goes_to_another_day():
    closed_sat = {d: [["08:00", "21:00"]] for d in ("mon", "tue", "wed", "thu", "fri", "sun")}
    closed_sat["sat"] = []
    recs = [spot("c1", CENTRE, 0, hours=closed_sat), spot("c2", CENTRE, 1)]
    trip = trip_of(recs, days=2)                     # 2026-12-12 is a Saturday
    per_day, _ = assign(trip, trip.ctxs, sorted(trip.by_place))
    assert "c1" in per_day[1]


def test_schedule_trip_reports_leftover_instead_of_dropping_silently():
    recs = [spot(f"c{i}", CENTRE, i, visit=(120, 180, 240)) for i in range(12)]
    s = schedule_trip(trip_of(recs, days=2))
    placed = {pid for r in s.results for pid in r.order}
    assert s.leftover and placed | set(s.leftover) == {f"c{i}" for i in range(12)}


def test_last_day_by_motorbike_keeps_places_near_the_way_out():
    far = (11.80, 108.45)                         # ~15 km south: ~50 rough minutes
    recs = [spot("c1", CENTRE, 0), rec("f1", *far)]
    d = decision(["c1", "f1"], days=1, mobility="motorbike",
                 base={"place_id": None, "text": "home", "lat": CENTRE[0], "lng": CENTRE[1]},
                 exit={"text": "bến xe", "lat": CENTRE[0], "lng": CENTRE[1]})
    d["trip_context"]["context"]["frame"] = {
        "days": [{"date": "2026-12-12", "start": "08:00", "end": "21:00", "busy": [], "intensity": "normal"}],
        "arrive": None, "leave": {"at": "2026-12-12T20:00", "how": "bus"}, "meals": {}}
    trip = prepared(d, recs)
    per_day, left = assign(trip, trip.ctxs, ["c1", "f1"])
    assert per_day[0] == ["c1"] and left == ["f1"]


def test_a_dawn_day_gets_a_midday_rest_at_the_lodging():
    recs = [spot("c1", CENTRE, 0, hours=None, features={"cloud_hunting": "present"}), spot("c2", CENTRE, 1)]
    s = schedule_trip(trip_of(recs, days=2))
    day = next(k for k, r in enumerate(s.results) if "c1" in r.order)
    assert s.ctxs[day].day.start < 8 * 60
    assert any(b[2] == "rest" and b[0] >= 11 * 60 for b in s.ctxs[day].day.busy)


# ---- beyond the brief: the rulings and known issues this task closes ----

def framed(recs, days, *, busy=None, ends=None, intensity=None):
    """A trip with a CompiledFrame: every day 08:00-21:00 unless `ends` says otherwise, busy = {day: [blocks]}."""
    d = decision([r["id"] for r in recs], days=len(days),
                 base={"place_id": None, "text": "home", "lat": CENTRE[0], "lng": CENTRE[1]})
    d["trip_context"]["context"]["frame"] = {
        "days": [{"date": date, "start": "08:00", "end": (ends or {}).get(i, "21:00"),
                  "busy": [{"start": a, "end": b, "kinds": [k], "labels": [k], "where": w}
                           for a, b, k, w in (busy or {}).get(i, [])],
                  "intensity": (intensity or {}).get(i, "normal")} for i, date in enumerate(days)],
        "arrive": None, "leave": None, "meals": {}}
    return prepared(d, recs)


def test_capacity_counts_the_users_blocks_the_meals_and_a_light_day():
    recs = [spot("c1", CENTRE, 0)]
    trip = framed(recs, ["2026-12-12", "2026-12-13", "2026-12-14"],
                  busy={1: [("15:00", "17:00", "work", "lodging")]}, intensity={2: "light"})
    full, meeting, light = (capacity(cx) for cx in trip.ctxs)
    assert 0 < meeting <= full - 100             # the meeting's two hours are not free (it also stands for a rest)
    assert full < 13 * 60 - 90 - 90               # lunch and dinner are reserved
    assert light <= full * trip.cfg.realistic["light_factor"] + 1


def test_two_dawn_places_take_two_days():
    recs = [spot("h1", CENTRE, 0, hours=None, features={"cloud_hunting": "present"}),
            spot("h2", CENTRE, 1, hours=None, features={"cloud_hunting": "present"})]
    trip = trip_of(recs, days=2)
    per_day, left = assign(trip, trip.ctxs, sorted(trip.by_place))
    assert not left and sorted(map(len, per_day)) == [1, 1]


def test_a_full_day_at_a_far_lodging_moves_stops_to_a_free_day_rather_than_past_its_end():
    # Every day 08:00-21:00 with a 12:30-14:00 nap at the lodging: the plan never runs past a day's end.
    recs = [spot(f"c{i}", CENTRE, i, visit=(90, 120, 150)) for i in range(6)]
    trip = framed(recs, ["2026-12-12", "2026-12-13", "2026-12-14"],
                  busy={k: [("12:30", "14:00", "nap", "lodging")] for k in range(3)}, ends={2: "12:00"})
    s = schedule_trip(trip)
    for cx, r in zip(s.ctxs, s.results):
        assert all(it.end <= cx.day.end for it in r.items), cx.day.index
    assert {p for r in s.results for p in r.order} | set(s.leftover) == {f"c{i}" for i in range(6)}
    assert not [v for v in s.violations if v.kind in {"day_window", "busy", "hours"}]


def test_a_day_with_no_room_still_shows_its_blocks_and_meals():
    recs = [spot("c1", CENTRE, 0), spot("c2", CENTRE, 1)]
    trip = framed(recs, ["2026-12-12", "2026-12-13"],
                  busy={1: [("08:00", "11:00", "work", None), ("14:00", "21:00", "work", None)]})
    s = schedule_trip(trip)
    assert s.per_day[1] == []
    items = s.results[1].items
    assert [i.start for i in items if i.kind == "busy"] == [8 * 60, 14 * 60]
    assert any(i.kind == "meal_free" and i.name == "lunch" for i in items)
    assert all(i.end <= 21 * 60 for i in items)


def test_a_dawn_pin_given_up_gives_the_day_its_start_back():
    # A call at the lodging until 07:00 leaves no way to the hill by dawn: the pin goes, and so does the 05:00 start.
    recs = [spot("h1", CENTRE, 3, hours=None, features={"cloud_hunting": "present"}), spot("c2", CENTRE, 1)]
    trip = framed(recs, ["2026-12-12"], busy={0: [("05:00", "07:00", "call", "lodging")]})
    s = schedule_trip(trip)
    assert "h1" in s.per_day[0] and s.results[0].unpinned == ("h1",)
    assert s.ctxs[0].day.start == 8 * 60 and not any(b[2] == "rest" for b in s.ctxs[0].day.busy)
    assert not any(w["code"] == "early_start" for w in s.warnings)
    assert all(i.start >= 8 * 60 for i in s.results[0].items)


def test_a_stop_that_would_take_the_lunch_before_a_nap_waits_until_after_it():
    # The lodging is an hour from the stop: going out in the morning leaves no hour for lunch before the 12:30 nap.
    from plan_fixtures import day_ctx
    from planning.schedule import simulate
    cx = day_ctx([rec("p", *CENTRE)], minutes=60, start=480, end=1260, start_node="h", end_node="h",
                 extra_nodes=("h",))
    cx = replace(cx, home="h", day=replace(cx.day, busy=((750, 840, "nap", "Bé ngủ trưa", "lodging"),)))
    items = simulate(["p"], cx).items
    lunch = next(i for i in items if i.kind == "meal_free" and i.name == "lunch")
    visit = next(i for i in items if i.kind == "visit")
    assert lunch.end <= 750 and visit.start >= 840


def test_a_restaurant_reached_only_after_a_midday_rest_takes_dinner_and_lunch_is_eaten_before_the_rest():
    from plan_fixtures import all_days, day_ctx
    from planning.schedule import simulate
    cx = day_ctx([rec("r", *CENTRE, usable=("meal", "backup"), group="restaurant", hours=all_days("10:30", "21:30"))],
                 minutes=60, start=480, end=1260, start_node="h", end_node="h", extra_nodes=("h",))
    cx = replace(cx, home="h", require_meals=True,
                 day=replace(cx.day, busy=((720, 870, "rest", "Nghỉ trưa", "lodging"),)))
    r = simulate(["r"], cx)
    visit = next(i for i in r.items if i.kind == "visit")
    lunch = next(i for i in r.items if i.kind == "meal_free" and i.name == "lunch")
    assert 1050 <= visit.start <= 1200 and lunch.end <= 720
    assert not r.violations


def test_a_failed_eviction_leaves_no_trace_and_the_next_one_lets_the_place_in():
    from collections import Counter
    from planning.layout import _Layout
    only = lambda day: {d: [["08:00", "21:00"]] if d == day else [] for d in ("mon", "tue", "wed", "thu", "fri",
                                                                               "sat", "sun")}
    recs = [spot("e", CENTRE, 0), spot("a", CENTRE, 1, hours=only("sat")),        # day 1 (Saturday): a stays there
            spot("b", CENTRE, 2), spot("g", CENTRE, 3),                             # day 2 (Sunday)
            spot("c", CENTRE, 4), spot("d", CENTRE, 5), spot("f", CENTRE, 6),       # day 3 (Monday)
            spot("x", CENTRE, 7, hours=only("sun"), visit=(400, 400, 400))]         # fits only an empty Sunday
    trip = framed(recs, ["2026-12-12", "2026-12-13", "2026-12-14"])
    lay = _Layout(trip, trip.ctxs)
    for k, ids in enumerate((["e", "a"], ["b", "g"], ["c", "d", "f"])):
        for pid in ids:
            lay.days[k].put(pid, lay.days[k].option(pid))
    assert not lay.place("x")
    assert lay.evict(["x"]) == []                       # Saturday cannot be emptied (a); Sunday can
    held = Counter(p for day in lay.days for p in day.ids())
    assert held == Counter({p: 1 for p in "eabgcdfx"}) and "x" in lay.days[1].ids()


def test_a_light_day_and_a_free_day_stay_so_when_places_are_left_over():
    recs = [spot(f"c{i}", CENTRE, i, visit=(120, 180, 240)) for i in range(10)]
    trip = framed(recs, ["2026-12-12", "2026-12-13", "2026-12-14"], intensity={1: "free", 2: "light"})
    s = schedule_trip(trip)
    assert s.leftover and s.per_day[1] == []
    light = s.results[2]
    assert sum(i.end - i.start for i in light.items if i.kind in {"visit", "travel"}) <= capacity(s.ctxs[2])
    free_window = replace(trip.ctxs[1], day=replace(trip.ctxs[1].day, end=1260))     # a free day that kept a window
    s2 = schedule_trip(replace(trip, ctxs=[trip.ctxs[0], free_window, trip.ctxs[2]]))
    assert s2.per_day[1] == []


def test_a_day_the_estimate_overfilled_sheds_stops_until_it_ends_in_time(monkeypatch):
    # The clock disagrees with the layout (here: the layout is told to put every place on the one short day).
    import planning.build as build
    recs = [spot(f"c{i}", CENTRE, i, visit=(60, 90, 120)) for i in range(4)] + \
        [spot(f"s{i}", SOUTH, i, visit=(60, 90, 120)) for i in range(4)]
    trip = trip_of(recs, days=1)                       # 08:00-15:00
    monkeypatch.setattr(build, "assign", lambda trip_, ctxs, ids: ([list(ids)], []))
    s = schedule_trip(trip)
    assert not [v for v in s.violations if v.kind in {"day_window", "departure"}]
    assert sorted(s.per_day[0] + list(s.leftover)) == sorted(trip.by_place) and s.leftover
    # Restaurants whose leaving would cost the lunch: no single removal "fits" better, yet the 08:00-12:00 day must
    # still end in time (it used to stop after three tries and stay 190 minutes late).
    from plan_fixtures import all_days
    meal = dict(usable=("meal", "backup"), group="restaurant", hours=all_days("10:30", "22:00"))
    recs = [rec("p0", 11.84238, 108.44821), rec("p1", 11.85224, 108.45417, hours=all_days("13:00", "12:00"),
                                                    visit=(60, 90, 120)),
            rec("r2", 11.89695, 108.43927, **meal), rec("r3", 11.84939, 108.45595, **meal),
            rec("p4", 11.89748, 108.45583, visit=(60, 90, 120)), rec("r5", 11.8591, 108.44151, **meal)]
    d = decision([r["id"] for r in recs], days=1, leave_at="12:00",
                 base={"place_id": None, "text": "home", "lat": CENTRE[0], "lng": CENTRE[1]})
    s = schedule_trip(prepared(d, recs))
    assert not [v for v in s.violations if v.kind in {"day_window", "departure"}]
    assert sorted(s.per_day[0] + list(s.leftover)) == sorted(r["id"] for r in recs)


def test_a_day_laid_out_for_a_smaller_selection_never_lends_its_places_to_a_later_call():
    recs = [spot("c1", CENTRE, 0), spot("c2", CENTRE, 1), spot("c3", CENTRE, 2)]
    trip = trip_of(recs, days=3)
    schedule_trip(trip, kept={"c1"})            # the composer tries subsets on the same trip (shared day memo)
    s = schedule_trip(trip)
    assert all(set(cx.places) == set(trip.by_place) for cx in s.ctxs)


def test_a_six_stop_day_the_seeded_order_cannot_fit_gets_the_exhaustive_search():
    # Found by the review's probe (seed 2, trial 42): from the layout's order the local search ends 2 minutes past the
    # 15:00 end, while one of the 720 permutations fits the day.
    from plan_fixtures import all_days
    from planning.route import order_day
    meal = dict(usable=("meal", "backup"), group="restaurant", hours=all_days("10:30", "22:00"))
    short, mid = (10, 15, 20), (15, 20, 30)
    recs = [rec("q0", 11.901875, 108.449327, hours=all_days("13:00", "22:00"), visit=short),
            rec("q1", 11.947009, 108.46619, **meal), rec("q2", 11.950687, 108.458477, visit=short),
            rec("q3", 11.909425, 108.443748, visit=mid), rec("q4", 11.901562, 108.435439, visit=mid),
            rec("q5", 11.90304, 108.44959, **meal), rec("q6", 11.948614, 108.443864, hours=all_days("13:00", "17:00"),
                                                       visit=short),
            rec("q7", 11.949214, 108.472585, **meal), rec("q8", 11.948923, 108.456481, visit=mid),
            rec("q9", 11.94253, 108.463554, visit=mid), rec("q10", 11.904193, 108.440315, **meal),
            rec("q11", 11.904082, 108.446538, **meal)]
    d = decision([r["id"] for r in recs], days=1, base={"place_id": None, "text": "home", "lat": CENTRE[0], "lng": CENTRE[1]})
    trip = prepared(d, recs)
    cx = replace(trip.ctxs[0], places=trip.by_place)
    ids = ["q0", "q4", "q3", "q6", "q2", "q9"]
    assert not order_day(ids, cx).violations
    seeded = order_day(ids, cx, seed=ids)
    assert not seeded.violations and seeded.method == "exact"
