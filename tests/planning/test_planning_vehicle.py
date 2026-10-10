"""Routing per vehicle (docs/P4_PLANNING.md §Phương tiện): a motorbike is door to door, a car pays for parking and parks
once to walk an area, a trip with no vehicle only walks. Grab / taxi (`ride`) is not a mode any more."""

import pytest
from plan_fixtures import CENTRE, SOUTH, decision, fake_matrix, prepared, rec, spot

import live
from planning.frame import trip_days
from plan_fixtures import CFG

CALLS = []


def counting_matrix(points, mode, cfg):
    CALLS.append(mode)
    return fake_matrix(points, mode, cfg)


def trip(mobility, *, features=None, south_features=None, **kw):
    recs = [spot("c1", CENTRE, 0), spot("s1", SOUTH, 0, features=south_features)]
    d = decision([r["id"] for r in recs], mobility=mobility, **kw)
    return prepared(d, recs, matrix=counting_matrix)


def test_the_modes_are_motorbike_car_and_walk_in_every_table():
    assert set(CFG.rough_speed_kmh) == set(CFG.radius_km) == set(CFG.park_min) == {"motorbike", "car", "walk"}
    assert set(live.load_settings().mode_factor) == {"motorbike", "car", "walk"}


def test_a_motorbike_arrives_door_to_door_with_the_matrix_time():
    t = trip("motorbike").travel
    assert t.leg("c1", "s1") == (fake_matrix([CENTRE, SOUTH], None, None)["minutes"][0][1] + CFG.park_min["motorbike"],
                                 "motorbike")


def test_a_car_pays_parking_at_every_stop_and_more_where_parking_is_hard():
    drive = fake_matrix([CENTRE, SOUTH], None, None)["minutes"][0][1]
    easy = trip("car").travel.leg("c1", "s1")
    hard = trip("car", south_features={"parking": "hard"}).travel.leg("c1", "s1")
    assert easy == (drive + CFG.park_min["car"], "car")
    assert hard == (drive + CFG.park_min["car"] + CFG.park_hard_extra_min, "car")
    # the same hard parking costs a motorbike nothing extra
    assert trip("motorbike", south_features={"parking": "hard"}).travel.leg("c1", "s1")[0] == \
        trip("motorbike").travel.leg("c1", "s1")[0]


def test_a_car_parks_once_and_walks_a_leg_a_motorbike_would_ride():
    a, b = (11.9404, 108.4583), (11.9404 + 0.0054, 108.4583)   # about 0.6 km apart: over walk_km, under car_walk_km
    recs = [rec("a", *a), rec("b", *b)]
    ride = prepared(decision(["a", "b"], mobility="motorbike"), recs).travel.leg("a", "b")
    walk = prepared(decision(["a", "b"], mobility="car"), recs).travel.leg("a", "b")
    assert ride[1] == "motorbike" and walk[1] == "walk"


def test_a_trip_with_no_vehicle_only_walks_and_asks_osrm_nothing():
    CALLS.clear()
    p = trip("walk")
    assert CALLS == [] and p.travel.source == "walk"
    mins, mode = p.travel.leg("c1", "s1")
    assert mode == "walk" and mins > 30                      # 4 km on foot: the plan shows it, it does not hide it
    assert any(w["code"] == "walk_only" for w in p.warnings)


def ctx(**kw):
    return {"start_date": "2026-12-12", "days": 3, "checkin_at": None, "checkout_at": None, "day_end": None, **kw}


@pytest.mark.parametrize("arrival", ["bus", "plane"])
def test_arriving_by_coach_or_plane_on_a_motorbike_leaves_time_to_collect_and_return_the_bike(arrival):
    days = trip_days(ctx(checkin_at="13:30", checkout_at="12:00", arrival_mode=arrival, mobility="motorbike"),
                     CFG, "h", None, None)
    assert days[0].start == 810 + CFG.rental["pickup_min"]
    assert days[-1].end == 720 - CFG.rental["return_min"]


@pytest.mark.parametrize("kw", [{"arrival_mode": "self", "mobility": "motorbike"},
                                {"arrival_mode": "bus", "mobility": "car"},
                                {"arrival_mode": "bus", "mobility": "walk"},
                                {"arrival_mode": None, "mobility": "motorbike"}])
def test_nobody_else_is_given_rental_time(kw):
    days = trip_days(ctx(checkin_at="13:30", checkout_at="12:00", **kw), CFG, "h", None, None)
    assert (days[0].start, days[-1].end) == (810, 720)
