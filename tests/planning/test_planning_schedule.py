from plan_fixtures import all_days, day_ctx, flat_travel, rec

from planning.schedule import intervals_for, pin_window, simulate

OPEN_AT_10 = all_days("10:00", "20:00")


def kinds(r):
    return [i.kind for i in r.items]


def test_a_day_is_travel_visit_buffer_travel_visit_with_the_clock_running_forward():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)], start_node="h", extra_nodes=["h"])
    r = simulate(["a", "b"], cx)
    assert [(i.kind, i.start, i.end) for i in r.items] == [
        ("travel", 480, 490), ("visit", 490, 550), ("buffer", 550, 570), ("travel", 570, 580), ("visit", 580, 640)]
    assert (r.travel_min, r.wait_min, r.end, r.violations) == (20, 0, 640, ())


def test_arriving_before_opening_waits_and_the_wait_is_counted():
    cx = day_ctx([rec("a", 1, 1, hours=OPEN_AT_10)], start_node="h", extra_nodes=["h"])
    r = simulate(["a"], cx)
    assert [(i.kind, i.start, i.end) for i in r.items][1:] == [("wait", 490, 600), ("visit", 600, 660)]
    assert r.wait_min == 110


def test_with_no_start_point_the_first_stop_opens_the_day_instead_of_being_waited_for():
    r = simulate(["a"], day_ctx([rec("a", 1, 1, hours=OPEN_AT_10)]))
    assert [(i.kind, i.start) for i in r.items] == [("visit", 600)] and r.wait_min == 0


def test_a_place_closed_that_weekday_is_a_violation_and_an_unknown_weekday_does_not_constrain():
    closed = rec("a", 1, 1, hours={**all_days(), "mon": []})
    assert [v.kind for v in simulate(["a"], day_ctx([closed], weekday="mon")).violations] == ["hours"]
    assert simulate(["a"], day_ctx([closed], weekday="tue")).violations == ()
    assert simulate(["a"], day_ctx([closed], weekday=None)).violations == ()      # days differ, weekday unknown


def test_a_visit_that_would_end_after_closing_is_a_violation():
    late = rec("a", 1, 1, hours=all_days("08:00", "08:20"), visit=(30, 60, 90))     # shorter than even the short visit
    assert [v.kind for v in simulate(["a"], day_ctx([late])).violations] == ["hours"]


def test_the_second_opening_interval_is_used_when_the_first_is_missed():
    split = rec("a", 1, 1, hours={d: [["08:00", "09:00"], ["15:00", "20:00"]] for d in all_days()})
    r = simulate(["a"], day_ctx([split], start=600, start_node="h", extra_nodes=["h"]))    # arrives 10:10, morning over
    assert [(i.kind, i.start) for i in r.items][1:] == [("wait", 610), ("meal_free", 690), ("wait", 750), ("visit", 900)]
    assert r.violations == () and r.items[1].note == "opening"


def test_hours_unknown_do_not_constrain():
    cx = day_ctx([rec("a", 1, 1, hours=None)])
    assert intervals_for(cx.places["a"], cx) == [(0, 1440)]


def test_a_sunset_place_is_held_until_the_sun_is_about_to_set():
    cx = day_ctx([rec("a", 1, 1, features={"sunset_view": "present"})], sun=(360, 1050), start_node="h",
                 extra_nodes=["h"])
    assert pin_window(cx.places["a"], cx) == (975, 1030)           # 75 to 20 minutes before 17:30
    r = simulate(["a"], cx)
    assert [(i.kind, i.start) for i in r.items][1:] == [("wait", 490), ("meal_free", 690), ("wait", 750), ("visit", 975)]
    assert r.violations == () and r.items[1].note == "pin"


def test_a_dawn_place_is_pinned_to_sunrise_and_missing_it_is_a_violation():
    cx = day_ctx([rec("a", 1, 1, hours=None, features={"cloud_hunting": "present"})], sun=(360, 1050), start=480)
    assert pin_window(cx.places["a"], cx) == (330, 420)
    assert [v.kind for v in simulate(["a"], cx).violations] == ["hours"]      # the day opens at 08:00, too late


def test_without_a_known_sun_a_sun_pin_is_ignored_but_a_clock_pin_stays():
    sun = day_ctx([rec("a", 1, 1, features={"sunset_view": "present"})], sun=None)
    assert pin_window(sun.places["a"], sun) == (0, 1440)
    music = day_ctx([rec("b", 1, 1, features={"live_music": "present"})], sun=None)
    assert pin_window(music.places["b"], music) == (1080, 1200)


def test_a_meal_place_takes_the_lunch_window():
    cx = day_ctx([rec("m", 1, 1, usable=("meal", "backup"))], start_node="h", extra_nodes=["h"])
    r = simulate(["m"], cx)
    assert [(i.kind, i.start) for i in r.items][1:] == [("wait", 490), ("visit", 690)]


def test_a_lunch_nobody_takes_becomes_a_free_block_never_an_invented_place():
    cx = day_ctx([rec("a", 1, 1, visit=(60, 120, 240)), rec("b", 1, 1)], start=480, end_node="h", extra_nodes=["h"])
    r = simulate(["a", "b"], cx)
    meals = [i for i in r.items if i.kind == "meal_free"]
    assert len(meals) == 1 and meals[0].name == "lunch" and 690 <= meals[0].start <= 810
    assert all(i.place_id in (None, "a", "b") for i in r.items)


def test_a_day_that_opens_after_the_lunch_window_notes_it_instead_of_squeezing_a_meal_in():
    r = simulate(["a"], day_ctx([rec("a", 1, 1)], start=840))
    assert "meal_missed:lunch" in r.notes and "meal_free" not in kinds(r)


def test_a_rest_is_forced_once_active_minutes_pass_the_limit_and_the_day_goes_on():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1), rec("c", 1, 1)], start_node="h", end_node="h", extra_nodes=["h"])
    rests = [i for i in simulate(["a", "b", "c"], cx).items if i.kind == "rest"]
    assert len(rests) == 1 and rests[0].end - rests[0].start == 15


def test_no_rest_is_added_after_the_last_stop():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1), rec("c", 1, 1)], start_node="h", extra_nodes=["h"])
    assert kinds(simulate(["a", "b", "c"], cx))[-1] == "visit"


def test_the_buffer_grows_for_a_long_leg_and_for_uncertain_hours():
    plain = simulate(["a", "b"], day_ctx([rec("a", 1, 1), rec("b", 1, 1)]))
    long_leg = simulate(["a", "b"], day_ctx([rec("a", 1, 1), rec("b", 1, 1)], travel=flat_travel(["a", "b"], 40)))
    shaky = simulate(["a", "b"], day_ctx([rec("a", 1, 1, status="UNCERTAIN"), rec("b", 1, 1)]))

    def size(r):
        return next(i.end - i.start for i in r.items if i.kind == "buffer")

    assert (size(plain), size(long_leg), size(shaky)) == (20, 30, 30)


def test_the_way_back_to_the_end_node_counts_and_a_day_that_runs_late_is_a_violation():
    cx = day_ctx([rec("a", 1, 1, visit=(60, 600, 700))], start=480, end=700, end_node="h", extra_nodes=["h"])
    r = simulate(["a"], cx)
    assert r.items[-1].kind == "travel" and r.items[-1].to_id == "h"
    assert [v.kind for v in r.violations] == ["day_window"] and r.violations[0].minutes > 0


def test_an_empty_day_is_empty():
    r = simulate([], day_ctx([rec("a", 1, 1)], start_node="h", end_node="h", extra_nodes=["h"]))
    assert (r.items, r.end, r.violations) == ((), 480, ())


def test_the_order_search_does_not_prefer_an_order_that_skips_lunch_just_to_end_earlier():
    from planning.route import order_day
    recs = [rec("long", 1, 1, visit=(60, 240, 240)), rec("s1", 1, 1), rec("s2", 1, 1)]
    r = order_day(["s1", "long", "s2"], day_ctx(recs))
    assert "meal_missed:lunch" not in r.notes


def test_a_lunch_missed_after_the_last_stop_is_noted_even_with_no_end_point():
    r = simulate(["a"], day_ctx([rec("a", 1, 1, visit=(60, 420, 420))]))
    assert "meal_missed:lunch" in r.notes


def test_a_meal_place_takes_a_window_the_day_can_still_reach_not_one_already_over():
    cx = day_ctx([rec("a", 1, 1), rec("m", 1, 1, usable=("meal", "backup"))], start=840)
    r = simulate(["a", "m"], cx)
    assert r.violations == ()
    assert next(i.start for i in r.items if i.place_id == "m" and i.kind == "visit") >= 1080
    assert not any(i.kind == "meal_free" and i.name == "dinner" for i in r.items)


def test_a_wait_for_a_meal_window_says_so():
    cx = day_ctx([rec("m", 1, 1, usable=("meal", "backup"))], start_node="h", extra_nodes=["h"])
    assert simulate(["m"], cx).items[1].note == "meal"


def test_a_rainy_day_gets_a_longer_buffer_and_a_missing_forecast_changes_nothing():
    def size(rain):
        r = simulate(["a", "b"], day_ctx([rec("a", 1, 1), rec("b", 1, 1)], rain=rain))
        return next(i.end - i.start for i in r.items if i.kind == "buffer")

    assert (size(0.8), size(0.6), size(0.3), size(None)) == (30, 30, 20, 20)


def test_a_place_with_several_timed_features_needs_one_of_them_not_all():
    # sunrise 05:30-07:00 and sunset 16:15-17:10 never overlap: one reason to be there is enough
    both = rec("a", 1, 1, hours=None, features={"cloud_hunting": "present", "sunset_view": "present"})
    cx = day_ctx([both], sun=(360, 1050), start_node="h", extra_nodes=["h"])
    assert pin_window(cx.places["a"], cx) == (975, 1030)           # the one that fits inside the day
    assert simulate(["a"], cx).violations == ()


def test_a_timed_feature_the_opening_hours_cannot_host_does_not_pin_the_place():
    # live music 18:00-20:00 at a cafe that closes at 18:30 with a 45-minute shortest visit: visit it like any other
    cafe = rec("c", 1, 1, hours=all_days("07:00", "18:30"), visit=(45, 75, 150), features={"live_music": "present"})
    cx = day_ctx([cafe], pace="slow", start_node="h", extra_nodes=["h"])
    assert pin_window(cx.places["c"], cx) == (0, 1440)
    assert simulate(["c"], cx).violations == ()


def test_a_timed_visit_shrinks_to_end_before_closing():
    # live music from 18:00, cafe closes at 19:00: the slow 150-minute visit becomes 60 minutes at the music
    cafe = rec("c", 1, 1, hours=all_days("07:00", "19:00"), visit=(45, 75, 150), features={"live_music": "present"})
    cx = day_ctx([cafe], pace="slow", start_node="h", extra_nodes=["h"])
    v = next(i for i in simulate(["c"], cx).items if i.kind == "visit")
    assert (v.start, v.end) == (1080, 1140)


def test_a_meal_place_known_for_evening_music_takes_the_dinner_window():
    lau = rec("m", 1, 1, usable=("meal", "backup"), hours=all_days("11:00", "23:30"), features={"live_music": "present"})
    cx = day_ctx([lau], start_node="h", extra_nodes=["h"])
    r = simulate(["m"], cx)
    assert r.violations == () and next(i.start for i in r.items if i.kind == "visit") >= 1080


def test_a_visit_longer_than_an_opening_block_shrinks_to_fit_but_never_below_its_short_estimate():
    # open in two blocks with a lunch break; the slow-pace visit (240) fits neither, its range does
    split = {d: [["07:30", "11:30"], ["13:30", "17:00"]] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
    cx = day_ctx([rec("p", 1, 1, hours=split, visit=(60, 120, 240))], pace="slow", start_node="h", extra_nodes=["h"])
    r = simulate(["p"], cx)
    v = next(i for i in r.items if i.kind == "visit")
    assert r.violations == () and 60 <= v.end - v.start < 240 and v.end <= 690
    too_short = {d: [["10:00", "10:30"]] for d in split}
    cx = day_ctx([rec("q", 1, 1, hours=too_short, visit=(60, 120, 240))], pace="slow", start_node="h", extra_nodes=["h"])
    assert [x.kind for x in simulate(["q"], cx).violations] == ["hours"]


def test_a_visit_estimated_longer_than_the_day_is_cut_to_the_day():
    camp = rec("c", 1, 1, hours=None, visit=(180, 360, 1080))
    cx = day_ctx([camp], pace="slow")
    r = simulate(["c"], cx)
    v = next(i for i in r.items if i.kind == "visit")
    assert r.violations == () and v.end <= cx.day.end and v.end - v.start >= 180


def test_a_meal_place_that_opens_in_the_afternoon_takes_dinner_not_lunch():
    late = rec("m", 1, 1, usable=("meal", "backup"), hours=all_days("15:00", "22:00"))
    r = simulate(["m"], day_ctx([late], start_node="h", extra_nodes=["h"]))
    assert r.violations == () and next(i.start for i in r.items if i.kind == "visit") >= 1080


def test_a_meal_place_no_meal_window_can_host_is_visited_like_any_place():
    tea = rec("t", 1, 1, usable=("meal", "backup"), hours=all_days("14:00", "17:00"))
    r = simulate(["t"], day_ctx([tea], start_node="h", extra_nodes=["h"]))
    assert r.violations == ()
