from dataclasses import replace

from plan_fixtures import all_days, day_ctx, flat_travel, rec

from planning.schedule import simulate


def kinds(r):
    return [i.kind for i in r.items]


def test_no_buffer_rows_the_buffer_rides_on_the_leg():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)], start_node="h", end_node="h", extra_nodes=["h"])
    r = simulate(["a", "b"], cx)
    assert "buffer" not in kinds(r)
    leg = next(i for i in r.items if i.kind == "travel" and i.from_id == "a")
    assert leg.end - leg.start == 10 + cx.cfg.buffer_min["normal"] and leg.note == f"+{cx.cfg.buffer_min['normal']}"
    assert r.travel_min == 30                       # the matrix minutes only, never the buffer


def test_a_long_wait_near_the_lodging_is_a_rest_there():
    late = rec("b", 1, 1, hours=all_days("15:00", "20:00"))
    cx = day_ctx([rec("a", 1, 1), late], start_node="h", end_node="h", extra_nodes=["h"])
    cx = replace(cx, home="h")
    r = simulate(["a", "b"], cx)
    assert not [i for i in r.items if i.kind == "wait" and i.end - i.start > cx.cfg.realistic["wait_max"]]
    rest = [i for i in r.items if i.kind == "rest" and i.note == "home"]
    assert rest and rest[0].end - rest[0].start >= 60


def test_a_long_wait_far_from_the_lodging_is_free_time_before_leaving():
    late = rec("b", 1, 1, hours=all_days("15:00", "20:00"))
    cx = day_ctx([rec("a", 1, 1), late], start_node="h", end_node="h", extra_nodes=["h"],
                 travel=flat_travel(["a", "b", "h"], 10, a_h=40, b_h=40))
    cx = replace(cx, home="h")
    r = simulate(["a", "b"], cx)
    free = [i for i in r.items if i.kind == "free"]
    assert free and free[0].note == "a"
    arrive = next(i for i in r.items if i.kind == "travel" and i.to_id == "b")
    assert arrive.start >= free[0].end


def test_a_long_wait_after_a_lunch_that_leaves_no_room_to_move_the_leg_is_free_time():
    # a is left at 10:10, the leg to b is 25 min + 20 buffer, lunch takes 11:00-12:30 and b opens at 13:00: the leg
    # cannot be moved later, but the 30 minutes before b opens are still not a wait
    a = rec("a", 1, 1, visit=(30, 90, 120))
    b = rec("b", 1, 1, hours=all_days("13:00", "20:00"))
    cx = day_ctx([a, b], start_node="h", end_node="h", extra_nodes=["h"],
                 travel=flat_travel(["a", "b", "h"], 10, a_b=25))
    r = simulate(["a", "b"], cx)
    assert not [i for i in r.items if i.kind == "wait" and i.end - i.start > cx.cfg.realistic["wait_max"]]
    free = [i for i in r.items if i.kind == "free" and i.start == 750]
    assert free and free[0].end == 780 and free[0].note == "b"
    assert r.violations == () and r.wait_min <= cx.cfg.realistic["wait_max"]


def test_a_meal_window_that_opens_inside_the_buffer_leaves_no_hole_in_the_timeline():
    # lunch opens 11:00 while the buffer after the visit (45 min) is still running: the minutes before the meal are
    # an item, a short wait when 20 or fewer, free time around the stop when longer
    for visit, kind, length in ((120, "wait", 20), (100, "free", 40)):        # the visit ends 10:40 / 10:20
        cx = day_ctx([rec("a", 1, 1, visit=(30, visit, visit + 30)), rec("b", 1, 1)], start_node="h", end_node="h",
                     extra_nodes=["h"])
        cx = replace(cx, cfg=replace(cx.cfg, buffer_min={**cx.cfg.buffer_min, "normal": 45}))
        items = sorted(simulate(["a", "b"], cx).items, key=lambda i: i.start)
        lunch = next(i for i in items if i.kind == "meal_free" and i.name == "lunch")
        before = items[items.index(lunch) - 1]
        assert (before.kind, before.end, before.end - before.start) == (kind, lunch.start, length)
        assert lunch.start == 660 and before.note in ("meal", "a")


def test_a_day_that_ends_at_noon_gets_a_sixty_minute_lunch():
    # the day ends at the last stop (no end node), so nothing follows the meal
    late = rec("a", 1, 1, hours=all_days("10:00", "20:00"))
    cx = day_ctx([late], start=480, end=720, start_node="h", extra_nodes=["h"])
    cx = replace(cx, require_meals=True)
    r = simulate(["a"], cx)
    assert [(i.kind, i.start, i.end) for i in r.items if i.kind == "visit"] == [("visit", 600, 660)]
    lunch = [i for i in r.items if i.kind == "meal_free" and i.name == "lunch"]
    assert [(i.start, i.end) for i in lunch] == [(660, 720)]
    from planning.validate import validate
    assert not validate([cx], [r], [], set(), None, None)
    short = replace(cx, day=replace(cx.day, end=690))                      # 11:00-11:30 is below meal_min: no lunch
    assert not [i for i in simulate(["a"], short).items if i.kind == "meal_free" and i.name == "lunch"]


def test_the_way_home_is_kept_out_of_the_lunch_the_day_end_leaves_room_for():
    from planning.validate import validate
    late = rec("b", 1, 1, hours=all_days("10:00", "20:00"))
    recs = [late]

    def day(end, road, buffer):
        cx = day_ctx(recs, start=480, end=end, start_node="h", end_node="h", extra_nodes=["h"],
                     travel=flat_travel(["b", "h"], 10, b_h=road))
        return replace(cx, home="h", require_meals=True,
                       cfg=replace(cx.cfg, buffer_min={**cx.cfg.buffer_min, "normal": buffer}))

    # 08:00-12:00, 20 minutes of road and a 20 minute buffer home: b ends 11:00, 20 minutes are left for a lunch: none is
    # needed and the day is valid (it used to get a lunch ending at 12:00 and then overrun)
    cx = day(720, 20, 20)
    r = simulate(["b"], cx)
    assert not [i for i in r.items if i.kind == "meal_free" and i.name == "lunch"]
    assert r.end <= 720 and not validate([cx], [r], [], set(), None, None)
    # a half hour later the lunch is shortened to what the way home leaves: it ends 15 minutes before the day does
    cx = day(750, 5, 10)
    r = simulate(["b"], cx)
    lunch = next(i for i in r.items if i.kind == "meal_free" and i.name == "lunch")
    assert (lunch.start, lunch.end) == (660, 735) and r.end == 750
    assert not validate([cx], [r], [], set(), None, None)


def test_meal_fit_is_the_full_length_the_shortened_length_or_nothing():
    from planning.schedule import meal_fit
    cx = day_ctx([rec("a", 1, 1)], end=720)
    assert [meal_fit("lunch", cx, s) for s in (600, 630, 660, 690, 720)] == [90, 90, 60, 0, 0]
    assert [meal_fit("breakfast", cx, s) for s in (600, 690, 700, 720)] == [30, 30, 0, 0]       # a 30-minute meal is below meal_min: it is kept whole or not at all


def _verdicts(cx, order):
    from planning.validate import validate
    r = simulate(order, cx)
    scheduler = sorted(v.detail for v in r.violations if v.kind == "meal_missing")
    validator = sorted(v.detail for v in validate([cx], [r], [], set(), None, None) if v.kind == "meal_missing")
    return r, scheduler, validator


def _tight(recs, end, start, travel, buffer):
    cx = day_ctx(recs, start=start, end=end, start_node="h", end_node="h", extra_nodes=["h"], travel=travel)
    return replace(cx, home="h", require_meals=True, cfg=replace(cx.cfg, buffer_min={**cx.cfg.buffer_min, "normal": buffer}))


def test_scheduler_and_validator_agree_when_the_visit_in_progress_leaves_no_room_for_lunch():
    # day 10:00-12:15, a is visited 10:45-11:45 across the lunch opening: free at 11:45 only 30 minutes remain, minus
    # the way home: no lunch is needed by either
    a = rec("a", 1, 1, hours=all_days("08:00", "20:00"), visit=(30, 60, 90))
    c = rec("c", 1, 1, hours=all_days("08:00", "20:00"), visit=(30, 30, 30))
    cx = _tight([a, c], 735, 600, flat_travel(["a", "c", "h"], 5), 5)
    r, scheduler, validator = _verdicts(cx, ["c", "a"])
    assert scheduler == validator == [] and r.violations == ()


def test_scheduler_and_validator_agree_when_the_meal_can_only_start_after_the_visit():
    # b is visited 10:00-11:30, the day ends 12:30, the way home takes 5 + 10: at 11:30 only 45 minutes are left,
    # so the 11:00 window does not make lunch needed (measured at 11:00 it would have, 75 minutes)
    b = rec("b", 1, 1, hours=all_days("10:00", "20:00"), visit=(30, 90, 120))
    cx = _tight([b], 750, 480, flat_travel(["b", "h"], 10, b_h=5), 10)
    r, scheduler, validator = _verdicts(cx, ["b"])
    assert scheduler == validator == [] and r.violations == ()
    # the same day ending 20 minutes later leaves 65 minutes at 11:30: the lunch is needed and the plan holds it
    r, scheduler, validator = _verdicts(replace(cx, day=replace(cx.day, end=770)), ["b"])
    assert scheduler == validator == [] and any(i.kind == "meal_free" and i.name == "lunch" for i in r.items)
