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


def test_overload_offers_drop_directions_and_preserves_selection():
    output, records = overloaded(roles={"p0": "anchor", "p1": "locked"})
    original = copy.deepcopy(output)
    out = run(output, records)
    assert {d for v in out["variants"] for d in [v["id"], *v.get("merged", [])]} == {"fit", "travel", "cost"}
    assert out["ok"] and valid(out)
    assert out["keep_all"] is None and out["overload"]
    for variant in valid(out):
        assert {"p0", "p1"} <= set(variant["kept"]) <= {r["id"] for r in records}
        assert variant["label"] and variant["gain"] and variant["dropped"]
        assert variant["violations"] == []
        visits = [i["place_id"] for day in variant["itinerary"] for i in day["items"] if i["kind"] == "visit"]
        assert set(visits) == set(variant["kept"]) and len(visits) == len(set(visits))
    assert output == original
    assert out["overload"]["missing_min"] > 0


def test_economical_can_drop_an_expensive_low_value_place_without_budget():
    output, records = overloaded(count=8)
    out = run(output, records)
    economical = next(v for v in out["variants"] if "cost" in [v["id"], *v.get("merged", [])])
    assert economical["status"] == "available"
    assert "p7" not in economical["kept"]
    assert economical["dropped"][0]["place_id"] == "p7"
    assert economical["compare"]["cost_known_vnd"] < sum(r["operation"]["entry_fee"]["typical_vnd"] for r in records)


def test_unknown_prices_are_reported_and_do_not_become_free():
    output, records = overloaded(count=8)
    for rec in records:
        rec["operation"]["entry_fee"] = None
    economical = next(v for v in run(output, records)["variants"] if "cost" in [v["id"], *v.get("merged", [])])
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


def test_impossible_must_set_is_explained_instead_of_silently_trimmed():
    output, records = overloaded(count=8, roles={f"p{i}": "anchor" for i in range(8)})
    output["trip_context"]["context"]["leave_at"] = "10:00"
    out = run(output, records)
    assert not out["ok"]
    assert len(out["variants"]) == 1
    assert set(out["variants"][0]["merged"]) == {"travel", "cost"}
    assert all(v["status"] == "unavailable" for v in out["variants"])
    assert all(set(v["kept"]) == {f"p{i}" for i in range(8)} for v in out["variants"])


def test_plan_cards_are_deterministic():
    output, records = overloaded(count=8)
    assert run(output, records) == run(output, records)


def test_fitting_dense_week_keeps_every_pick_in_both_weeks():
    output, records = overloaded(days=14, count=51)
    output["chunk_assignments"] = {f"p{i}": 0 if i < 49 else 1 for i in range(51)}
    out = run(output, records)
    assert out["ok"]
    route, = out["variants"]
    assert route["id"] == "main" and out["overload"] is None
    assert route["status"] == "available"
    assert {"p49", "p50"} <= set(route["kept"])
    assert len(route["kept"]) == 51


def test_retained_value_denominator_includes_confirmed_places_without_serving_records():
    output = decision(["kept", "unplaced"], days=1, leave_at="21:00")
    output['confirmed'][0]['utility'] = 10
    output['confirmed'][1]['utility'] = 90
    records = [spot('kept', CENTRE, 0)]
    out = run(output, records)
    main, = out['variants']
    assert main['id'] == 'main' and main['metrics']['value_share'] == 0.1
    assert main['compare']['fit'] == 0.1
    assert not out['overload']
    assert any(u['id'] == 'unplaced' for u in out['unplaced'])


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


def test_98_fitting_places_have_one_main_plan_without_duplicate_visits():
    output, records = overloaded(days=14, count=98, roles={'p0': 'anchor'})
    output['chunk_assignments'] = {f'p{i}': i // 49 for i in range(98)}
    out = run(output, records)
    assert out['ok']
    assert out['keep_all'] is None and out['overload'] is None
    assert [v['id'] for v in out['variants']] == ['main']
    for v in valid(out):
        ids = [it['place_id'] for d in v['itinerary'] for it in d['items'] if it['kind'] == 'visit']
        assert 'p0' in ids
        assert len(ids) == len(set(ids)) == 98
        assert not v['violations']
