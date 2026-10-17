"""The memos of one plan (Trip.routes) answer only the question they were asked: a plan does not depend on how many
entries the memo holds or on which subset the overload search tried first (docs/PLANNING.md §Hiệu năng)."""

from dataclasses import replace

from plan_fixtures import CFG, decision, prepared, rec

from planning.build import _seed_key, schedule_trip
from planning.overload import plan_or_directions


def _trip(cache_entries: int, n: int = 9, days: int = 2):
    records = [rec(f"p{i}", 11.94 + 0.004 * (i % 3), 108.45 + 0.004 * (i // 3), visit=(60, 90, 120)) for i in range(n)]
    d = decision([r["id"] for r in records], days=days, leave_at="17:00")
    trip = prepared(d, records)
    return replace(trip, cfg=replace(trip.cfg, route_cache_entries=cache_entries), routes={})


def _shape(sched):
    return ([list(r.order) for r in sched.results], [r.travel_min for r in sched.results], list(sched.leftover),
            [(v.kind, v.day, v.place_id) for v in sched.violations])


def test_seed_key_tells_orders_apart_exactly_when_the_search_depends_on_them():
    trip = _trip(4096)
    cx = _route_ctx = trip.ctxs[0]
    limit = cx.cfg.realistic["seeded_exact_n"]
    few = [f"p{i}" for i in range(limit)]
    many = [f"p{i}" for i in range(limit + 1)]
    # up to seeded_exact_n stops every permutation is tried: the seed cannot matter, so the key ignores the order
    assert _seed_key(few, cx, few) == _seed_key(few[::-1], cx, few[::-1])
    # above it the search starts from the seed: another order of the same stops is another search
    assert _seed_key(many, cx, many) != _seed_key(many[::-1], cx, many[::-1])


def test_a_schedule_does_not_depend_on_the_size_of_the_route_memo():
    kept_sets = [None, {f"p{i}" for i in range(7)}, {f"p{i}" for i in range(2, 9)}]
    for kept in kept_sets:
        small, large = (_shape(schedule_trip(_trip(entries), kept=kept)) for entries in (1, 4096))
        assert small == large


def test_the_overload_directions_do_not_depend_on_the_size_of_the_route_memo():
    plans = []
    for entries in (1, 4096):
        out = plan_or_directions(_trip(entries, n=12, days=1))
        plans.append([(v["id"], v["kept"], v["compare"]["travel_min"]) for v in out["variants"]])
    assert plans[0] == plans[1]
