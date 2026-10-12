"""Overload proposals retain the selection and explain three different priorities."""

import copy
from dataclasses import replace

from planning import build_variants
from plan_fixtures import CENTRE, CFG, FakeLive, decision, fake_matrix, fixed_sun, no_geocode, prepared, spot


def overloaded(*, days=1, count=8, roles=None):
    records = [spot(f"p{i}", CENTRE, i % 7, price={"typical_vnd": 200000 if i == 7 else 10000},
                    group=f"kind-{i % 4}") for i in range(count)]
    output = decision([r["id"] for r in records], days=days, roles=roles, leave_at="21:00")
    output["feasibility"] = {"status": "infeasible", "totals": {"needed": 1000 * days, "available": 600 * days},
                             "conflicts": [{"check": "time", "id": "time"}]}
    for chosen in output["confirmed"]:
        chosen["utility"] = 0.1 if chosen["id"] == "p7" else 1.0
        chosen["utility_source"] = "decision_score"
    return output, records


def run(output, records):
    return build_variants(output, records, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode,
                          matrix_fn=fake_matrix, sun_fn=fixed_sun)


def valid(out):
    return [v for v in out["variants"] if v.get("status") == "available"]


def test_overload_offers_three_explained_profiles_and_preserves_selection():
    output, records = overloaded(roles={"p0": "anchor", "p1": "locked"})
    original = copy.deepcopy(output)
    out = run(output, records)
    assert {v.get("preset") for v in out["variants"]} == {"low_cost", "diverse", "least_travel"}
    assert out["ok"] and valid(out)
    assert not out["keep_all"]["confirmable"] or out["keep_all"]["robustness"]["level"] == "fragile"
    for variant in valid(out):
        assert {"p0", "p1"} <= set(variant["kept"]) <= {r["id"] for r in records}
        assert variant["definition"] and variant["why"] and variant["dropped_by_plan"]
        assert variant["violations"] == []
        visits = [i["place_id"] for day in variant["itinerary"] for i in day["items"] if i["kind"] == "visit"]
        assert set(visits) == set(variant["kept"]) and len(visits) == len(set(visits))
    assert output == original
    assert out["overload"]["binding"]


def test_economical_can_drop_an_expensive_low_value_place_without_budget():
    output, records = overloaded(count=8)
    out = run(output, records)
    economical = next(v for v in out["variants"] if v.get("preset") == "low_cost")
    assert economical["status"] == "available"
    assert "p7" not in economical["kept"]
    assert economical["metrics"]["value_share"] >= 0.7
    assert economical["delta_vs_selection"]["cost_vnd"] < 0


def test_experience_keeps_full_visits_and_routing_counts_places_first():
    output, records = overloaded(count=8)
    out = run(output, records)
    experience = next(v for v in out["variants"] if v.get("preset") == "diverse")
    routing = next(v for v in out["variants"] if v.get("preset") == "least_travel")
    assert experience["status"] == "available"
    assert experience["metrics"]["duration_loss_min"] == 0
    assert experience["robustness"]["level"] in {"solid", "feasible"}
    assert routing["status"] == "available"
    assert routing["metrics"]["places"] >= experience["metrics"]["places"]


def test_unknown_prices_are_reported_and_do_not_become_free():
    output, records = overloaded(count=8)
    for rec in records:
        rec["operation"]["entry_fee"] = None
    economical = next(v for v in run(output, records)["variants"] if v.get("preset") == "low_cost")
    assert economical["metrics"]["cost_unknown"] == len(economical["kept"])
    assert economical["metrics"]["transport_cost_vnd"] is None
    assert economical["metrics"]["cost_basis"] == "partial"


def test_price_imputation_uses_only_the_same_kind_and_keeps_known_total_separate():
    output = decision(["known-low", "known-high", "unknown"], days=1, leave_at="21:00")
    records = [spot("known-low", CENTRE, 0, price={"typical_vnd": 10000}, group="museum"),
               spot("known-high", CENTRE, 1, price={"typical_vnd": 30000}, group="museum"),
               spot("unknown", CENTRE, 2, price=None, group="museum")]
    trip = prepared(output, records)
    from planning.build import schedule_trip
    from planning.composer import profile_metrics

    result = profile_metrics(trip, schedule_trip(trip))

    assert result["cost_vnd"] == 40000
    assert result["cost_unknown"] == 1
    assert result["estimated_cost_vnd"] == 60000
    assert result["cost_unestimated"] == 0


def test_economical_does_not_drop_a_place_when_directed_transport_cost_would_rise_more():
    records = [spot("a", CENTRE, 0, price={"typical_vnd": 10000}),
               spot("b", CENTRE, 10, price={"typical_vnd": 10000}),
               spot("bridge", CENTRE, 20, price={"typical_vnd": 200000})]
    output = decision([r["id"] for r in records], days=1, leave_at="21:00")
    output["feasibility"] = {"status": "partial", "totals": {"needed": 500, "available": 600},
                             "conflicts": [{"check": "time", "id": "time"}]}
    for chosen in output["confirmed"]:
        chosen["utility"] = 0.1 if chosen["id"] == "bridge" else 1.0

    ids_by_point = {(r["identity"]["lat"], r["identity"]["lng"]): r["id"] for r in records}

    def directed_matrix(points, mode, cfg):
        ids = [ids_by_point[tuple(point)] for point in points]
        minutes = [[0 if a == b else 1 if "bridge" in {a, b} else 500 for b in ids] for a in ids]
        return {"minutes": minutes, "source": "fixture", "fetched_at": "2026-10-11T00:00:00+00:00"}

    cfg = replace(CFG, composer={**CFG.composer, "transport_vnd_per_min": {"motorbike": 1000}})
    out = build_variants(output, records, cfg=cfg, live_cfg=FakeLive(), geocode_fn=no_geocode,
                         matrix_fn=directed_matrix, sun_fn=fixed_sun)
    economical = next(v for v in out["variants"] if v["preset"] == "low_cost")

    assert "bridge" in economical["kept"], economical["metrics"]
    assert economical["metrics"]["transport_cost_vnd"] is not None


def test_impossible_must_set_is_explained_instead_of_silently_trimmed():
    output, records = overloaded(count=8, roles={f"p{i}": "anchor" for i in range(8)})
    output["trip_context"]["context"]["leave_at"] = "10:00"
    out = run(output, records)
    assert not out["ok"]
    assert len(out["variants"]) == 3
    assert all(v["status"] == "unavailable" for v in out["variants"])
    assert all(set(v["kept"]) == {f"p{i}" for i in range(8)} for v in out["variants"])


def test_profiles_are_deterministic():
    output, records = overloaded(count=8)
    assert run(output, records) == run(output, records)


def test_long_trip_trims_dense_week_without_dropping_the_light_week():
    output, records = overloaded(days=14, count=51)
    output["chunk_assignments"] = {f"p{i}": 0 if i < 49 else 1 for i in range(51)}
    out = run(output, records)
    assert out["ok"]
    route = next(v for v in out["variants"] if v.get("preset") == "least_travel")
    assert route["status"] == "available"
    assert {"p49", "p50"} <= set(route["kept"])
    assert len(route["kept"]) < 51


def test_retained_value_denominator_includes_confirmed_places_without_serving_records():
    output = decision(["kept", "unplaced"], days=1, leave_at="21:00")
    output["feasibility"] = {"status": "infeasible", "totals": {"needed": 900, "available": 600},
                             "conflicts": [{"check": "time", "id": "time"}]}
    output["confirmed"][0]["utility"] = 10
    output["confirmed"][1]["utility"] = 90
    records = [spot("kept", CENTRE, 0)]
    out = run(output, records)
    economical = next(v for v in out["variants"] if v["preset"] == "low_cost")
    assert economical["metrics"]["value_share"] < 0.2
    assert economical["status"] == "unavailable"
    dropped = next(p for p in economical["dropped_by_plan"] if p["place_id"] == "unplaced")
    assert dropped["source"] == "data" and dropped["reason"] == "unplaced"
    assert economical["delta_vs_selection"]["cost_vnd"] is None


def test_timed_wish_is_unknown_without_sun_data_and_two_pins_do_not_share_one_window():
    output = decision(["sun"], days=1, start_date=None, leave_at="21:00")
    output["trip_context"]["soft_weights"] = [
        {"feature": "sunset_view", "value": "present", "context": None, "weight": 1},
        {"feature": "cloud_hunting", "value": "present", "context": None, "weight": 1},
    ]
    records = [spot("sun", CENTRE, 0, hours=None,
                    features={"sunset_view": "present", "cloud_hunting": "present"})]
    trip = prepared(output, records)
    from planning.build import schedule_trip
    from planning.composer import _wishes
    sched = schedule_trip(trip, allow_shrink=False)
    wishes = _wishes(trip, sched)
    assert wishes["met"] == []
    assert {w["feature"] for w in wishes["unknown"]} == {"sunset_view", "cloud_hunting"}


def test_unpinned_sunset_wish_is_not_counted_as_met():
    output = decision(["sun"], days=1, leave_at="21:00")
    output["trip_context"]["soft_weights"] = [
        {"feature": "sunset_view", "value": "present", "context": None, "weight": 1},
    ]
    records = [spot("sun", CENTRE, 0, features={"sunset_view": "present"})]
    trip = prepared(output, records)
    from planning.build import schedule_trip
    from planning.composer import _wishes
    sched = schedule_trip(trip, allow_shrink=False)
    unpinned_ctx = replace(sched.ctxs[0], places={"sun": replace(sched.ctxs[0].places["sun"], pins=())})
    unpinned_result = replace(sched.results[0], unpinned=("sun",))
    sched = replace(sched, ctxs=[unpinned_ctx], results=[unpinned_result])
    wishes = _wishes(trip, sched)
    assert wishes["met"] == []
    assert wishes["unmet"] == [{"feature": "sunset_view", "value": "present"}]


def test_one_visit_with_sun_data_cannot_satisfy_both_sunrise_and_sunset():
    from planning.build import schedule_trip
    from planning.composer import _wishes
    output = decision(['sun'], days=1, arrive_at='05:00', leave_at='21:00')
    output['trip_context']['soft_weights'] = [
        {'feature': f, 'value': 'present', 'context': None, 'weight': 1}
        for f in ('sunset_view', 'cloud_hunting')]
    trip = prepared(output, [spot('sun', CENTRE, 0, hours=None,
                    features={'sunset_view': 'present', 'cloud_hunting': 'present'})])
    sched = schedule_trip(trip, allow_shrink=False)
    assert sched.ctxs[0].sun == (360, 1050)
    wishes = _wishes(trip, sched)
    assert len(wishes['met']) == 1
    assert len(wishes['unmet']) == 1
    assert not wishes['unknown']


def test_98_places_over_14_days_offer_valid_trimmed_plan_without_duplicate_visits():
    output, records = overloaded(days=14, count=98, roles={'p0': 'anchor'})
    output['chunk_assignments'] = {f'p{i}': i // 49 for i in range(98)}
    out = run(output, records)
    assert out['ok']
    assert not out['keep_all']['confirmable'] or out['keep_all']['robustness']['level'] == 'fragile'
    for v in valid(out):
        ids = [it['place_id'] for d in v['itinerary'] for it in d['items'] if it['kind'] == 'visit']
        assert 'p0' in ids
        assert len(ids) == len(set(ids)) < 98
        assert not v['violations']
