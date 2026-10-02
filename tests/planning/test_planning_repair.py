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


def test_key_folds_the_diff_penalty_into_a_comparable_scalar_not_a_tie_break_only():
    # same violations and missed-meals, but r1 ends 2 minutes earlier than r2; r1 disagrees with the previous
    # order (diff=1), r2 matches it (diff=0). A real penalty must be able to outweigh a small end-time gap --
    # not just break an exact tie, which is all the old tuple-position design could ever do (tuple comparison
    # short-circuits at the first unequal element, so a 4th "weight*diff" slot is never reached once end differs).
    from planning.model import DayResult
    from planning.repair import _key
    r1 = DayResult((), ("b", "a"), (), 0, 0, 100)
    r2 = DayResult((), ("a", "b"), (), 0, 0, 102)
    prev = ("a", "b")
    assert _key(r1, prev, 0.0) < _key(r2, prev, 0.0)      # no penalty: the strictly earlier end wins
    assert _key(r2, prev, 5.0) < _key(r1, prev, 5.0)      # a real penalty: matching the previous order wins


def test_repair_error_is_an_action_error_so_the_server_maps_it_to_400():
    from planning.session import ActionError
    assert issubclass(RepairError, ActionError)
