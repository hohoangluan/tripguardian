from types import SimpleNamespace

from fixtures import si, srec

from decision.fit import centers, fit, radius
from decision.model import Cand
from decision.settings import default
from decision.trip_days import trip_days

CFG = default()
P = SimpleNamespace(travel_mult=1.0, crowd_tolerance=None)
BUSY = {"weekday": {"morning": 80, "noon": 40, "afternoon": 30, "evening": 20, "night": 10},
        "weekend": {"morning": 95, "noon": 60, "afternoon": 50, "evening": 40, "night": 20}}


def run(c, s, profile=P, anchor_areas=frozenset()):
    by_id = {c.id: c.rec}
    fit(c, s, trip_days(s.context, CFG), centers(s, by_id, CFG), set(anchor_areas), profile, CFG)
    return c


def test_centers_base_then_anchors_else_city_center():
    base, anc = srec("B", lat=11.95, lng=108.45), srec("A", lat=11.90, lng=108.40)
    s = si(context={"base": {"place_id": "B", "text": "ks"}}, anchors=[{"place_id": "A", "priority": "must"}])
    assert [n for n, _ in centers(s, {"B": base, "A": anc}, CFG)] == ["Nơi B", "Nơi A"]
    assert centers(si(), {}, CFG)[0][0] == "trung tâm Đà Lạt"


def test_distance_and_radius_shrink_with_travel_tolerance():
    near = run(Cand(srec("N", lat=11.9404, lng=108.4583), "experience"), si())
    far = run(Cand(srec("F", lat=12.03, lng=108.4583), "experience"), si())
    assert near.fit == 1.0 and near.minutes == 1 and near.center == "trung tâm Đà Lạt"
    assert 0 < far.fit < 0.5
    assert radius(si(pace={"max_leg_min": 20}), P, CFG) < radius(si(), P, CFG)
    assert radius(si(), SimpleNamespace(travel_mult=0.5, crowd_tolerance=None), CFG) == CFG.radius_km["motorbike"] / 2


def test_crowd_penalty_only_when_avoiding_and_day_type_known():
    rec = srec("C", lat=11.9404, lng=108.4583, crowd_by_time=BUSY)
    c = run(Cand(rec, "experience"), si(pace={"crowd_tolerance": "avoid"}))
    assert c.fit == 1.0 - CFG.crowd_penalty and c.flags[0]["code"] == "crowded"
    no_dates = run(Cand(rec, "experience"), si(context={"start_date": None, "month": 12}, pace={"crowd_tolerance": "avoid"}))
    assert no_dates.fit == 1.0 and no_dates.flags[0]["code"] == "crowded"
    assert run(Cand(rec, "experience"), si()).flags == []


def test_area_bonus_rain_and_rough_road_flags():
    rec = srec("R", lat=12.02, features={"weather_exposed": "present", "rough_road_access": "present"}, area="area-9")
    s = si(context={"start_date": "2026-07-06", "mobility": "ride"})
    c = run(Cand(rec, "experience"), s, anchor_areas={"area-9"})
    plain = run(Cand(srec("R2", lat=12.02, area="area-1"), "experience"), s)
    assert round(c.fit - plain.fit, 3) == CFG.area_bonus
    assert {f["code"] for f in c.flags} == {"rain", "rough_road"}
    assert any("xe công nghệ" in f["text"] for f in c.flags)
