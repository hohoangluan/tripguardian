from dataclasses import replace

import pytest
from plan_fixtures import CFG, day_ctx, rec

from planning.repair import RepairError, repair_day


def test_with_no_history_repair_day_matches_a_fresh_order_day():
    from planning.route import order_day
    recs = [rec("a", 1, 1), rec("b", 2, 2), rec("c", 3, 1)]
    cx = day_ctx(recs)
    assert repair_day(["a", "b", "c"], cx, None, set(), CFG).order == order_day(["a", "b", "c"], cx).order


def test_among_equally_good_orders_the_one_closest_to_the_previous_version_wins():
    # a, b, c sit on a line 5 apart; "b, a, c" and "a, b, c" tour the same total distance from the start node,
    # but only "a, b, c" keeps a and b (both present before) in their previous relative order.
    recs = [rec("a", 1, 1), rec("b", 1, 1), rec("c", 1, 1)]
    from plan_fixtures import line_travel
    cx = day_ctx(recs, travel=line_travel({"a": 0, "b": 5, "c": 10}, scale=1), start_node=None, end_node=None)
    r = repair_day(["a", "b", "c"], cx, ("a", "b"), set(), CFG)
    assert r.order == ("a", "b", "c")


def test_a_brand_new_stop_added_to_an_old_day_costs_no_penalty_for_being_new():
    recs = [rec("a", 1, 1), rec("b", 1, 1), rec("new", 1, 1)]
    cx = day_ctx(recs)
    r = repair_day(["a", "b", "new"], cx, ("a", "b"), set(), CFG)
    assert {"a", "b"}.issubset(set(r.order)) and set(r.order) == {"a", "b", "new"}
    # a still comes before b: the one thing the previous version promised is kept
    assert r.order.index("a") < r.order.index("b")


def test_a_locked_place_leaving_its_day_is_refused():
    recs = [rec("a", 1, 1), rec("b", 1, 1)]
    cx = day_ctx(recs)
    with pytest.raises(RepairError):
        repair_day(["b"], cx, ("a", "b"), {"a"}, CFG)


def test_a_locked_place_that_stays_in_the_day_is_not_refused():
    recs = [rec("a", 1, 1), rec("b", 1, 1), rec("c", 1, 1)]
    cx = day_ctx(recs)
    repair_day(["a", "b", "c"], cx, ("a", "b"), {"a"}, CFG)   # no raise


def test_more_than_exact_n_stops_still_seeds_from_the_previous_order():
    small_exact_n = replace(CFG, exact_n=2)
    recs = [rec(p, i, i) for i, p in enumerate(["a", "b", "c", "d"])]
    cx = day_ctx(recs)
    r = repair_day(["a", "b", "c", "d"], cx, ("d", "c", "b", "a"), set(), small_exact_n)
    assert set(r.order) == {"a", "b", "c", "d"} and not r.violations
