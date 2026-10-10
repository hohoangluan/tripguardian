"""Nights are their own fact: 3N2Đ, 3N3Đ and 1N0Đ differ in lodging nights and in the night slots of the itinerary."""

import pytest
from plan_fixtures import CENTRE, CFG, FakeLive, fake_matrix, fixed_sun, no_geocode, prepared, sample_trip, spot

from planning import build_plan, render_text
from planning.frame import trip_days
from planning.lodging import _dates
from planning.objectives import metrics as compute_metrics
from planning.output import build

CASES = [(3, 2), (3, 3), (1, 0)]     # 3N2Đ, 3N3Đ, 1N0Đ


def plan(days, nights, extra=(), **kw):
    """A trip of `days` days over the shared centre/south places, plus the given extra records."""
    d, recs = sample_trip(days=days, nights=nights, **kw)
    recs = [*recs, *extra]
    return build_plan(d, recs, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                      sun_fn=fixed_sun), recs


def night_market(pid="nm", i=6, hours=("17:00", "23:00"), group="market", **kw):
    return spot(pid, CENTRE, i, group=group, hours={d: [list(hours)] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")},
                usable=("experience", "backup"), **kw)


def nights_of_plan(p):
    return [d["night"] is not None for d in p["itinerary"]]


# ---------- lodging nights follow the trip ----------

@pytest.mark.parametrize("days, nights", CASES)
def test_cost_and_check_out_use_the_nights_of_the_trip(days, nights):
    d, recs = sample_trip(days=days, nights=nights)
    trip = prepared(d, recs)
    from planning.build import schedule_trip
    sched = schedule_trip(trip)
    m = compute_metrics(sched.ctxs, sched.results)
    chosen = {"id": "v1", "objective": "least_travel", "label": "x", "score": [0, 0], "metrics": m, "itinerary": [],
              "travel_load": [], "robustness": {"level": "solid", "label": "Vững", "reasons": [], "scenarios": [],
                                                "breaking": [], "skipped": []},
              "backups": {"places": [], "on_delay": []}, "warnings": [],
              "lodging": {"id": "h", "name": "h", "price_vnd": 500_000}}
    out = build(trip, [chosen], chosen, sched.results, d, {}, object(), route_fn=lambda *a: None)
    assert out["cost"]["known_vnd"] == m["cost_vnd"] + 500_000 * nights
    start, check_out = _dates(d["trip_context"]["context"])
    assert (start, check_out) == ("2026-12-12", f"2026-12-{12 + nights:02d}")


def test_without_nights_the_trip_sleeps_days_minus_one():
    d, recs = sample_trip(days=3)
    assert _dates(d["trip_context"]["context"])[1] == "2026-12-14"


# ---------- the last day ----------

def test_a_trip_that_sleeps_after_its_last_day_runs_that_day_to_the_end_of_the_evening():
    ctx = lambda **kw: {"days": 3, "nights": 3, "checkout_at": None, "day_end": None, "checkin_at": None, "start_date": None, **kw}
    assert trip_days(ctx(), CFG, None, None, None)[-1].end == CFG.day_end
    assert trip_days(ctx(nights=2), CFG, None, None, None)[-1].end == CFG.leave_at
    assert trip_days(ctx(checkout_at="12:00"), CFG, None, None, None)[-1].end == 12 * 60


# ---------- night slots ----------

@pytest.mark.parametrize("days, nights, slots", [(3, 2, [True, True, False]), (3, 3, [True, True, True]),
                                                 (1, 0, [False]), (3, None, [True, True, False])])
def test_only_nights_that_really_exist_get_a_slot(days, nights, slots):
    p, _ = plan(days, nights, extra=[night_market()])
    assert nights_of_plan(p) == slots


def test_a_night_slot_opens_after_the_day_and_offers_only_places_open_then():
    late_cafe = night_market("late", 7, hours=("08:00", "22:30"), group="cafe")           # open 90 min of the slot
    day_cafe = night_market("day", 8, hours=("08:00", "21:00"), group="cafe")             # shut when the slot opens
    park = spot("park", CENTRE, 9, group="nature", hours={d: [["00:00", "23:59"]] for d in
                                                         ("mon", "tue", "wed", "thu", "fri", "sat", "sun")})
    unknown = spot("mystery", CENTRE, 10, group="bar", hours=None)                        # hours unknown: never guessed
    hotel = night_market("inn", 11, hours=("00:00", "23:59"), group="stay")
    p, _ = plan(2, 1, extra=[night_market(), late_cafe, day_cafe, park, unknown, hotel])
    night = p["itinerary"][0]["night"]
    assert night["start"] == "21:00" and night["end"] > night["start"] and night["empty"] is False
    assert {o["place_id"] for o in night["options"]} == {"nm", "late"}
    assert all("name" in o and "km" in o for o in night["options"])
    assert p["itinerary"][1]["night"] is None                                              # the return day has no night


def test_a_place_already_in_the_plan_is_not_offered_again_for_the_night():
    d, recs = sample_trip(days=2, nights=1)
    market = night_market()
    d["confirmed"].append({"id": "nm", "name": "nm", "role": "selected", "visit": None, "flags": [], "relaxed": []})
    p = build_plan(d, [*recs, market], cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                   sun_fn=fixed_sun)
    assert p["itinerary"][0]["night"]["options"] == []


def test_a_night_with_no_night_place_stays_empty_and_says_so():
    p, _ = plan(3, 2)
    for day in p["itinerary"][:2]:
        night = day["night"]
        assert night["options"] == [] and night["empty"] is True and night["text"]
    text = render_text(p)
    assert text.count("Đêm") == 2 and "chưa có nơi hợp ban đêm" in text.lower()


def test_a_hard_filter_the_place_fails_keeps_it_off_the_night():
    bar = night_market("bar", 6, group="bar", features={"live_music": "present"})
    hard = [{"feature": "live_music", "op": "ne", "value": "present", "unknown_policy": "exclude"}]
    p, _ = plan(2, 1, extra=[bar, night_market("nm", 7)], hard=hard)
    assert {o["place_id"] for o in p["itinerary"][0]["night"]["options"]} == {"nm"}


def test_night_slots_are_plain_json_and_deterministic():
    import json
    a, _ = plan(3, 2, extra=[night_market()])
    b, _ = plan(3, 2, extra=[night_market()])
    assert a == b and json.loads(json.dumps(a)) == a


# ---------- the session and the confirmed Plan Output ----------

def test_the_session_view_and_the_confirmed_plan_carry_the_night_blocks():
    from plan_fixtures import fake_lodging
    from planning.engine import Engine
    from planning.session import Store
    d, recs = sample_trip(days=3, nights=2)
    e = Engine([*recs, night_market()], cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode,
               matrix_fn=fake_matrix, sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging,
               route_fn=lambda *a: None, background=False)
    sid = e.create(d, None)["id"]
    e.act(sid, {"type": "pick_variant", "id": e.variants(sid)[0]["id"]})
    shown = e.load(sid)["view"]["itinerary"]
    assert [day["night"] is not None for day in shown] == [True, True, False]
    assert [o["place_id"] for o in shown[0]["night"]["options"]] == ["nm"]
    confirmed = e.confirm(sid)["itinerary"]
    assert [day["night"] is not None for day in confirmed] == [True, True, False]
