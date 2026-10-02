from plan_fixtures import all_days, day_ctx, flat_travel, line_travel, rec

from planning.route import order_day
from planning.schedule import simulate


def test_the_best_order_of_a_few_stops_is_found_by_trying_them_all():
    travel = flat_travel(["h", "a", "b", "c"], 10, h_b=20, h_c=30, a_c=20)      # h - a - b - c along a road
    cx = day_ctx([rec("c", 1, 1), rec("a", 1, 1), rec("b", 1, 1)], start_node="h", extra_nodes=["h"], travel=travel)
    r = order_day(["c", "a", "b"], cx)
    assert r.order == ("a", "b", "c") and r.method == "exact" and r.violations == ()


def test_a_place_that_opens_late_goes_last_even_though_it_is_close():
    late = rec("b", 1, 1, hours=all_days("15:00", "20:00"))
    cx = day_ctx([rec("a", 1, 1), late, rec("c", 1, 1)], start_node="h", extra_nodes=["h"])
    r = order_day(["a", "b", "c"], cx)
    assert r.order[-1] == "b" and r.violations == ()


def test_an_order_without_violations_beats_a_shorter_one_with_a_violation():
    morning_only = rec("a", 1, 1, hours=all_days("08:00", "10:00"))
    travel = flat_travel(["h", "a", "b"], 60, h_a=30, h_b=5)
    cx = day_ctx([morning_only, rec("b", 1, 1)], start_node="h", extra_nodes=["h"], travel=travel)
    assert simulate(["b", "a"], cx).end < simulate(["a", "b"], cx).end      # b first is quicker but misses a's hours
    r = order_day(["a", "b"], cx)
    assert r.order == ("a", "b") and r.violations == ()


def test_the_same_input_gives_the_same_order():
    recs = [rec(f"p{i}", 1, 1) for i in range(5)]
    cx = day_ctx(recs, start_node="h", extra_nodes=["h"], travel=line_travel(
        {"h": -1, "p0": 3, "p1": 0, "p2": 4, "p3": 1, "p4": 2}))
    first = order_day([r["id"] for r in recs], cx)
    assert order_day(list(reversed([r["id"] for r in recs])), cx) == first


def test_more_stops_than_exact_n_use_the_heuristic_and_still_place_every_stop_once():
    pos = {f"p{i}": (i * 7) % 8 for i in range(8)}                 # 8 stops in a scrambled order along a line
    recs = [rec(pid, 1, 1, visit=(10, 20, 30)) for pid in pos]
    cx = day_ctx(recs, start_node="h", extra_nodes=["h"], travel=line_travel({"h": -1, **pos}, scale=3))
    r = order_day(list(pos), cx)
    assert r.method == "heuristic" and sorted(r.order) == sorted(pos)
    assert list(r.order) == sorted(pos, key=pos.get)               # the line is walked end to end


def test_zero_and_one_stop_need_no_search():
    cx = day_ctx([rec("a", 1, 1)], start_node="h", extra_nodes=["h"])
    assert order_day([], cx).items == ()
    assert order_day(["a"], cx) == simulate(["a"], cx)
