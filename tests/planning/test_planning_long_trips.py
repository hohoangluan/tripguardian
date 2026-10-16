"""Weekly allocation, absolute trip boundaries and local edit reuse."""

from collections import Counter

from plan_fixtures import CFG, FakeLive, decision, fake_matrix, fixed_sun, no_geocode, rec

from planning.build import prepare, schedule_trip
from planning.engine import Engine
from planning.session import Store


def inputs(n=8):
    records = [rec(str(i), 11.94 + i * 0.0001, 108.44) for i in range(n)]
    d = decision([r["id"] for r in records], days=14)
    d["chunk_assignments"] = {str(i): i % 2 for i in range(n)}
    return d, records


def prepare_trip(d, records):
    return prepare(d, records, CFG, FakeLive(), no_geocode, fake_matrix, fixed_sun)


def test_visits_stay_in_assigned_weeks_and_trip_boundaries_remain_absolute():
    d, records = inputs()
    trip = prepare_trip(d, records)
    schedule = schedule_trip(trip)
    assert not schedule.violations
    placed = Counter()
    for index, ids in enumerate(schedule.per_day):
        for pid in ids:
            assert index // 7 == d["chunk_assignments"][pid]
            placed[pid] += 1
    assert placed == Counter({r["id"]: 1 for r in records})
    assert trip.days[6].end == CFG.day_end
    assert trip.days[7].start == CFG.day_start
    assert trip.days[13].end == CFG.leave_at
    assert trip.days[7].date > trip.days[6].date


def test_long_routes_have_a_small_exact_bound_but_week_trips_keep_existing_bound():
    d, records = inputs()
    assert prepare_trip(d, records).cfg.exact_n == 5
    d["trip_context"]["context"]["days"] = 7
    d["chunk_assignments"] = {r["id"]: 0 for r in records}
    assert prepare_trip(d, records).cfg.exact_n == CFG.exact_n


def test_cross_week_edit_recomputes_only_source_and_destination_days(monkeypatch):
    import planning.engine as engine_module

    d, records = inputs()
    matrix_calls = []
    eng = Engine(records, cfg=CFG, live_cfg=FakeLive(), store=Store(None), background=False,
                 geocode_fn=no_geocode, matrix_fn=lambda *a: (matrix_calls.append(1) or fake_matrix(*a)),
                 sun_fn=fixed_sun)
    created = eng.create(d, None)
    sid = created["id"]
    eng.act(sid, {"type": "pick_variant", "id": created["view"]["variants"][0]["id"]})
    s = eng.store.get(sid)
    base = eng._ensure_base(sid)
    original = eng._active_itinerary(s, base)["results"]
    src = next(i for i, r in enumerate(original) if r.order)
    pid = original[src].order[0]
    dest = 7 if src < 7 else 0
    calls = []
    # Spec §8: move_place inserts where it costs least and retimes the source day (Engine._quick_order), with no
    # repair search; only those two days are laid out again.
    quick = engine_module.Engine._quick_order
    monkeypatch.setattr(engine_module.Engine, "_quick_order", staticmethod(lambda ids, prev, cx, *a:
                        (calls.append(cx.day.index) or quick(ids, prev, cx, *a))))
    out = eng.act(sid, {"type": "move_place", "place": pid, "day": dest})
    current = eng._active_itinerary(s, base)["results"]
    assert set(calls) == {src, dest}
    assert all(current[i] is original[i] for i in range(14) if i not in (src, dest))
    assert len(matrix_calls) == 1
    assert out["view"]["chunk_assignments"][pid] == dest // 7
    assert out["view"]["chunks"][dest // 7]["places"]
    assert out["diff"]["affected_chunks"] == [0, 1]


def test_dense_week_reports_what_does_not_fit_instead_of_running_past_the_days():
    d, records = inputs(98)
    records = [{**r, "operation": {**r["operation"], "visit_minutes": {
        **r["operation"]["visit_minutes"], "short": 120, "typical": 180, "long": 240}}} for r in records]
    schedule = schedule_trip(prepare_trip(d, records))
    assert not any(v.kind == "day_window" for v in schedule.violations)
    placed = [pid for ids in schedule.per_day for pid in ids]
    assert schedule.leftover and sorted(placed + list(schedule.leftover)) == sorted(r["id"] for r in records)


def test_daily_budget_remains_per_person_per_day_across_weeks():
    from planning.schedule import simulate
    from planning.validate import validate

    d, records = inputs(2)
    d["trip_context"]["context"]["budget_vnd"] = 150000
    records = [{**r, "operation": {**r["operation"], "entry_fee": {"typical_vnd": 100000}}} for r in records]
    trip = prepare_trip(d, records)
    results = [simulate(["0"] if i == 0 else ["1"] if i == 7 else [], cx) for i, cx in enumerate(trip.ctxs)]
    assert not validate(trip.ctxs, results, [], set(), 150000, None)
    assert not validate(trip.ctxs, results, [], set(), 150000, None, day_cache={})
    results[0] = simulate([], trip.ctxs[0])
    results[7] = simulate(["0", "1"], trip.ctxs[7])
    assert any(v.kind == "budget" for v in validate(trip.ctxs, results, [], set(), 150000, None))


def test_legacy_output_without_week_assignments_is_placed_once():
    d, records = inputs()
    d.pop("chunk_assignments")
    schedule = schedule_trip(prepare_trip(d, records))
    assert Counter(pid for ids in schedule.per_day for pid in ids) == Counter({r["id"]: 1 for r in records})


def test_legacy_week_allocation_is_shared_across_objectives_and_home_variants(monkeypatch):
    import planning.build as build

    d, records = inputs()
    d.pop("chunk_assignments")
    trip = prepare_trip(d, records)
    coarse_weights = []
    assign = build.assign

    def counted_assign(trip_, ctxs, ids):
        if len(ctxs) > trip.cfg.chunk_days:
            coarse_weights.append(dict(ctxs[0].cfg.weights))
        return assign(trip_, ctxs, ids)

    monkeypatch.setattr(build, "assign", counted_assign)
    schedules = [
        schedule_trip(trip, {key: 1000 for key in trip.cfg.weights}),
        schedule_trip(trip, {key: 0 for key in trip.cfg.weights}),
        schedule_trip(build.with_home(trip, None), {key: 500 for key in trip.cfg.weights}),
    ]
    assert coarse_weights == [trip.cfg.weights]
    mappings = [{pid: index // 7 for index, ids in enumerate(s.per_day) for pid in ids} for s in schedules]
    assert mappings[0] == mappings[1] == mappings[2]
    for schedule in schedules:
        assert Counter(pid for ids in schedule.per_day for pid in ids) == Counter({r["id"]: 1 for r in records})


def test_prepared_week_allocation_copies_explicit_decision_mapping():
    d, records = inputs()
    trip = prepare_trip(d, records)
    d["chunk_assignments"]["0"] = 1
    schedule = schedule_trip(trip)
    assert next(index // 7 for index, ids in enumerate(schedule.per_day) if "0" in ids) == 0
