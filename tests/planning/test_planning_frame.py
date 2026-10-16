from plan_fixtures import CFG

from planning.frame import trip_days


def ctx(**kw):
    base = {"start_date": "2026-12-12", "days": 3, "arrive_at": None, "leave_at": None, "day_end": None}
    return {**base, **kw}


def test_every_day_has_a_date_a_weekday_and_the_default_window():
    days = trip_days(ctx(), CFG, "h")
    assert [(d.date.isoformat(), d.weekday) for d in days] == [
        ("2026-12-12", "sat"), ("2026-12-13", "sun"), ("2026-12-14", "mon")]
    assert (days[1].start, days[1].end) == (480, 1260)


def test_the_first_day_opens_at_arrival_and_the_last_closes_at_departure():
    days = trip_days(ctx(arrive_at="13:30", leave_at="12:00", day_end="20:00"), CFG, "h")
    assert (days[0].start, days[0].end) == (810, 1200)
    assert (days[1].start, days[1].end) == (480, 1200)
    assert (days[2].start, days[2].end) == (480, 720)


def test_the_last_day_closes_at_the_default_leave_time_when_the_user_gave_none():
    assert trip_days(ctx(), CFG, "h")[-1].end == CFG.leave_at


def test_a_one_day_trip_is_both_the_first_and_the_last_day():
    (d,) = trip_days(ctx(days=1, arrive_at="10:00", leave_at="17:00"), CFG, "h")
    assert (d.start, d.end, d.start_node, d.end_node) == (600, 1020, "h", "h")


def test_every_day_starts_and_ends_at_the_lodging():
    assert [(d.start_node, d.end_node) for d in trip_days(ctx(), CFG, "h")] == [("h", "h")] * 3


def test_days_and_dates_the_user_never_gave_stay_unknown():
    days = trip_days(ctx(days=None, start_date=None), CFG, "h")
    assert len(days) == CFG.default_days and all(d.date is None and d.weekday is None for d in days)
    only_date = trip_days(ctx(days=None), CFG, "h")      # a start date without a length gives no weekdays
    assert all(d.weekday is None for d in only_date)


# --- the user's day frame: busy blocks, arrival / departure points, skipped meals (Task 4) ---

from dataclasses import replace

from plan_fixtures import CENTRE, SOUTH, all_days, day_ctx, decision, prepared, rec, spot

from planning.build import pull_early, schedule_trip
from planning.model import Day, Item
from planning.schedule import pin_window, simulate
from planning.validate import validate


def compiled(**kw):
    day = {"date": "2026-11-07", "start": "08:00", "end": "21:00", "busy": [], "intensity": "normal", **kw}
    return {"frame": {"days": [day], "arrive": None, "leave": None, "meals": {"skip": [], "breakfast_at_lodging": False,
                                                                            "snacks": False, "shift_min": 0}}}


def test_trip_days_reads_busy_blocks_and_intensity():
    ctx = compiled(busy=[{"start": "15:00", "end": "16:00", "kinds": ["work"], "labels": ["Họp"], "where": "lodging"}],
                   intensity="light")
    d = trip_days(ctx, CFG, "h")[0]
    assert d.busy == ((900, 960, "work", "Họp", "lodging"),) and d.intensity == "light"


def test_trip_days_without_frame_keeps_the_config_window():
    d = trip_days({"days": 1, "start_date": None}, CFG, None)[0]
    assert (d.start, d.end, d.busy, d.intensity) == (CFG.day_start, CFG.leave_at, (), "normal")


def test_a_meeting_at_the_lodging_sends_the_day_home_and_back():
    # the meeting is at 16:00 (the brief had 15:00: from a 14:00 start, 10' road + 60' visit + 10' road + 20' buffer
    # cannot end by 15:00, so no schedule could go out and come home before it)
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)], start_node="h", end_node="h", extra_nodes=["h"], start=840)
    cx = replace(cx, home="h", day=Day(0, None, "mon", 840, 1260, "h", "h", busy=((960, 1020, "work", "Họp", "lodging"),)))
    r = simulate(["a", "b"], cx)
    busy = next(i for i in r.items if i.kind == "busy")
    assert (busy.start, busy.end, busy.name) == (960, 1020, "Họp")
    assert all(not (i.start < 1020 and 960 < i.end) for i in r.items if i.kind in {"visit", "travel"})
    before = [i for i in r.items if i.kind == "travel" and i.end <= 960]
    assert before and before[-1].to_id == "h"
    after = [i for i in r.items if i.kind == "visit" and i.start >= 1020]
    assert after and not r.violations


def test_a_skipped_breakfast_is_not_planned():
    cx = day_ctx([rec("a", 1, 1)], start_node="h", end_node="h", extra_nodes=["h"])
    cx = replace(cx, meal_skip=frozenset({"breakfast"}))
    r = simulate(["a"], cx)
    assert not [i for i in r.items if i.kind == "meal_free" and i.name == "breakfast"]


def test_a_duration_the_user_said_wins_over_the_estimate():
    recs = [spot("c1", CENTRE, 0, group="cafe", usable=("experience", "meal", "backup"))]
    d = decision(["c1"], days=1)
    d["trip_context"]["context"]["frame"] = {"days": [{"date": "2026-12-12", "start": "08:00", "end": "21:00",
                                                       "busy": [], "intensity": "normal"}],
                                             "arrive": None, "leave": None, "visit": {"cafe": 120}, "meals": {}}
    p = prepared(d, recs).by_place["c1"]
    assert (p.visit["short"], p.visit["typical"], p.visit["long"], p.visit["source"]) == (120, 120, 120, "user")


def test_a_lunch_before_a_nap_at_the_lodging_leaves_room_to_get_home():
    cx = day_ctx([rec("a", 1, 1)], start_node="h", end_node="h", extra_nodes=["h"], start=600)
    cx = replace(cx, home="h", day=Day(0, None, "mon", 600, 1260, "h", "h",
                                       busy=((750, 840, "nap", "Bé ngủ trưa", "lodging"),)))
    r = simulate(["a"], cx)
    assert not r.violations, r.violations
    assert all(not (i.start < 840 and 750 < i.end) for i in r.items if i.kind in {"visit", "travel", "meal_free"})
    lunch = [i for i in r.items if i.kind == "meal_free" and i.name == "lunch"]
    assert lunch and lunch[0].end <= 750 - 10           # eaten and home (10 min away) before the nap


def test_the_rest_rhythm_the_user_gave_replaces_the_pace_default():
    recs = [rec(c, 1, 1, visit=(60, 60, 60)) for c in "abc"]
    cx = replace(day_ctx(recs, start_node="h", end_node="h", extra_nodes=["h"], minutes=5), rest=(60, 25))
    rests = [i for i in simulate(["a", "b", "c"], cx).items if i.kind == "rest"]
    assert rests and all(i.end - i.start == 25 for i in rests)


def frame_trip(*, arrive=None, leave=None, entry=None, exit=None, days=1, busy=(), drive=None, sources=None, starts=None):
    """A decision whose context carries a CompiledFrame over two centre places."""
    recs = [spot("c1", CENTRE, 0), spot("c2", CENTRE, 1)]
    d = decision(["c1", "c2"], days=days, start_date="2026-12-12", base={"text": "home", "lat": CENTRE[0] + 0.001,
                                                                         "lng": CENTRE[1]}, entry=entry, exit=exit)
    fdays = [{"date": f"2026-12-{12 + i}", "start": (starts or {}).get(i, "08:00"), "end": "21:00",
              "busy": list(busy), "intensity": "normal"} for i in range(days)]
    d["trip_context"]["context"]["frame"] = {"days": fdays, "arrive": arrive, "leave": leave, "drive_day_min": drive,
                                             "meals": {"skip": [], "breakfast_at_lodging": False, "snacks": False,
                                                       "shift_min": 0}, "rest": None, "visit": {}}
    if sources:
        d["trip_context"]["sources"] = sources
    return d, recs


AIRPORT = {"text": "airport", "lat": SOUTH[0], "lng": SOUTH[1]}


def test_arrival_and_departure_points_open_and_close_the_trip():
    d, recs = frame_trip(arrive={"at": "2026-12-12T10:00", "how": "plane"}, leave={"at": "2026-12-13T16:40", "how": "plane"},
                         entry=AIRPORT, exit=AIRPORT, days=2, starts={0: "11:15"})
    trip = prepared(d, recs)
    first, last = trip.days
    assert (first.start_node, first.start, first.start_by_user) == ("@entry", 600 + 45, True)
    assert (last.end_node, last.end) == ("@exit", 1000 - 45)
    from planning.schedule import simulate as sim
    r = sim(["c1"], trip.ctxs[0])
    road, bags = r.items[0], r.items[1]
    assert (road.kind, road.from_id, road.to_id, road.start) == ("travel", "@entry", "@home", 645)
    assert (bags.kind, bags.note, bags.end - bags.start) == ("rest", "drop_bags", CFG.realistic["drop_bags_min"])


def test_a_departure_time_the_user_gave_for_the_last_day_is_kept():
    d, recs = frame_trip(leave={"at": "2026-12-12T16:40", "how": "plane"}, exit=AIRPORT,
                         sources={"frame.days.0.end": "user"})
    d["trip_context"]["context"]["frame"]["days"][0]["end"] = "13:00"
    assert prepared(d, recs).days[0].end == 780


def test_missing_the_departure_is_a_physical_violation():
    d, recs = frame_trip(leave={"at": "2026-12-12T16:40", "how": "plane"}, exit=AIRPORT)
    trip = prepared(d, recs)
    sched = schedule_trip(trip)
    late = replace(sched.results[0], items=sched.results[0].items + (Item("travel", 960, 1000, from_id="c2",
                                                                          to_id="@exit", mode="motorbike"),))
    v = [x for x in validate(sched.ctxs, [late], [], set(), None, None) if x.kind == "departure"]
    assert v and v[0].physical


def test_a_visit_over_a_busy_block_and_a_day_over_the_driving_cap_are_violations():
    block = {"start": "10:00", "end": "11:00", "kinds": ["work"], "labels": ["Họp"], "where": "lodging"}
    d, recs = frame_trip(busy=[block], drive=1)
    trip = prepared(d, recs)
    sched = schedule_trip(trip)
    assert trip.cfg.realistic["drive_day_min"] == 1
    kinds = {x.kind for x in sched.violations}
    assert "drive_day" in kinds and "busy" not in kinds          # the schedule keeps the meeting free
    over = replace(sched.results[0], items=(Item("visit", 590, 640, place_id="c1", name="c1"),))
    assert any(x.kind == "busy" and not x.physical for x in validate(sched.ctxs, [over], [], set(), None, None))


# --- dawn on a day whose start is only a default (carried ruling from Task 2) ---

def dual_ctx(**kw):
    """A day over one hill known for dawn and for sunset, dawn first as prepare orders it."""
    from planning.roles import pin_order
    cx = day_ctx([rec("hill", 1, 1, hours=None, features={"cloud_hunting": "present", "sunset_view": "present"})],
                 sun=(360, 1050), start=480, **kw)
    hill = replace(cx.places["hill"], pins=pin_order(cx.places["hill"].pins, set()))
    return replace(cx, places={"hill": hill})


def test_trip_days_marks_the_starts_the_user_set():
    plain = trip_days({"days": 2, "start_date": "2026-12-12"}, CFG, "h")
    assert [x.start_by_user for x in plain] == [False, False]
    arrived = trip_days({"days": 2, "start_date": "2026-12-12", "arrive_at": "09:00"}, CFG, "h")
    assert [x.start_by_user for x in arrived] == [True, False]
    framed = compiled()
    framed["frame"]["arrive"] = {"at": "2026-11-07T06:00", "how": "bus"}
    assert trip_days(framed, CFG, "h")[0].start_by_user
    said = trip_days(compiled(), CFG, "h", sources={"frame.days.0.start": "user"})
    assert said[0].start_by_user and not trip_days(compiled(), CFG, "h")[0].start_by_user


def test_a_default_first_day_is_pulled_to_dawn_like_a_later_day():
    cx = dual_ctx()
    hill = cx.places["hill"]
    assert hill.pins[0] == "cloud_hunting" and pin_window(hill, cx) == (330, 420)
    pulled, who = pull_early(cx, ["hill"], cx.places, cx.travel)
    assert who == "hill" and pulled.day.start <= 330


def test_a_start_the_user_set_is_never_moved_and_dawn_gives_way_to_sunset():
    cx = dual_ctx()
    for index in (0, 1):
        fixed = replace(cx, day=replace(cx.day, index=index, start_by_user=True))
        assert pin_window(fixed.places["hill"], fixed)[0] > 900
        assert pull_early(fixed, ["hill"], fixed.places, fixed.travel) == (fixed, None)


def test_the_plan_says_when_dawn_was_swapped_for_sunset():
    recs = [spot("hill", CENTRE, 0, hours=None, features={"cloud_hunting": "present", "sunset_view": "present"})]
    d, _ = frame_trip(sources={"frame.days.0.start": "user"})
    d["confirmed"] = [{"id": "hill", "name": "hill", "role": "selected", "visit": None, "flags": [], "relaxed": []}]
    sched = schedule_trip(prepared(d, recs))
    assert any(w["code"] == "dawn_swapped" for w in sched.warnings)
    visit = next(i for i in sched.results[0].items if i.kind == "visit")
    assert visit.start > 900
    d2, _ = frame_trip()
    d2["confirmed"] = d["confirmed"]
    sched2 = schedule_trip(prepared(d2, recs))
    assert not any(w["code"] == "dawn_swapped" for w in sched2.warnings)
    assert next(i for i in sched2.results[0].items if i.kind == "visit").start < 480


def test_a_frame_start_earlier_than_the_arrival_buffer_is_the_users_and_is_kept():
    d, recs = frame_trip(arrive={"at": "2026-12-12T05:00", "how": "bus"}, entry=AIRPORT, starts={0: "05:00"})
    assert prepared(d, recs).days[0].start == 300            # never before the arrival, never later than the frame


# --- fix round 1 ---

def nap_day(start=600, nap=(690, 780), **kw):
    cx = day_ctx([rec("a", 1, 1)], start_node="h", end_node="h", extra_nodes=["h"], start=start, **kw)
    return replace(cx, home="h", require_meals=True,
                   day=Day(0, None, "mon", start, 1260, "h", "h", busy=((*nap, "nap", "Bé ngủ trưa", "lodging"),)))


def test_a_nap_over_the_lunch_opening_moves_lunch_after_it_instead_of_deleting_it():
    from planning.schedule import _meal_slots, meals_needed
    cx = nap_day()
    _, free = _meal_slots(["a"], cx)
    assert "lunch" in free                                    # 13:00 is still inside the 11:00-13:30 window
    r = simulate(["a"], cx)
    lunch = [i for i in r.items if i.kind == "meal_free" and i.name == "lunch"]
    assert lunch and 780 <= lunch[0].start <= 810, r.items
    assert not r.violations and not validate([cx], [r], [], set(), None, None)
    without = tuple(i for i in r.items if not (i.kind == "meal_free" and i.name == "lunch"))
    assert meals_needed(without, cx) == ["lunch"]             # the validator asks for it too


def frame_with_leave(at="2026-12-12T16:40", end="21:00", sources=None):
    d, recs = frame_trip(leave={"at": at, "how": "plane"}, exit=AIRPORT, sources=sources)
    d["trip_context"]["context"]["frame"]["days"][0]["end"] = end
    return d, recs


def test_the_departure_deadline_holds_whatever_the_days_end_says():
    trip = prepared(*frame_with_leave())
    day = trip.days[0]
    assert (day.end, day.depart_by) == (955, 955)
    stretched = replace(trip.ctxs[0], day=replace(day, end=1380))           # a window edited to 23:00
    from planning.model import DayResult
    late = DayResult((Item("visit", 1200, 1300, place_id="c1", name="c1"),
                      Item("travel", 1300, 1340, from_id="c1", to_id="@exit", mode="motorbike")), ("c1",), (), 40, 0, 1340)
    v = [x for x in validate([stretched], [late], [], set(), None, None) if x.kind == "departure"]
    assert v and v[0].physical


def test_an_edited_window_never_passes_the_departure():
    from planning.build import window_override
    trip = prepared(*frame_with_leave())
    assert window_override(trip.days[0], 480, 1380).end == 955
    assert window_override(trip.days[0], 480, 900).end == 900
    # A leave day Trip left free keeps no window, yet the flight still binds it: an edit opening it stops at the
    # departure, and anything planned past the departure is flagged as physical.
    d, recs = frame_with_leave(end="15:25")
    d["trip_context"]["context"]["frame"]["days"][0]["intensity"] = "free"
    free = prepared(d, recs).days[0]
    assert (free.start, free.end, free.depart_by) == (480, 480, 955)
    opened = window_override(free, 480, 1200)
    assert (opened.end, opened.depart_by) == (955, 955)
    from planning.model import DayResult
    late = DayResult((Item("visit", 1000, 1100, place_id="c1", name="c1"),
                      Item("travel", 1100, 1140, from_id="c1", to_id="@exit", mode="motorbike")), ("c1",), (), 40, 0, 1140)
    cx = replace(prepared(d, recs).ctxs[0], day=replace(free, end=1200))       # whatever the window says
    v = [x for x in validate([cx], [late], [], set(), None, None) if x.kind == "departure"]
    assert v and v[0].physical
    # The same flight with no known exit point still binds the day.
    d, recs = frame_trip(leave={"at": "2026-12-12T16:40", "how": "plane"})
    unplaced_exit = prepared(d, recs).days[0]
    assert unplaced_exit.depart_by == 955 and window_override(unplaced_exit, 480, 1380).end == 955


def test_the_last_day_never_runs_later_than_the_frame_or_the_departure_allows():
    late_flight = prepared(*frame_with_leave(at="2026-12-12T23:30", end="21:00",
                                             sources={"frame.days.0.end": "user"})).days[0]
    assert late_flight.end == 1260                          # a 23:30 flight does not stretch the user's 21:00 to 22:45
    said = prepared(*frame_with_leave(end="20:00", sources={"frame.days.0.end": "user"})).days[0]
    assert said.end == 955                                  # the user's 20:00 still has to make the 16:40 flight


def test_an_event_somewhere_unknown_is_flagged_and_one_at_a_known_place_is_travelled_to():
    block = {"start": "15:00", "end": "16:00", "kinds": ["event"], "labels": ["Tiệc"], "where": "Nhà hàng X"}
    trip = prepared(*frame_trip(busy=[block]))
    assert any(w["code"] == "event_location_unknown" for w in trip.warnings)
    known = {**block, "where": "c2"}
    trip = prepared(*frame_trip(busy=[known]))
    assert not any(w["code"] == "event_location_unknown" for w in trip.warnings)
    from planning.schedule import simulate as sim
    r = sim(["c1"], trip.ctxs[0])
    to_event = [i for i in r.items if i.kind == "travel" and i.to_id == "c2" and i.end <= 900]
    assert to_event and not r.violations, r.items


def test_a_trip_wide_day_start_the_user_gave_is_never_pulled_to_dawn():
    framed = compiled()
    framed["frame"]["days"].append({"date": "2026-11-08", "start": "08:00", "end": "21:00", "busy": [],
                                    "intensity": "normal"})
    days = trip_days(framed, CFG, "h", sources={"frame.day_start": "user"})
    assert days[1].start_by_user
    assert not trip_days(framed, CFG, "h")[1].start_by_user


def test_bags_are_dropped_only_when_arriving_before_check_in():
    early = prepared(*frame_trip(arrive={"at": "2026-12-12T10:00", "how": "plane"}, entry=AIRPORT, starts={0: "11:15"}))
    late = prepared(*frame_trip(arrive={"at": "2026-12-12T15:00", "how": "plane"}, entry=AIRPORT, starts={0: "16:15"}))
    from planning.schedule import simulate as sim
    assert any(i.note == "drop_bags" for i in sim(["c1"], early.ctxs[0]).items)
    after = sim(["c1"], late.ctxs[0]).items
    assert not any(i.note == "drop_bags" for i in after) and after[0].from_id == "@entry"


def test_a_check_in_hour_the_user_gave_is_kept_and_a_profile_one_is_not():
    def first_start(source):
        d, recs = frame_trip(arrive={"at": "2026-12-12T10:00", "how": "plane"}, entry=AIRPORT, starts={0: "14:00"},
                             days=2, sources={"checkin_at": source})
        d["trip_context"]["context"]["checkin_at"] = "14:00"
        return prepared(d, recs).days[0]
    said, prior = first_start("user"), first_start("profile")
    assert (said.start, said.start_by_user) == (840, True)
    assert (prior.start, prior.start_by_user) == (645, True)      # the arrival still bounds it; the prior does not


def test_a_meeting_over_the_lunch_opening_leaves_lunch_after_it():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)], start_node="h", end_node="h", extra_nodes=["h"], start=480)
    cx = replace(cx, home="h", require_meals=True,
                 day=Day(0, None, "mon", 480, 1260, "h", "h", busy=((660, 780, "work", "Họp", "lodging"),)))
    r = simulate(["a", "b"], cx)
    lunch = [i for i in r.items if i.kind == "meal_free" and i.name == "lunch"]
    assert lunch and lunch[0].start >= 780, r.items
    assert not validate([cx], [r], [], set(), None, None)


def test_a_crowd_day_queue_counts_when_heading_back_for_a_meeting(monkeypatch):
    import planning.conditions as conditions
    from planning.conditions import DayCond
    monkeypatch.setattr(conditions, "crowd_sensitive", lambda p, cond, cfg: cond is not None and cond.crowd != "normal")
    for block in (920, 925, 930):
        cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)], start_node="h", end_node="h", extra_nodes=["h"], start=840)
        cx = replace(cx, home="h", cond=DayCond(crowd="peak"),
                     day=Day(0, None, "mon", 840, 1260, "h", "h", busy=((block, block + 60, "work", "Họp", "lodging"),)))
        r = simulate(["a", "b"], cx)
        kinds = {v.kind for v in validate([cx], [r], [], set(), None, None)}
        assert not kinds & {"busy", "overlap"}, (block, r.items)


def test_a_pace_rest_never_runs_into_a_block_away_from_the_lodging():
    for where in ("online", "lodging"):
        cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)], start_node="h", end_node="h", extra_nodes=["h"], start=840)
        cx = replace(cx, home="h", rest=(60, 25),
                     day=Day(0, None, "mon", 840, 1260, "h", "h", busy=((925, 985, "event", "Gọi", where),)))
        r = simulate(["a", "b"], cx)
        assert not any(i.start < 985 and 925 < i.end for i in r.items if i.kind == "rest"), (where, r.items)
        assert not {v.kind for v in validate([cx], [r], [], set(), None, None)} & {"busy", "overlap"}, where


def test_a_block_reached_late_never_shows_an_item_over_what_came_before():
    cx = day_ctx([rec("a", 1, 1)], start_node="h", end_node="h", extra_nodes=["h"], start=540)
    cx = replace(cx, home="h", day=Day(0, None, "mon", 540, 1260, "h", "h", busy=((500, 600, "work", "Họp", None),)))
    items = sorted(simulate(["a"], cx).items, key=lambda i: (i.start, i.end))
    busy = next(i for i in items if i.kind == "busy")
    assert busy.start >= 540
    assert all(b.start >= a.end for a, b in zip(items, items[1:])), items


def test_a_block_straddling_the_shortened_last_day_is_clipped_to_it():
    block = {"start": "15:00", "end": "17:00", "kinds": ["work"], "labels": ["Họp"], "where": "lodging"}
    d, recs = frame_trip(leave={"at": "2026-12-12T16:40", "how": "plane"}, exit=AIRPORT, busy=[block])
    day = prepared(d, recs).days[0]
    assert day.blocks == ((900, 955, "work", "Họp", "lodging"),)
    assert day.busy == ((900, 1020, "work", "Họp", "lodging"),)        # the user's block itself stays whole


def test_trips_own_end_on_the_leave_day_gives_way_to_the_departure_less_its_buffer():
    # Trip compiles a 16:40 flight with no end wish to 15:25 (departure - 45 - its fixed 30-min road); the road to the
    # exit is a leg of the day now, so the day keeps until 15:55, the departure less the airport buffer
    compiled_end = prepared(*frame_with_leave(end="15:25")).days[0]
    assert (compiled_end.end, compiled_end.depart_by) == (955, 955)
    said = prepared(*frame_with_leave(end="15:25", sources={"frame.days.0.end": "user"})).days[0]
    assert (said.end, said.depart_by) == (925, 955)
    checkout = frame_with_leave(end="15:25", sources={"checkout_at": "user"})
    checkout[0]["trip_context"]["context"]["checkout_at"] = "15:25"
    assert prepared(*checkout).days[0].end == 925


def test_an_online_block_keeps_the_person_where_they_are_and_needs_no_place():
    block = {"start": "15:00", "end": "16:00", "kinds": ["work"], "labels": ["Họp online"], "where": "Online"}
    trip = prepared(*frame_trip(busy=[block]))
    assert not any(w["code"] == "event_location_unknown" for w in trip.warnings)
    from planning.schedule import simulate as sim
    r = sim(["c1", "c2"], trip.ctxs[0])
    busy = next(i for i in r.items if i.kind == "busy")
    assert busy.start == 900 and not [i for i in r.items if i.kind == "travel" and i.to_id == "@home"
                                      and i.end <= 900], r.items          # nobody goes back to the lodging for a call
    assert not {v.kind for v in validate(trip.ctxs, [r], [], set(), None, None)} & {"busy", "overlap"}


def test_a_leave_day_trip_left_free_keeps_no_window_and_its_blocks_still_bind():
    block = {"start": "08:00", "end": "15:25", "kinds": ["work"], "labels": ["Họp"], "where": "lodging"}
    d, recs = frame_with_leave(end="15:25")
    day = d["trip_context"]["context"]["frame"]["days"][0]
    day["busy"], day["intensity"] = [block], "free"
    trip = prepared(d, recs)
    first = trip.days[0]
    assert first.end == first.start == 480 and first.blocks == ()
    assert first.busy == ((480, 925, "work", "Họp", "lodging"),)
    from planning.schedule import simulate as sim
    kinds = {v.kind for v in validate(trip.ctxs, [sim(["c1", "c2"], trip.ctxs[0])], [], set(), None, None)}
    assert {"busy", "day_window"} <= kinds                       # a stop squeezed into it is caught, not hidden


def test_a_check_out_the_user_gave_does_not_make_a_prior_end_theirs():
    d, recs = frame_with_leave(end="15:25", sources={"frame.days.0.end": "profile", "checkout_at": "user"})
    d["trip_context"]["context"]["checkout_at"] = "15:25"
    assert prepared(d, recs).days[0].end == 955                 # the prior end gives way to the departure
