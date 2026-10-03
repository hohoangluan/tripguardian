import pytest

from planning import evaluate as ev
from plan_fixtures import rec


def test_trips_loads_the_shared_eval_trips_yaml():
    t = ev.trips()
    assert len(t) >= 10 and all({"id", "role", "hard", "soft"} <= set(x) for x in t)


def test_search_input_from_a_hidden_trip():
    si = ev.search_input({"id": "x", "role": "experience", "hard": {}, "soft": {"scenic_view": 1.0}}, version=1)
    assert si.soft_weights[0].feature == "scenic_view" and si.context.days == 3


def test_decision_outputs_keeps_a_confirmed_trip_with_no_places_so_it_counts_in_the_denominator(monkeypatch):
    # Place Decision confirms an empty shortlist as "feasible" (verified on serving data): such a trip is kept, so
    # plan_results reports it as not ok and it lowers feasible_itinerary_rate instead of silently disappearing.
    monkeypatch.setattr(ev, "trips", lambda: [
        {"id": "nothing_matches", "role": "experience", "hard": {"kids": "unsuitable"}, "soft": {}}])
    a = rec("A", 10.0, 106.0, usable=("meal",))  # no "experience" record exists -> Decision cannot fill any experience role
    a["provenance"] = {"as_of": "2026-09-30", "coverage": {}, "voices": 30, "rating_trend": None, "inputs": []}
    out = ev.decision_outputs([a])
    assert [tid for tid, _ in out] == ["nothing_matches"] and out[0][1]["confirmed"] == []


from plan_fixtures import CFG, FakeLive, decision, fake_lodging, fake_matrix, no_geocode, sample_trip  # noqa: E402


def fake_route(points, mode, live_cfg):
    return {"points": [list(q) for q in points], "source": "osrm", "fetched_at": "t"}


def test_plan_results_measures_a_confirmable_decision_output():
    d, recs = sample_trip(budget=5_000_000)
    row = ev.plan_results(d, recs, planning_cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode,
                          matrix_fn=fake_matrix, sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging,
                          route_fn=fake_route)
    # Not asserted: travel_min <= baseline_travel_min. The chosen order minimises the full day objective (waits, time
    # windows), not travel alone, so on some trips it is longer than pure nearest-neighbour; evaluate reports that as is.
    assert row["ok"] and row["baseline_travel_min"] >= 0 and row["travel_min"] >= 0
    assert row["robustness"] in ("solid", "feasible", "fragile")
    assert row["ms_variants"] >= 0 and row["ms_total"] >= row["ms_variants"]
    assert row["lodging_saved_min_per_day"] >= 0  # the best candidate is never worse than no lodging at all


def test_plan_results_reports_not_ok_for_a_decision_output_with_no_places():
    row = ev.plan_results(decision([]), [], planning_cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode,
                          matrix_fn=fake_matrix, sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging)
    assert row["ok"] is False and row["reason"] == "no_confirmed_places"


def test_plan_results_reports_not_ok_when_nothing_is_scheduled():
    d = decision(["ghost"])  # confirmed id absent from the records: Planning reports ok but schedules no visit
    row = ev.plan_results(d, [], planning_cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                          sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, route_fn=fake_route)
    assert row["ok"] is False and row["reason"] == "no_visits"


def test_evaluate_summarizes_every_confirmable_trip(monkeypatch):
    d, recs = sample_trip(budget=5_000_000)
    monkeypatch.setattr(ev, "decision_outputs", lambda records, cfg=None: [("t1", d), ("t2", d)])
    res = ev.evaluate(recs, planning_cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                      sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, route_fn=fake_route)
    assert res["summary"]["trips"] == 2 and res["summary"]["ok"] == 2
    assert res["summary"]["avg_saved_vs_baseline_pct"] <= 100
    assert set(res["summary"]["robustness"]) == {"solid", "feasible", "fragile"}
    assert len(res["trips"]) == 2 and res["trips"][0]["trip"] == "t1"


def test_evaluate_lists_not_ok_trips_with_their_reason(monkeypatch):
    monkeypatch.setattr(ev, "decision_outputs", lambda records, cfg=None: [("empty", decision([]))])
    res = ev.evaluate([], planning_cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                      sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, route_fn=fake_route)
    assert res["summary"]["feasible_itinerary_rate"] == 0.0
    assert res["summary"]["not_ok_trips"] == [{"trip": "empty", "reason": "no_confirmed_places"}]


def test_cli_evaluate_dispatches_to_run_without_reading_a_decision_output(monkeypatch):
    from planning import __main__ as cli
    called = []
    monkeypatch.setattr(ev, "run", lambda: called.append(True) or {})
    assert cli.main(["evaluate"]) == 0 and called == [True]
