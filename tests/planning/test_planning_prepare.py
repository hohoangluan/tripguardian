from plan_fixtures import CENTRE, SOUTH, prepared, sample_trip

from corpus.ontology import load as load_ontology

import planning.build as build_module
from planning.build import schedule_trip, with_home


def test_each_day_gets_the_rain_of_its_date_and_a_date_the_forecast_lacks_stays_unknown():
    d, recs = sample_trip(days=3)
    trip = prepared(d, recs, weather={"2026-12-12": {"rain_prob": 0.7}, "2026-12-13": {"rain_prob": None},
                                      "2027-01-01": {"rain_prob": 1.0}})
    assert [cx.rain for cx in trip.ctxs] == [0.7, None, None]


def test_without_dates_or_a_forecast_no_day_has_rain():
    d, recs = sample_trip(start_date=None, days=None)
    assert all(cx.rain is None for cx in prepared(d, recs, weather={"2026-12-12": {"rain_prob": 0.9}}).ctxs)
    d, recs = sample_trip()
    assert all(cx.rain is None for cx in prepared(d, recs).ctxs)


def test_every_day_knows_how_much_the_trip_wants_each_place():
    d, recs = sample_trip()
    d["trip_context"]["soft_weights"] = [{"feature": "scenic_view", "value": "present", "context": None, "weight": 1}]
    recs[0]["experience"]["scenic_view"] = {"value": "present", "distribution": {"present": 3}, "status": "VERIFIED",
                                            "n": 3}
    prefs = prepared(d, recs).ctxs[0].prefs
    assert prefs["c1"] == 1.0 and prefs["c2"] == 0.0


def test_a_place_known_for_two_times_of_day_keeps_only_the_one_the_user_wants():
    d, recs = sample_trip()
    for fid in ("sunset_view", "cloud_hunting"):
        recs[0].setdefault(load_ontology().features[fid].group, {})[fid] = {
            "value": "present", "distribution": {"present": 3}, "status": "VERIFIED", "n": 3}
    assert prepared(d, recs).by_place["c1"].pins == ("sunset_view", "cloud_hunting")
    d["trip_context"]["soft_weights"] = [{"feature": "cloud_hunting", "value": "present", "context": None, "weight": 1}]
    assert prepared(d, recs).by_place["c1"].pins == ("cloud_hunting",)


def test_a_day_seen_before_is_not_ordered_again(monkeypatch):
    d, recs = sample_trip()
    trip = prepared(d, recs)
    calls, real = [], build_module.order_day
    monkeypatch.setattr(build_module, "order_day", lambda ids, cx: calls.append(1) or real(ids, cx))
    first = schedule_trip(trip)
    again = schedule_trip(trip, {"travel": 2.0})
    assert len(calls) == 2 and first.per_day == again.per_day and first.results == again.results


def test_objective_weights_reach_the_day_split_but_not_the_shared_days():
    d, recs = sample_trip()
    trip = prepared(d, recs)
    s = schedule_trip(trip, {"repeat": 40.0})
    assert s.ctxs[0].cfg.weights["repeat"] == 40.0 and "repeat" not in trip.ctxs[0].cfg.weights


def test_extra_nodes_join_the_one_travel_matrix_and_are_not_otherwise_placed():
    d, recs = sample_trip()
    trip = prepared(d, recs, extra_nodes={"h1": (CENTRE[0] + 0.001, CENTRE[1])})
    assert "h1" in trip.travel.ids and "h1" not in trip.by_place
    assert trip.lodging_ids == ("h1",)


def test_with_home_changes_only_where_the_day_starts_and_ends():
    d, recs = sample_trip()
    trip = prepared(d, recs, extra_nodes={"h1": (SOUTH[0], SOUTH[1])})
    swapped = with_home(trip, "h1")
    assert swapped.days[0].start_node == "h1" and trip.days[0].start_node != "h1"
    assert swapped.ctxs[0].rain == trip.ctxs[0].rain and swapped.travel is trip.travel


def test_order_is_cached_separately_per_home():
    d, recs = sample_trip()
    trip = prepared(d, recs, extra_nodes={"h1": (SOUTH[0], SOUTH[1])})
    schedule_trip(trip)
    n = len(trip.routes)
    schedule_trip(with_home(trip, "h1"))
    assert len(trip.routes) > n  # a different start node is a different cache key, not reused
