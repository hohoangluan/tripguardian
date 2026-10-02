from plan_fixtures import CFG, all_days, day_ctx, line_travel, rec

from planning.days import assign_days, blocked, day_cost, load_of


def two_days(recs, positions, weekdays=("mon", "tue")):
    """Two DayCtx over the same places and travel, one per weekday."""
    travel = line_travel(positions)
    return [day_ctx(recs, weekday=wd, travel=travel) for wd in weekdays]


def test_two_far_apart_clusters_go_on_separate_days():
    pos = {"a1": 0, "a2": 1, "a3": 2, "b1": 100, "b2": 101, "b3": 102}
    recs = [rec(i, 1, 1) for i in pos]
    out, flag = assign_days([["a1", "a2", "a3"], ["b1", "b2", "b3"]], two_days(recs, pos))
    assert flag is None and sorted(map(sorted, out)) == [["a1", "a2", "a3"], ["b1", "b2", "b3"]]


def test_a_cluster_with_a_place_closed_that_day_moves_to_the_other_day():
    pos = {"a1": 0, "a2": 1, "a3": 2, "b1": 3, "b2": 4, "b3": 5}
    shut_mon = {**all_days(), "mon": []}
    recs = [rec("a1", 1, 1, hours=shut_mon), rec("a2", 1, 1), rec("a3", 1, 1),
            rec("b1", 1, 1), rec("b2", 1, 1), rec("b3", 1, 1)]
    out, _ = assign_days([["a1", "a2", "a3"], ["b1", "b2", "b3"]], two_days(recs, pos))
    assert out == [["b1", "b2", "b3"], ["a1", "a2", "a3"]]


def test_a_place_is_blocked_on_a_day_it_is_closed_or_only_opens_after_the_day_ends():
    evening = rec("e", 1, 1, hours=all_days("18:00", "22:00"))
    shut = rec("s", 1, 1, hours={**all_days(), "mon": []})
    fine = rec("f", 1, 1)
    short_day = day_ctx([evening, shut, fine], weekday="mon", end=900)
    assert blocked(["e", "s", "f"], short_day) == 2
    assert blocked(["e", "s", "f"], day_ctx([evening, shut, fine], weekday="tue")) == 0
    assert blocked(["e"], day_ctx([rec("n", 1, 1, hours=None), evening], weekday="mon", end=900)) == 1


def test_a_cluster_with_an_evening_only_place_never_goes_on_a_day_that_ends_before_it_opens():
    pos = {"e1": 0, "e2": 1, "x1": 50, "x2": 51}
    evening = all_days("18:00", "22:00")
    recs = [rec("e1", 1, 1, hours=evening), rec("e2", 1, 1), rec("x1", 1, 1), rec("x2", 1, 1)]
    travel = line_travel(pos)
    ctxs = [day_ctx(recs, weekday="mon", end=900, travel=travel), day_ctx(recs, weekday="tue", travel=travel)]
    out, _ = assign_days([["e1", "e2"], ["x1", "x2"]], ctxs)
    assert "e1" in out[1]


def test_the_greedy_fallback_also_keeps_a_place_off_a_day_it_cannot_use():
    pos = {f"p{i}": i * 50 for i in range(9)}
    recs = [rec(i, 1, 1, hours=all_days("18:00", "22:00") if i == "p0" else "open") for i in pos]
    travel = line_travel(pos)
    ctxs = [day_ctx(recs, weekday="mon", end=900, travel=travel), day_ctx(recs, weekday="tue", travel=travel)]
    out, flag = assign_days([[i] for i in pos], ctxs)
    assert flag == "days_fallback" and "p0" in out[1]


def test_a_day_that_cannot_hold_its_load_costs_more():
    pos = {f"p{i}": i for i in range(6)}
    recs = [rec(i, 1, 1, visit=(120, 180, 240)) for i in pos]
    cx = day_ctx(recs, travel=line_travel(pos))
    assert day_cost(list(pos)[:2], cx) < day_cost(list(pos), cx)


def test_the_planned_count_per_day_follows_the_pace():
    recs = [rec(f"p{i}", 1, 1) for i in range(3)]
    slow, packed = day_ctx(recs, pace="slow"), day_ctx(recs, pace="packed")
    ids = ["p0", "p1", "p2"]
    assert day_cost(ids, slow) < day_cost(ids, packed)       # three places is the slow target and under the packed one


def test_no_clusters_means_empty_days():
    cx = day_ctx([rec("a", 1, 1)])
    assert assign_days([], [cx, cx]) == ([[], []], None)


def test_the_same_input_always_gives_the_same_split():
    pos = {f"p{i}": i * 3 for i in range(6)}
    recs = [rec(i, 1, 1) for i in pos]
    clusters = [["p0", "p1"], ["p2", "p3"], ["p4", "p5"]]
    ctxs = two_days(recs, pos)
    assert assign_days(clusters, ctxs) == assign_days(clusters, ctxs)


def test_more_clusters_than_max_clusters_falls_back_to_greedy_and_says_so():
    pos = {f"p{i}": i * 50 for i in range(9)}
    recs = [rec(i, 1, 1) for i in pos]
    out, flag = assign_days([[i] for i in pos], two_days(recs, pos))
    assert flag == "days_fallback" and sorted(i for d in out for i in d) == sorted(pos)
    assert abs(len(out[0]) - len(out[1])) <= 1


def test_load_is_visit_minutes_by_pace_plus_the_moves_inside_the_cluster():
    cx = day_ctx([rec("a", 1, 1, visit=(10, 20, 30))])
    assert load_of(["a"], cx.places, CFG, "slow") == 30 + CFG.intra_leg_min
    assert load_of(["a"], cx.places, CFG, "packed") == 10 + CFG.intra_leg_min
