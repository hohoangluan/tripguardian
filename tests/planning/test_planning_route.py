import pytest

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


def test_route_reuses_day_rules_across_candidate_orders(monkeypatch):
    from dataclasses import replace
    from itertools import permutations
    import planning.schedule as schedule
    import planning.timefit as timefit

    records = [rec("a", 1, 1, group="cafe"), rec("b", 1, 1, group="restaurant"),
               rec("c", 1, 1, hours=all_days("14:00", "20:00")), rec("d", 1, 1)]
    cx = day_ctx(records, start_node="h", end_node="h", extra_nodes=["h"])
    ids = [r["id"] for r in records]
    expected = replace(min((simulate(list(p), cx) for p in permutations(sorted(ids))), key=lambda r: r.key),
                       method="exact")
    calls = []
    original = timefit.windows_for

    def counted(place, ctx):
        calls.append(place.id)
        return original(place, ctx)

    monkeypatch.setattr(schedule, "windows_for", counted)
    monkeypatch.setattr(timefit, "windows_for", counted)
    actual = order_day(ids, cx)
    assert actual == expected
    assert len(calls) <= len(ids)


def test_route_cache_does_not_survive_a_context_change():
    from dataclasses import replace
    from itertools import permutations

    records = [rec("a", 1, 1, group="cafe"), rec("b", 1, 1), rec("c", 1, 1)]
    cx = day_ctx(records, start_node="h", end_node="h", extra_nodes=["h"])
    ids = [r["id"] for r in records]
    order_day(ids, cx)
    changed = replace(cx, day=replace(cx.day, start=840, end=1080),
                      time_preferences=({"place_id": "a", "period": "afternoon", "weight": 2},))
    expected = replace(min((simulate(list(p), changed) for p in permutations(sorted(ids))), key=lambda r: r.key),
                       method="exact")
    assert order_day(ids, changed) == expected


@pytest.mark.parametrize("weekday", ["mon", "tue", "wed", "thu", "fri", "sat", "sun"])
def test_cached_search_matches_full_simulation_on_each_weekday(weekday):
    from dataclasses import replace
    from itertools import permutations

    records = [rec("coffee", 1, 1, group="cafe", hours=None),
               rec("meal", 1, 1, group="restaurant", hours=all_days("11:00", "20:00")),
               rec("late", 1, 1, features={"live_music": "present"},
                   hours={d: [] if d == "wed" else [["18:30" if d == "tue" else "16:00", "21:00"]]
                          for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}),
               rec("view", 1, 1, features={"sunset_view": "present"}, status="UNCERTAIN"),
               rec("walk", 1, 1, group="garden_farm", visit=(20, 40, 60))]
    cx = day_ctx(records, weekday=weekday, start_node="h", end_node="h", extra_nodes=["h"],
                 sun=(360, 1050), rain=.8)
    cx = replace(cx, time_preferences=({"place_id": "coffee", "period": "afternoon", "weight": 2},))
    ids = [r["id"] for r in records]
    expected = replace(min((simulate(list(p), cx) for p in permutations(sorted(ids))), key=lambda r: r.key),
                       method="exact")
    assert order_day(ids, cx) == expected


def test_route_result_caches_obey_the_configured_memory_limit():
    from dataclasses import replace
    from itertools import permutations
    from planning.schedule import _SimulationCache

    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1), rec("c", 1, 1)],
                 start_node="h", end_node="h", extra_nodes=["h"])
    cx = replace(cx, cfg=replace(cx.cfg, cache_entries=2))
    cache = _SimulationCache(["a", "b", "c"], cx)
    for order in permutations(["a", "b", "c"]):
        assert simulate(list(order), cx, _cache=cache) == simulate(list(order), cx)
        assert len(cache.scores) <= 2
        assert len(cache.legs) <= 2


def test_a_simulation_cache_cannot_be_used_with_a_different_context():
    from dataclasses import replace
    from planning.schedule import _SimulationCache

    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)])
    cache = _SimulationCache(["a", "b"], cx)
    with pytest.raises(ValueError, match="another context"):
        simulate(["a", "b"], replace(cx, pace="slow"), _cache=cache)


def test_cached_heuristic_matches_uncached_search(monkeypatch):
    import planning.route as route

    records = [rec(f"p{i}", 1, 1, group="cafe" if i % 2 else "garden_farm",
                   hours=all_days("14:00", "20:00") if i == 3 else None, visit=(10, 20, 30))
               for i in range(8)]
    cx = day_ctx(records, start_node="h", end_node="h", extra_nodes=["h"], travel=line_travel(
        {"h": -1, **{r["id"]: (i * 7) % 8 for i, r in enumerate(records)}}, scale=3))
    ids = [r["id"] for r in records]
    with monkeypatch.context() as m:
        m.setattr(route, "_SimulationCache", lambda ids, ctx: None)
        expected = order_day(ids, cx)
    assert expected.method == "heuristic"
    assert order_day(ids, cx) == expected
