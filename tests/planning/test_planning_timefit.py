from dataclasses import replace

from plan_fixtures import CFG, day_ctx, decision, prepared, rec

from planning.build import build_plan, schedule_trip
from planning.route import order_day
from planning.schedule import simulate
from planning.timefit import visit_score, windows_for


def test_photo_garden_and_nightlife_are_scored_at_actual_visit_time():
    cx = day_ctx([rec("garden", 11.94, 108.45, group="garden_farm", features={"flower_garden": "present"}),
                  rec("bar", 11.941, 108.45, group="bar")])
    cx = replace(cx, purpose="photo")
    assert visit_score(cx.places["garden"], 540, 600, cx)[0] < visit_score(cx.places["garden"], 1140, 1200, cx)[0]
    result = order_day(["bar", "garden"], cx)
    visits = {i.place_id: i for i in result.items if i.kind == "visit"}
    assert visits["garden"].end <= 1050
    assert visits["bar"].start >= 1080
    assert not result.violations


def test_coffee_is_an_afternoon_snack_never_a_lunch():
    cx = day_ctx([rec("coffee", 11.94, 108.45, group="cafe")])
    result = simulate(["coffee"], cx)
    item = next(i for i in result.items if i.kind == "visit")
    assert 870 <= item.start < 1050
    assert result.time_details[0]["source"] == "heuristic"


def test_explicit_evening_photo_beats_default_and_indoor_photo_has_no_daylight_rule():
    cx = day_ctx([rec("indoor", 11.94, 108.45, features={"setting": "indoor"}),
                  rec("garden", 11.941, 108.45, group="garden_farm")])
    cx = replace(cx, purpose="photo")
    assert not windows_for(cx.places["indoor"], cx)
    cx = replace(cx, time_preferences=({"place_id": "garden", "period": "evening", "weight": 2},))
    result = simulate(["garden"], cx)
    assert next(i.start for i in result.items if i.kind == "visit") >= 1080
    assert result.time_details[0]["source"] == "user"


def test_soft_time_never_blocks_hours_or_day_end_and_never_shrinks_below_short():
    cx = day_ctx([rec("bar", 11.94, 108.45, group="bar", hours={"mon": [["08:00", "10:00"]]})], end=600)
    result = simulate(["bar"], cx)
    visit = next(i for i in result.items if i.kind == "visit")
    assert not result.violations
    assert visit.end <= 600 and visit.end - visit.start >= cx.places["bar"].visit["short"]
    assert result.time_penalty > 0


def test_competing_morning_visits_can_move_to_the_next_day():
    records = [rec(x, 11.94, 108.45, visit=(90, 150, 180), group="museum") for x in ("a", "b")]
    for record in records:
        record["operation"]["visit_minutes"]["source"] = "reviews"
        record["operation"]["visit_minutes"]["n"] = 3
    d = decision(["a", "b"], days=2, leave_at="21:00")
    d["trip_context"]["time_preferences"] = [{"period": "morning", "weight": 3}]
    sched = schedule_trip(prepared(d, records))
    assert all(len(ids) == 1 for ids in sched.per_day)
    assert not sched.violations


def test_plan_reports_time_reasons_without_automatically_adding_a_place():
    from plan_fixtures import FakeLive, fake_matrix, fixed_sun, no_geocode
    records = [rec("garden", 11.94, 108.45, group="garden_farm")]
    d = decision(["garden"], days=1)
    plan = build_plan(d, records, CFG, FakeLive(), no_geocode, fake_matrix, fixed_sun)
    assert plan["time_suitability"][0]["places"][0]["place_id"] == "garden"
    assert "recommendations" in plan
    assert {i["place_id"] for day in plan["itinerary"] for i in day["items"] if i["kind"] == "visit"} == {"garden"}


def test_optional_gap_suggestions_use_real_pool_and_diet_checks():
    from planning.recommendations import recommend
    veg = {"feature": "vegetarian_options", "op": "eq", "value": "yes", "unknown_policy": "exclude"}
    records = [rec("garden", 11.94, 108.45, group="garden_farm"),
               rec("good", 11.941, 108.45, group="cafe", usable=("meal", "experience", "backup"),
                   features={"vegetarian_options": "yes"}),
               rec("bad", 11.942, 108.45, group="restaurant", usable=("meal", "backup"),
                   features={"vegetarian_options": "no"})]
    d = decision(["garden"], days=1, hard=[veg], leave_at="18:00")     # a snack needs an afternoon gap to fill
    d["backup_pool"] = [{"id": "good"}, {"id": "bad"}, {"id": "invented"}]
    d["trip_context"]["activities"] = {"good": "eating"}
    trip = prepared(d, records)
    sched = schedule_trip(trip)
    before = sched.results[:]
    suggestions = recommend(sched.ctxs, sched.results, d, trip.by_id)
    alternatives = [a for s in suggestions for a in s.get("alternatives") or []]
    assert "good" in {a["id"] for a in alternatives}
    assert not {"bad", "invented"} & {a["id"] for a in alternatives}
    assert all(s["optional"] for s in suggestions)
    assert sched.results == before


def test_waiting_for_beautiful_time_falls_back_when_it_would_break_a_later_visit():
    cx = day_ctx([rec("coffee", 11.94, 108.45, group="cafe"),
                  rec("museum", 11.941, 108.45, hours={"mon": [["08:00", "10:30"]]})])
    result = simulate(["coffee", "museum"], cx)
    assert not result.violations
    assert next(i for i in result.items if i.place_id == "museum" and i.kind == "visit").end <= 630


def test_first_evening_activity_does_not_claim_that_lunch_was_missed():
    cx = day_ctx([rec("bar", 11.94, 108.45, group="bar")])
    result = simulate(["bar"], cx)
    assert next(i for i in result.items if i.kind == "visit").start >= 1080
    assert "meal_missed:lunch" not in result.notes
    assert any(i.kind == "meal_free" and i.name == "lunch" for i in result.items)


def test_global_walking_and_photo_periods_apply_to_relevant_default_activities():
    cx = day_ctx([rec("garden", 11.94, 108.45, group="garden_farm")])
    for activity, period, earliest in [("walking", "afternoon", 870), ("photography", "evening", 1080)]:
        requested = replace(cx, purpose="photo" if activity == "photography" else None,
                            time_preferences=({"activity": activity, "period": period},))
        result = simulate(["garden"], requested)
        assert next(i for i in result.items if i.kind == "visit").start >= earliest
        assert result.time_details[0]["source"] == "user"


def test_explicit_coffee_activity_is_not_reinterpreted_as_a_photo_visit():
    cx = day_ctx([rec("cafe", 11.94, 108.45, group="cafe", features={"photo_spot": "present"})])
    cafe = replace(cx.places["cafe"], activity="coffee", activity_explicit=True)
    cx = replace(cx, places={"cafe": cafe}, purpose="photo",
                 time_preferences=({"activity": "photography", "period": "evening"},))
    assert windows_for(cafe, cx)[0].reason == "light_snack"      # a cafe is an afternoon snack, not a photo visit


def test_disabling_time_suitability_removes_its_penalties():
    cx = day_ctx([rec("garden", 11.94, 108.45, group="garden_farm")])
    cx = replace(cx, cfg=replace(cx.cfg, time_suitability={**cx.cfg.time_suitability, "enabled": False}))
    assert visit_score(cx.places["garden"], 1140, 1170, cx)[0] == 0


def test_route_cache_does_not_reuse_the_old_paces_visit_length():
    records = [rec("a", 11.94, 108.45)]
    trip = prepared(decision(["a"], days=1), records)
    first = schedule_trip(trip)
    slower = replace(trip, pace="slow", ctxs=[replace(cx, pace="slow") for cx in trip.ctxs])
    second = schedule_trip(slower)
    visit = next(i for i in second.results[0].items if i.kind == "visit")
    assert visit.end - visit.start == 90
    assert first.results[0] != second.results[0]
