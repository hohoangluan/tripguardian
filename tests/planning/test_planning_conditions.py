"""Day conditions: weather beyond rain probability, crowds, shop closures, hazard notices (docs/PLANNING.md §Điều kiện từng ngày)."""

from datetime import date

import pytest
from plan_fixtures import (CFG, CENTRE, SOUTH, FakeLive, decision, fake_matrix, fixed_sun, no_geocode, rec,
                           sample_trip, spot)

import live
from planning import conditions
from planning.backup import sensitive
from planning.build import prepare, schedule_trip
from planning.conditions import DayCond, build_cond, crowd_tips, fetch_live, hazard, weather_level
from planning.engine import Engine
from planning.model import Day
from planning.session import Store
from planning.variants import build_variants

SAT, SUN = "2026-12-12", "2026-12-13"          # a Saturday and the Sunday after it
CLEAR = {"rain_prob": 0.1, "rain_mm": 0.0, "gust_kmh": 10.0, "storm": False, "source": "open-meteo", "fetched_at": "t"}
SEVERE = {**CLEAR, "rain_prob": 0.95, "rain_mm": 120.0, "gust_kmh": 40.0}
HEAVY = {**CLEAR, "rain_prob": 0.9, "rain_mm": 40.0, "storm": True}


def sig(**by_date):
    return {d: {"holiday": None, "events": [], "advisories": [], **v} for d, v in by_date.items()}


def day(d=SAT, weekday="sat"):
    return Day(0, date.fromisoformat(d), weekday, 480, 1260, None, None)


def trip(d, recs, weather=None, signals=None):
    return prepare(d, recs, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                   sun_fn=fixed_sun, weather=weather, signals=signals)


# ---------- reading the day ----------

def test_weather_levels_follow_the_configured_thresholds():
    assert weather_level(None, CFG) == "none"
    assert weather_level(CLEAR, CFG) == "none"
    assert weather_level({"rain_mm": 40}, CFG) == "heavy" and weather_level({"storm": True}, CFG) == "heavy"
    assert weather_level({"rain_mm": 90}, CFG) == "severe" and weather_level({"gust_kmh": 75}, CFG) == "severe"
    assert weather_level({"rain_prob": 0.99}, CFG) == "none"        # probability alone is not severity


def test_a_day_with_no_signal_has_no_condition():
    assert build_cond(day(), {SAT: {"rain_prob": 0.5}}, None, CFG) is None
    assert build_cond(Day(0, None, None, 480, 1260, None, None), None, sig(), CFG) is None


def test_weekend_is_busy_holiday_and_peak_events_are_peak():
    assert build_cond(day(), None, sig(), CFG).crowd == "busy"
    assert build_cond(day("2026-12-14", "mon"), None, sig(), CFG).crowd == "normal"
    h = build_cond(day("2026-09-02", "wed"), None, sig(**{"2026-09-02": {"holiday": "Quốc khánh"}}), CFG)
    assert (h.crowd, h.day_type, h.crowd_reasons) == ("peak", "holiday", ("Ngày lễ: Quốc khánh",))
    tet = {"events": [{"name": "Tết", "crowd": "peak", "closure_risk": True}]}
    assert build_cond(day("2027-02-06", "sat"), None, sig(**{"2027-02-06": tet}), CFG).closure_risk == "Tết"


# ---------- hazards: fail-closed ----------

def exposed_trip():
    d, recs = sample_trip()
    recs[4:7] = [spot(f"s{i + 1}", SOUTH, i, features={"weather_exposed": "present"}) for i in range(3)]
    return d, recs


def test_a_severe_day_keeps_weather_exposed_places_off_that_day():
    d, recs = exposed_trip()
    t = trip(d, recs, {SAT: SEVERE, SUN: CLEAR}, sig(**{SAT: {}, SUN: {}}))
    s = schedule_trip(t)
    assert not s.violations
    assert not {"s1", "s2", "s3"} & set(s.per_day[0]) and {"s1", "s2", "s3"} <= set(s.per_day[1])


def test_when_no_day_is_safe_the_plan_is_refused_not_adjusted():
    d, recs = exposed_trip()
    out = build_variants(d, recs, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                         sun_fn=fixed_sun, weather={SAT: SEVERE, SUN: SEVERE}, signals=sig(**{SAT: {}, SUN: {}}))
    assert not out["ok"] and {v["kind"] for v in out["violations"]} == {"hazard"}
    assert {"s1", "s2", "s3"} <= set(out["back_to_decision"]["places"])


def test_heavy_weather_is_not_a_hard_stop_but_counts_as_rain():
    d, recs = exposed_trip()
    t = trip(d, recs, {SAT: {**HEAVY, "rain_prob": 0.2}, SUN: CLEAR}, sig(**{SAT: {}, SUN: {}}))
    assert t.ctxs[0].wet == CFG.rain_high      # a low probability does not cancel a thunderstorm and t.ctxs[1].wet == pytest.approx(0.1)
    assert hazard(next(iter(t.by_place.values())), t.ctxs[0].cond) is None
    assert {w["code"] for w in t.warnings} >= {"heavy_weather"}


def landslide(radius=3.0, severity="severe", lat=SOUTH[0], lng=SOUTH[1]):
    return {"kind": "landslide", "severity": severity, "area": {"lat": lat, "lng": lng, "radius_km": radius},
            "note": "Sạt lở", "source": "KTTV", "issued": None}


def test_a_severe_notice_keeps_every_place_in_its_area_off_that_day():
    d, recs = sample_trip()                              # none of them weather-exposed
    t = trip(d, recs, None, sig(**{SAT: {"advisories": [landslide()]}, SUN: {}}))
    s = schedule_trip(t)
    assert not s.violations and not {"s1", "s2", "s3"} & set(s.per_day[0])
    assert any(w["code"] == "advisory" and "KTTV" in w["text"] for w in t.warnings)


def test_a_storm_notice_only_keeps_out_what_the_weather_hurts():
    d, recs = exposed_trip()
    storm = {**landslide(), "kind": "storm", "area": "city"}
    t = trip(d, recs, None, sig(**{SAT: {"advisories": [storm]}, SUN: {}}))
    s = schedule_trip(t)
    assert not s.violations and "c1" in s.per_day[0] + s.per_day[1]
    assert not {"s1", "s2", "s3"} & set(s.per_day[0])


def test_a_notice_below_severe_warns_and_makes_the_visit_sensitive_without_forbidding_it():
    d, recs = sample_trip()
    notice = {"advisories": [landslide(severity="warning")]}
    t = trip(d, recs, None, sig(**{SAT: notice, SUN: notice}))
    s = schedule_trip(t)
    assert not s.violations
    south = [(it, cx) for r, cx in zip(s.results, s.ctxs) for it in r.items if it.kind == "visit" and it.place_id.startswith("s")]
    assert len(south) == 3 and all("advisory" in sensitive(it, cx) for it, cx in south)


def test_without_any_signal_nothing_changes():
    d, recs = exposed_trip()
    assert all(cx.cond is None for cx in trip(d, recs, {SAT: {"rain_prob": 0.9}}).ctxs)


# ---------- crowds ----------

def busy_place():
    r = spot("c1", CENTRE, 0, features={"crowd": "low"})
    r["operation"]["crowd_by_time"] = {"weekend": {"morning": 20, "afternoon": 90}, "holiday": {"morning": 40, "afternoon": 95}}
    return r


def test_a_place_is_crowd_sensitive_only_on_a_busy_day_by_its_own_evidence():
    d, recs = sample_trip()
    recs[0] = busy_place()
    t = trip(d, recs, None, sig(**{SAT: {}, SUN: {}}))
    p = t.by_place["c1"]
    assert conditions.crowd_sensitive(p, t.ctxs[0].cond, CFG)
    assert not conditions.crowd_sensitive(t.by_place["c2"], t.ctxs[0].cond, CFG)          # no evidence of crowds
    assert not conditions.crowd_sensitive(p, DayCond(crowd="normal"), CFG)
    assert not conditions.crowd_sensitive(p, None, CFG)


def test_a_busy_day_adds_queue_time_and_buffer_to_a_busy_place():
    d, recs = sample_trip()
    recs[0] = busy_place()
    plain = schedule_trip(trip(d, recs))
    busy = schedule_trip(trip(d, recs, None, sig(**{SAT: {}, SUN: {}})))

    def minutes(s, kind, pid):
        return next(it.end - it.start for r in s.results for it in r.items
                    if it.kind == kind and (kind != "visit" or it.place_id == pid))
    assert minutes(busy, "visit", "c1") > minutes(plain, "visit", "c1")
    assert any(w["code"] == "crowd_day" for w in trip(d, recs, None, sig(**{SAT: {}, SUN: {}})).warnings)


def test_a_user_who_avoids_crowds_weighs_a_crowded_day_more():
    d, recs = sample_trip()
    recs[0] = busy_place()
    t = trip(d, recs, None, sig(**{SAT: {}, SUN: {}}))
    from dataclasses import replace
    from planning.days import crowd_risk
    avoid = replace(t.ctxs[0], crowd_tol="avoid")
    assert crowd_risk(["c1"], avoid) == crowd_risk(["c1"], t.ctxs[0]) * CFG.conditions["crowd_avoid_factor"] > 0
    assert crowd_risk(["c2"], t.ctxs[0]) == 0


def test_crowd_tips_name_the_calm_time_from_the_places_own_figures():
    d, recs = sample_trip()
    recs[0] = busy_place()
    t = trip(d, recs, None, sig(**{SAT: {}, SUN: {}}))
    (tip,) = crowd_tips(list(t.by_place.values()), [cx.cond for cx in t.ctxs], CFG)
    assert (tip["busy"], tip["calm"], tip["day_type"]) == ("afternoon", "morning", "weekend")
    assert crowd_tips(list(t.by_place.values()), [None, None], CFG) == []


# ---------- shops closed for Tết ----------

def test_a_closure_period_warns_and_flags_meal_places_for_a_backup():
    d, recs = sample_trip()
    tet = {"events": [{"name": "Tết Nguyên Đán", "crowd": "peak", "closure_risk": True}]}
    t = trip(d, recs, None, sig(**{SAT: tet, SUN: tet}))
    assert any(w["code"] == "holiday_closure" and "Tết" in w["text"] for w in t.warnings)
    s = schedule_trip(t)
    meal = next(it for r, cx in zip(s.results, s.ctxs) for it in r.items if it.kind == "visit" and it.place_id == "r1")
    cx = next(c for c, r in zip(s.ctxs, s.results) if any(i.place_id == "r1" for i in r.items))
    assert "holiday_closure" in sensitive(meal, cx)


# ---------- output and the engine ----------

def test_the_plan_output_reports_each_days_conditions_only_when_there_are_any():
    d, recs = sample_trip()
    out = build_variants(d, recs, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                         sun_fn=fixed_sun, weather={SAT: HEAVY, SUN: CLEAR}, signals=sig(**{SAT: {}, SUN: {}}))
    assert [c["weather"] for c in out["day_conditions"]] == ["heavy", "none"]
    assert out["day_conditions"][0]["crowd"] == "busy" and out["day_conditions"][0]["date"] == SAT
    plain = build_variants(d, recs, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                           sun_fn=fixed_sun)
    assert "day_conditions" not in plain


def make_engine(recs, conditions_fn=None):
    return Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                  sun_fn=fixed_sun, lodging_fn=lambda *a: [], background=False, conditions_fn=conditions_fn,
                  route_fn=lambda points, mode, cfg: {"points": [list(p) for p in points], "source": "osrm", "fetched_at": "t"})


def test_the_engine_asks_for_conditions_and_shows_them():
    d, recs = sample_trip()
    calls = []

    def conditions_fn(decision, by_id):
        calls.append(sorted(by_id)[:1])
        return {SAT: HEAVY, SUN: CLEAR}, sig(**{SAT: {}, SUN: {}})
    view = make_engine(recs, conditions_fn).create(d, None)["view"]
    assert calls and [c["weather"] for c in view["day_conditions"]] == ["heavy", "none"]
    assert any(w["code"] == "heavy_weather" for w in view["warnings"])
    assert make_engine(recs).create(d, None)["view"]["day_conditions"] == []


# ---------- fetching ----------

def test_fetch_collects_weather_holidays_events_and_notices_for_the_trips_dates(monkeypatch):
    d, recs = sample_trip()
    seen = {}
    monkeypatch.setattr(live, "weather", lambda lat, lng, dates, cfg: seen.update(dates=dates) or {x: CLEAR for x in dates})
    monkeypatch.setattr(live, "holidays", lambda dates: {date(2026, 12, 13): "X"})
    monkeypatch.setattr(live, "events", lambda dates: {})
    monkeypatch.setattr(live, "advisories", lambda dates: {})
    weather, signals = fetch_live(FakeLive())(d, {r["id"]: r for r in recs})
    assert seen["dates"] == [SAT, SUN] and set(weather) == {SAT, SUN}
    assert signals[SUN]["holiday"] == "X" and signals[SAT]["holiday"] is None


def test_an_unanswering_weather_source_leaves_weather_unknown_but_keeps_the_hand_entered_signals(monkeypatch):
    d, recs = sample_trip()

    def down(*a, **k):
        raise live.Unavailable("no network")
    monkeypatch.setattr(live, "weather", down)
    weather, signals = fetch_live(FakeLive())(d, {r["id"]: r for r in recs})
    assert weather is None and set(signals) == {SAT, SUN}


def test_a_trip_without_dates_fetches_nothing():
    d, recs = sample_trip(start_date=None)
    assert fetch_live(FakeLive())(d, {r["id"]: r for r in recs}) == (None, None)


def test_the_confirmed_plan_keeps_each_days_conditions():
    d, recs = sample_trip()
    e = make_engine(recs, lambda decision, by_id: ({SAT: HEAVY, SUN: CLEAR}, sig(**{SAT: {}, SUN: {}})))
    sid = e.create(d, None)["id"]
    e.act(sid, {"type": "pick_variant", "id": "v1"})
    out = e.confirm(sid)
    assert [c["weather"] for c in out["day_conditions"]] == ["heavy", "none"]
    plain = make_engine(recs)
    sid = plain.create(d, None)["id"]
    plain.act(sid, {"type": "pick_variant", "id": "v1"})
    assert "day_conditions" not in plain.confirm(sid)
