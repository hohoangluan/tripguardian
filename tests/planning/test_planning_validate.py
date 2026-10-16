from dataclasses import replace

from plan_fixtures import all_days, day_ctx, rec

from planning.model import DayResult, Item
from planning.route import order_day
from planning.validate import validate


def result(*items):
    return DayResult(tuple(items), (), (), 0, 0, items[-1].end if items else 0)


def visit(pid, start, end):
    return Item("visit", start, end, place_id=pid, name=pid)


def kinds(violations):
    return sorted(v.kind for v in violations)


def run(cx, res, hard=(), anchors=(), budget=None, max_leg=None):
    return validate([cx], [res], list(hard), set(anchors), budget, max_leg)


def test_a_plan_the_scheduler_built_validly_passes():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)], start_node="h", end_node="h", extra_nodes=["h"])
    assert run(cx, order_day(["a", "b"], cx), anchors=["a"]) == []


def test_a_visit_outside_the_opening_hours_fails_even_if_the_scheduler_said_nothing():
    cx = day_ctx([rec("a", 1, 1, hours=all_days("08:00", "09:00"))])
    assert kinds(run(cx, result(visit("a", 600, 660)))) == ["hours"]


def test_a_place_closed_that_weekday_fails():
    cx = day_ctx([rec("a", 1, 1, hours={**all_days(), "mon": []})], weekday="mon")
    assert kinds(run(cx, result(visit("a", 600, 660)))) == ["hours"]


def test_a_sunset_place_visited_at_noon_fails_the_timed_check():
    cx = day_ctx([rec("a", 1, 1, features={"sunset_view": "present"})], sun=(360, 1050))
    assert kinds(run(cx, result(visit("a", 720, 780)))) == ["timed"]


def test_overlapping_items_fail():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)])
    v = run(cx, result(visit("a", 600, 660), visit("b", 650, 710)))
    assert kinds(v) == ["overlap"] and v[0].minutes == 10


def test_a_day_that_runs_past_its_end_or_starts_before_it_fails():
    cx = day_ctx([rec("a", 1, 1, hours=None)], start=480, end=700)      # no hours, so only the day window can fail
    assert kinds(run(cx, result(visit("a", 650, 750)))) == ["day_window"]
    assert kinds(run(cx, result(visit("a", 400, 460)))) == ["day_window"]


def test_a_travel_leg_shorter_than_the_travel_time_fails_and_one_over_the_limit_fails():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)], minutes=30)
    short = Item("travel", 600, 610, from_id="a", to_id="b", mode="motorbike")
    assert kinds(run(cx, result(short))) == ["travel"]
    exact = Item("travel", 600, 630, from_id="a", to_id="b", mode="motorbike")
    assert run(cx, result(exact)) == []
    assert kinds(run(cx, result(exact), max_leg=20)) == ["long_leg"]


def test_an_anchor_that_is_not_in_the_plan_fails():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)])
    v = run(cx, result(visit("a", 600, 660)), anchors=["a", "b"])
    assert [(x.kind, x.place_id) for x in v] == [("anchor", "b")]


def test_a_day_over_the_budget_fails_and_unknown_prices_are_not_counted():
    price = lambda n: {"min_vnd": n, "typical_vnd": n, "max_vnd": n}
    cx = day_ctx([rec("a", 1, 1, price=price(200000)), rec("b", 1, 1, price=price(150000)), rec("c", 1, 1)])
    res = result(visit("a", 600, 660), visit("b", 700, 760), visit("c", 800, 860))
    assert [(v.kind, v.minutes) for v in run(cx, res, budget=300000)] == [("budget", 50000)]
    assert run(cx, res, budget=400000) == []


def test_a_hard_filter_the_place_clearly_breaks_fails_and_a_physical_one_says_so():
    steep = rec("a", 1, 1, features={"steep_or_stairs": "present"})
    cx = day_ctx([steep])
    hard = [{"feature": "steep_or_stairs", "op": "ne", "value": "present", "unknown_policy": "exclude"}]
    v = run(cx, result(visit("a", 600, 660)), hard=hard)
    assert [(x.kind, x.physical) for x in v] == [("hard", True)]


def test_a_relaxed_filter_and_a_place_with_no_evidence_do_not_fail():
    hard = [{"feature": "steep_or_stairs", "op": "ne", "value": "present", "unknown_policy": "flag"}]
    unknown = day_ctx([rec("u", 1, 1)])
    assert run(unknown, result(visit("u", 600, 660)), hard=hard) == []
    steep = rec("a", 1, 1, features={"steep_or_stairs": "present"})
    relaxed = day_ctx([steep])
    relaxed.places["a"] = replace(relaxed.places["a"], relaxed=("steep_or_stairs",))
    assert run(relaxed, result(visit("a", 600, 660)), hard=hard) == []


def test_the_same_place_twice_fails_but_two_near_duplicates_the_user_kept_pass():
    # near duplicate = the same kind of place (PLACE_DECISION §9.1): a hint to keep one, never a reason to refuse
    cx = day_ctx([rec("a", 1, 1, dup=7), rec("b", 1, 1, dup=7)])
    assert kinds(run(cx, result(visit("a", 600, 660), visit("a", 700, 760)))) == ["duplicate"]
    assert run(cx, result(visit("a", 600, 660), visit("b", 700, 760))) == []


def test_a_non_physical_hard_filter_is_not_marked_physical():
    noisy = rec("a", 1, 1, features={"live_music": "present"})
    hard = [{"feature": "live_music", "op": "ne", "value": "present", "unknown_policy": "exclude"}]
    v = run(day_ctx([noisy]), result(visit("a", 1100, 1160)), hard=hard)
    assert [(x.kind, x.physical) for x in v] == [("hard", False)]


def test_diet_eq_rejects_a_meal_without_verified_options_but_allows_a_park():
    hard = [{"feature": "vegetarian_options", "op": "eq", "value": "yes", "unknown_policy": "exclude"}]
    for features in ({"vegetarian_options": "no"}, {}):
        meal = day_ctx([rec("meal", 1, 1, group="restaurant", usable=("meal",), features=features)])
        assert kinds(run(meal, result(visit("meal", 720, 750)), hard=hard)) == ["hard"]
    park = day_ctx([rec("park", 1, 1, group="nature")])
    assert run(park, result(visit("park", 600, 660)), hard=hard) == []


def test_unknown_ne_is_fail_closed_unless_user_chose_flag():
    hard = [{"feature": "noise", "op": "ne", "value": "loud", "unknown_policy": "exclude"}]
    cx = day_ctx([rec("unknown", 1, 1)])
    assert kinds(run(cx, result(visit("unknown", 600, 660)), hard=hard)) == ["hard"]
    hard[0]["unknown_policy"] = "flag"
    assert run(cx, result(visit("unknown", 600, 660)), hard=hard) == []


def test_required_meals_are_checked_from_visits_even_when_order_metadata_is_empty():
    cx = replace(day_ctx([rec("a", 1, 1)]), require_meals=True)
    violations = run(cx, result(visit("a", 600, 660)))
    assert {v.detail for v in violations if v.kind == "meal_missing"} == {
        "missing breakfast", "missing lunch", "missing dinner"}


def test_full_itinerary_rejects_a_visit_shorter_than_its_estimate_minimum():
    cx = replace(day_ctx([rec("a", 1, 1)]), require_meals=True)
    violations = run(cx, result(visit("a", 600, 610)))
    assert [(v.place_id, v.minutes) for v in violations if v.kind == "visit_duration"] == [("a", 20)]


def test_cached_validation_tracks_visit_estimates_without_order_metadata():
    cx = replace(day_ctx([rec("a", 1, 1)]), require_meals=True)
    res = result(visit("a", 600, 640))
    cache = {}
    before = validate([cx], [res], [], set(), None, None, day_cache=cache)
    assert not any(v.kind == "visit_duration" for v in before)
    changed = replace(cx, places={"a": replace(cx.places["a"], visit={"short": 60, "typical": 60, "long": 90})})
    actual = validate([changed], [res], [], set(), None, None, day_cache=cache)
    assert actual == run(changed, res)
    assert any(v.kind == "visit_duration" and v.minutes == 20 for v in actual)


def test_cached_validation_tracks_travel_endpoints_without_order_metadata():
    from plan_fixtures import flat_travel
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)], minutes=10)
    res = result(Item("travel", 600, 620, from_id="a", to_id="b", mode="motorbike"))
    cache = {}
    assert not validate([cx], [res], [], set(), None, None, day_cache=cache)
    changed = replace(cx, travel=flat_travel(["a", "b"], 30))
    actual = validate([changed], [res], [], set(), None, None, day_cache=cache)
    assert actual == run(changed, res)
    assert [(v.kind, v.minutes) for v in actual] == [("travel", 10)]
