from plan_fixtures import prepared, sample_trip

from live import Unavailable
from planning.objectives import metrics as compute_metrics
from planning.output import build, cost, route_of_day


def fake_route_ok(points, mode, live_cfg):
    return {"points": [list(p) for p in points], "source": "osrm", "fetched_at": "t"}


def fake_route_down(points, mode, live_cfg):
    raise Unavailable("osrm down")


def test_route_of_day_asks_for_the_days_visited_points_in_order():
    seen = []

    def fake(points, mode, live_cfg):
        seen.append(points)
        return fake_route_ok(points, mode, live_cfg)

    from planning.model import Day, DayResult, Item
    day = Day(0, None, None, 480, 1260, "@entry", "@exit")
    r = DayResult((Item("visit", 500, 530, place_id="a"), Item("visit", 600, 630, place_id="b")), ("a", "b"), (), 0, 0, 630)
    coords = {"@entry": (1.0, 1.0), "a": (1.1, 1.1), "b": (1.2, 1.2), "@exit": (1.3, 1.3)}
    out = route_of_day(day, r, coords, object(), "motorbike", route_fn=fake)
    assert out["source"] == "osrm" and seen[0] == [(1.0, 1.0), (1.1, 1.1), (1.2, 1.2), (1.3, 1.3)]


def test_route_of_day_is_none_not_a_crash_when_osrm_is_down():
    from planning.model import Day, DayResult, Item
    day = Day(0, None, None, 480, 1260, None, None)
    r = DayResult((Item("visit", 500, 530, place_id="a"),), ("a",), (), 0, 0, 530)
    out = route_of_day(day, r, {"a": (1.0, 1.0)}, object(), "motorbike", route_fn=fake_route_down)
    assert out is None


def test_route_of_day_needs_at_least_two_points():
    from planning.model import Day, DayResult
    day = Day(0, None, None, 480, 1260, None, None)
    r = DayResult((), (), (), 0, 0, 480)
    assert route_of_day(day, r, {}, object(), "motorbike", route_fn=fake_route_ok) is None


def test_cost_adds_a_known_lodging_price_and_counts_an_unknown_one_separately():
    m = {"cost_vnd": 300000, "cost_unknown": 1}
    known = cost(m, 500000, 2)
    assert known == {"known_vnd": 300000 + 500000 * 2, "unknown_items": 1, "lodging_known": True}
    unknown = cost(m, None, 2)
    assert unknown == {"known_vnd": 300000, "unknown_items": 2, "lodging_known": False}
    no_stay = cost(m, None, 0)
    assert no_stay == {"known_vnd": 300000, "unknown_items": 1, "lodging_known": True}   # 0 nights: nothing to know


def test_build_assembles_the_plan_output_shape():
    d, recs = sample_trip(days=2)
    trip = prepared(d, recs)
    from planning.build import schedule_trip
    sched = schedule_trip(trip)
    m = compute_metrics(sched.ctxs, sched.results)
    chosen = {"id": "v1", "objective": "least_travel", "label": "Ít di chuyển", "score": [m["travel_min"], m["travel_min"]],
             "metrics": m,
             "itinerary": [], "travel_load": [], "robustness": {"level": "solid", "label": "Vững", "reasons": [],
                                                                 "scenarios": [], "breaking": [], "skipped": []},
             "backups": {"places": [], "on_delay": []}, "warnings": [], "lodging": {"id": None, "name": None, "price_vnd": None}}
    coords = {p.id: (p.lat, p.lng) for p in trip.by_place.values()}
    out = build(trip, [chosen], chosen, sched.results, d, coords, object(), route_fn=fake_route_down)
    for key in ("variants", "chosen", "itinerary", "route", "lodging", "cost", "travel_load", "reasons", "tradeoffs",
               "warnings", "uncertainty", "robustness", "backups", "provenance"):
        assert key in out, key
    assert out["chosen"] == "v1" and len(out["route"]) == len(trip.days)
