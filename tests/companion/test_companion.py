from datetime import datetime, timedelta

import pytest

from companion import Companion, load_settings, plan_hash, stops_of
from companion.trips import TZ

pytestmark = pytest.mark.pg

NOW = datetime(2026, 11, 12, 15, 0, tzinfo=TZ)  # a Thursday


def rec(pid, lat, lng, *, group="cafe", hours=True, exp=None, service=None, effort=None, visit=30, crowd=None):
    return {"id": pid, "identity": {"name": pid.upper(), "lat": lat, "lng": lng, "category_group": group},
            "operation": {"hours": {"status": "VERIFIED", "value": {d: [["07:00", "22:00"]] for d in
                                    ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}} if hours else None,
                          "visit_minutes": {"short": visit}, "crowd_by_time": crowd},
            "experience": exp or {}, "service": service or {}, "effort": effort or {}, "environment": {}}


def f(value, status="VERIFIED", n=4):
    return {"value": value, "status": status, "n": n, "distribution": {value: n}, "evidence": ["gmaps:x:0"],
            "confidence": {"agreement": 1.0}, "by_context": {}}


RECORDS = [
    rec("here", 11.94, 108.44, exp={"sunset_view": f("present"), "cozy_decor": f("present", n=9),
                                    "live_music": f("present", status="UNCERTAIN")},
        service={"entry_fee": f("paid"), "wait_time": f("long", status="UNCERTAIN")},
        crowd={"weekday": {"afternoon": 55}}),
    rec("near_ok", 11.941, 108.441, exp={"cozy_decor": f("present")}),
    rec("near_steep", 11.942, 108.441, effort={"steep_or_stairs": f("present")}),
    rec("near_unknown_effort", 11.943, 108.441),
    rec("near_no_hours", 11.944, 108.441, hours=False),
    rec("far_away", 12.20, 108.70),
    rec("planned_b", 11.945, 108.442),
]
PLAN = {"itinerary": [
    {"day": 1, "date": "2026-11-12", "window": ["08:00", "21:00"], "items": [
        {"kind": "visit", "start": "14:00", "end": "15:00", "place_id": "here", "name": "Here"},
        {"kind": "travel", "start": "15:00", "end": "15:10"},
        {"kind": "visit", "start": "17:30", "end": "18:30", "place_id": "planned_b", "name": "B"}]},
    {"day": 2, "date": "2026-11-13", "window": ["08:00", "21:00"], "items": [
        {"kind": "visit", "start": "09:00", "end": "10:00", "place_id": "near_ok", "name": "Near"}]}],
    "backups": {"on_delay": [{"day": 1, "place_id": "planned_b", "name": "B"}]},
    "warnings": [{"code": "hours_unknown", "text": "x"}], "day_conditions": []}
SEARCH = {"soft_weights": [{"feature": "cozy_decor", "value": "present", "weight": 1}],
          "hard_filters": [{"feature": "steep_or_stairs", "op": "ne", "value": "present", "unknown_policy": "flag"}],
          "context": {"mobility": "motorbike"}}


@pytest.fixture
def comp(pg_url):
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    clock = {"now": NOW}
    with ConnectionPool(pg_url, min_size=1, max_size=4, kwargs={"row_factory": dict_row}, open=True) as pool:
        c = Companion(pool, RECORDS, load_settings(), now=lambda: clock["now"])
        c.clock = clock
        c.sync("j00000000001", None, PLAN)
        yield c


def stop(c, place):
    return next(s for d in c.today("j00000000001", PLAN)["days"] for s in d["stops"] if s["place_id"] == place)


def test_plan_becomes_stops_with_local_times(comp):
    view = comp.today("j00000000001", PLAN)
    assert view["day"] == 1 and view["today"] == 1 and view["trip"]["start_date"] == "2026-11-12"
    assert [(s["place_id"], s["arrive"]) for s in view["days"][0]["stops"]] == [("here", "14:00"), ("planned_b", "17:30")]
    assert all(s["status"] == "planned" for d in view["days"] for s in d["stops"])  # never "missed"
    assert len(stops_of(PLAN)) == 3 and plan_hash(stops_of(PLAN)) == plan_hash(stops_of(PLAN))


def test_reconfirm_keeps_checked_in_stops_and_moves_the_rest(comp):
    here = stop(comp, "here")
    comp.checkin("j00000000001", stop_id=here["id"])
    moved = {**PLAN, "itinerary": [
        {"day": 1, "date": "2026-11-12", "items": [{"kind": "visit", "start": "16:00", "end": "17:00",
                                                    "place_id": "planned_b", "name": "B"}]},
        {"day": 2, "date": "2026-11-13", "items": []}]}
    comp.sync("j00000000001", None, moved)
    view = comp.today("j00000000001", moved)
    by = {s["place_id"]: s for d in view["days"] for s in d["stops"]}
    assert by["here"]["status"] == "arrived" and by["here"]["id"] == here["id"]  # kept as it happened
    assert by["planned_b"]["arrive"] == "16:00" and "near_ok" not in by


def test_checkin_skip_rate_are_voluntary_and_validated(comp):
    b = stop(comp, "planned_b")
    assert comp.skip("j00000000001", b["id"], "crowded")["status"] == "skipped"
    with pytest.raises(ValueError):
        comp.skip("j00000000001", b["id"], "because")
    assert comp.rate("j00000000001", b["id"], -1)["rating"] == -1
    with pytest.raises(ValueError):
        comp.rate("j00000000001", b["id"], 5)
    with pytest.raises(ValueError):
        comp.checkin("j00000000001", stop_id="not-a-uuid")
    with pytest.raises(ValueError):
        comp.checkin("j00000000001", place_id="invented-place")
    off = comp.checkin("j00000000001", place_id="near_no_hours")
    assert off["on_plan"] is False and comp.today("j00000000001", PLAN)["here"]["place_id"] == "near_no_hours"


def test_suggestions_come_from_serving_with_hard_filters_and_unknowns_kept(comp):
    comp.checkin("j00000000001", stop_id=stop(comp, "here")["id"])
    out = comp.suggestions("j00000000001", SEARCH, PLAN, "here", disliked=set())
    ids = {r["id"] for r in RECORDS}
    assert {n["place_id"] for n in out["nearby"]} <= ids
    nearby = {n["place_id"]: n for n in out["nearby"]}
    assert "near_steep" not in nearby  # hard filter fails
    assert nearby["near_unknown_effort"]["flags"] == ["steep_or_stairs"]  # unknown kept, flagged, never "pass"
    assert nearby["near_no_hours"]["open"] is None  # hours unknown: "chưa xác nhận", not open
    assert "far_away" not in nearby and "planned_b" not in nearby and "near_ok" not in nearby  # far / in the plan
    assert [p["feature"] for p in out["play"]][:1] == ["cozy_decor"] and "live_music" not in [p["feature"] for p in out["play"]]
    assert {p["feature"]: p["status"] for p in out["practical"]} == {"entry_fee": "VERIFIED", "wait_time": "UNCERTAIN"}
    assert out["timely"]["sunset"].startswith("17:") and out["timely"]["crowd"]["pct"] == 55
    assert out["next"]["place_id"] == "planned_b" and out["budget_min"] == 150
    with pytest.raises(ValueError):
        comp.suggestions("j00000000001", SEARCH, PLAN, "invented", disliked=set())


def test_disliked_places_are_not_suggested(comp):
    out = comp.suggestions("j00000000001", SEARCH, PLAN, "here", disliked={"near_unknown_effort"})
    assert "near_unknown_effort" not in {n["place_id"] for n in out["nearby"]}


def test_late_checkin_offers_the_plans_own_options_neutrally(comp):
    comp.clock["now"] = NOW.replace(hour=14, minute=50)
    comp.checkin("j00000000001", stop_id=stop(comp, "here")["id"])
    tight = comp.today("j00000000001", PLAN)["tight"]
    assert tight["late_min"] == 50 and tight["options"][0]["id"] == "drop:planned_b"
    assert comp.option("j00000000001", PLAN, "drop:planned_b") == {"type": "drop_place", "place": "planned_b"}
    with pytest.raises(ValueError):
        comp.option("j00000000001", PLAN, "drop:near_ok")


def test_on_time_checkin_is_not_tight(comp):
    comp.clock["now"] = NOW.replace(hour=14, minute=10)
    comp.checkin("j00000000001", stop_id=stop(comp, "here")["id"])
    assert comp.today("j00000000001", PLAN)["tight"] is None


def test_quality_counts_hard_filter_fails_and_unknowns_on_planned_places(comp):
    si = {"hard_filters": [{"feature": "steep_or_stairs", "op": "ne", "value": "present", "unknown_policy": "exclude"}]}
    plan = {"itinerary": [{"day": 1, "items": [{"kind": "visit", "place_id": "near_steep"},
                                               {"kind": "visit", "place_id": "near_unknown_effort"}]}]}
    assert comp.quality(plan, si) == {"places": 2, "hard_checks": 2, "hard_fail": 1, "hard_unknown": 1}
