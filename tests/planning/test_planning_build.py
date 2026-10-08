import json

from plan_fixtures import CENTRE, CFG, all_days, decision, fake_matrix, fixed_sun, no_geocode, prepared, rec, spot

from live import Unavailable
from planning import build_plan, render_text

CENTRE = (11.9404, 108.4583)
FAR = (11.9029, 108.4482)       # about 4 km from the centre


def spot(pid, anchor, i, **kw):
    return rec(pid, anchor[0] + i * 0.002, anchor[1] + i * 0.002, area="area-1" if anchor == CENTRE else "area-2", **kw)


def trip(**kw):
    """Four places in the centre, three out south and a restaurant."""
    recs = [spot("c1", CENTRE, 0), spot("c2", CENTRE, 1), spot("c3", CENTRE, 2), spot("c4", CENTRE, 3),
            spot("s1", FAR, 0), spot("s2", FAR, 1), spot("s3", FAR, 2),
            spot("r1", CENTRE, 4, usable=("meal", "backup"))]
    return decision([r["id"] for r in recs], **kw), recs


def build(d, recs, matrix=fake_matrix, geocode=no_geocode, **kw):
    return build_plan(d, recs, cfg=CFG, live_cfg=_Live(), geocode_fn=geocode, matrix_fn=matrix, sun_fn=fixed_sun, **kw)


class _Live:
    tz_offset_h = 7


def visits(plan):
    return [[i["place_id"] for i in d["items"] if i["kind"] == "visit"] for d in plan["itinerary"]]


def test_a_two_day_trip_is_built_with_every_place_once_and_passes_validation():
    d, recs = trip()
    plan = build(d, recs)
    assert plan["ok"], plan["violations"]
    placed = [p for day in visits(plan) for p in day]
    assert sorted(placed) == sorted(r["id"] for r in recs) and len(plan["itinerary"]) == 2
    assert plan["uncertainty"]["travel_source"] == "osrm" and plan["unplaced"] == []


def test_the_two_clusters_land_on_different_days():
    d, recs = trip()
    day1, day2 = visits(build(d, recs))
    centre, south = {"c1", "c2", "c3", "c4", "r1"}, {"s1", "s2", "s3"}
    assert (set(day1) | set(day2)) == centre | south
    assert south <= set(day1) or south <= set(day2)


def test_the_same_input_gives_the_same_plan_and_the_plan_is_plain_json():
    d, recs = trip()
    first, second = build(d, recs), build(d, recs)
    assert first == second
    assert json.loads(json.dumps(first)) == first


def test_one_matrix_request_serves_the_whole_trip():
    d, recs = trip()
    calls = []

    def counting(points, mode, cfg):
        calls.append(len(points))
        return fake_matrix(points, mode, cfg)

    build(d, recs, matrix=counting)
    assert len(calls) == 1 and calls[0] >= len(recs)


def test_without_osrm_the_plan_is_built_from_rough_times_and_says_so():
    d, recs = trip()

    def dead(points, mode, cfg):
        raise Unavailable("osrm down")

    plan = build(d, recs, matrix=dead)
    assert plan["uncertainty"]["travel_source"] == "rough"
    assert "travel_rough" in {w["code"] for w in plan["warnings"]}
    assert plan["provenance"]["travel"] == {"source": "rough", "fetched_at": None}
    assert sorted(p for day in visits(plan) for p in day) == sorted(r["id"] for r in recs)


def test_a_place_that_cannot_be_scheduled_is_reported_and_an_unplaced_anchor_fails_the_plan():
    d, recs = trip(roles={"c1": "anchor"})
    d["confirmed"].append({"id": "ghost", "name": "Ghost", "role": "selected", "flags": [], "relaxed": []})
    plan = build(d, recs)
    assert plan["unplaced"] == [{"id": "ghost", "name": "Ghost", "reason": "no_record"}]
    assert plan["ok"]
    d["confirmed"].append({"id": "gone", "name": "Gone", "role": "anchor", "flags": [], "relaxed": []})
    failed = build(d, recs)
    assert not failed["ok"] and [v["kind"] for v in failed["violations"]] == ["anchor"]


def test_the_base_the_entry_and_the_exit_become_the_start_and_end_of_the_trip():
    d, recs = trip(base={"place_id": "c1", "text": "c1"}, entry={"place_id": None, "text": "Bến xe"},
                   exit={"place_id": None, "text": "Sân bay"})
    hit = lambda text: {"lat": 11.9404, "lng": 108.4583, "label": text, "source": "nominatim", "fetched_at": "t"}
    plan = build(d, recs, geocode=hit)
    first, last = plan["itinerary"][0]["items"][0], plan["itinerary"][-1]["items"][-1]
    assert first["kind"] == "travel" and first["from"] == "@entry"
    assert last["kind"] == "travel" and last["to"] == "@exit"
    assert plan["provenance"]["points"]["@entry"] == {"text": "Bến xe", "source": "nominatim", "fetched_at": "t"}
    assert "entry_exit_unknown" not in {w["code"] for w in plan["warnings"]}


def test_a_trip_without_dates_or_entry_points_says_what_it_could_not_check():
    d, recs = trip(start_date=None, days=None)
    codes = {w["code"] for w in build(d, recs)["warnings"]}
    assert {"days_assumed", "dates_unknown", "entry_exit_unknown", "base_unknown"} <= codes


def test_places_without_hours_are_flagged_not_assumed_open_silently():
    d, recs = trip()
    recs[0] = spot("c1", CENTRE, 0, hours=None)
    assert any(w["code"] == "hours_unknown" and "c1" in w["text"] for w in build(d, recs)["warnings"])


def test_a_hard_filter_the_confirmed_place_breaks_fails_the_plan_as_physical():
    d, recs = trip(hard=[{"feature": "steep_or_stairs", "op": "ne", "value": "present", "unknown_policy": "exclude"}])
    recs[0] = spot("c1", CENTRE, 0, features={"steep_or_stairs": "present"})
    plan = build(d, recs)
    assert not plan["ok"]
    assert [(v["kind"], v["physical"], v["place_id"]) for v in plan["violations"]] == [("hard", True, "c1")]


def test_what_the_user_relaxed_and_what_could_not_be_placed_are_tradeoffs_and_the_log_is_kept():
    d, recs = trip(relaxed={"c1": ["long_walk"]}, log=["chose c1 over c9"])
    plan = build(d, recs)
    assert {"kind": "relaxed", "place_id": "c1", "features": ["long_walk"]} in plan["tradeoffs"]
    assert plan["reasons"] == ["chose c1 over c9"]


def test_decision_flags_reach_the_warnings():
    d, recs = trip(flags={"s1": ["giờ mở cửa chưa chắc"]})
    assert {"code": "flag", "text": "giờ mở cửa chưa chắc"} in build(d, recs)["warnings"]


def test_travel_load_adds_up_the_travel_items_of_each_day():
    d, recs = trip()
    plan = build(d, recs)
    for day, load in zip(plan["itinerary"], plan["travel_load"]):
        legs = [int(i["end"][:2]) * 60 + int(i["end"][3:]) - int(i["start"][:2]) * 60 - int(i["start"][3:])
                for i in day["items"] if i["kind"] == "travel"]
        assert load["travel_min"] == sum(legs) and load["longest_leg_min"] == max(legs, default=0)


def test_a_trip_with_no_places_is_an_empty_valid_plan():
    d, recs = trip()
    d["confirmed"] = []
    plan = build(d, recs)
    assert plan["ok"] and all(day["items"] == [] for day in plan["itinerary"])


def test_a_meal_window_the_day_opens_after_is_a_warning_in_vietnamese():
    d, recs = trip(days=1, arrive_at="14:00")
    d["confirmed"] = d["confirmed"][:2]
    texts = [w["text"] for w in build(d, recs)["warnings"] if w["code"] == "meal_missed"]
    assert "Ngày 1: quá khung giờ trưa, chưa xếp bữa." in texts


def test_the_text_rendering_lists_each_day_a_free_meal_and_the_verdict():
    d, recs = trip(base={"place_id": "c1", "text": "c1"})
    text = render_text(build(d, recs))
    assert "Ngày 1 (2026-12-12)" in text and "Ngày 2 (2026-12-13)" in text and text.endswith("Hợp lệ.")
    assert "ăn trưa (tự chọn)" in text


def test_six_places_of_one_area_are_spread_over_both_days_and_the_plan_is_valid():
    recs = [spot(f"c{i}", CENTRE, i) for i in range(6)]
    d = decision([r["id"] for r in recs])
    plan = build(d, recs)
    assert plan["ok"], plan["violations"]
    assert all(len(day) >= 2 for day in visits(plan))


def test_a_sunrise_place_opens_a_later_day_early_instead_of_failing_the_plan():
    recs = [spot("c1", CENTRE, 0), spot("c2", CENTRE, 1), spot("c3", CENTRE, 2),
            spot("cloud", CENTRE, 3, hours=None, features={"cloud_hunting": "present"})]
    plan = build(decision([r["id"] for r in recs]), recs)
    assert plan["ok"], plan["violations"]
    day = next(i for i, v in enumerate(visits(plan)) if "cloud" in v)
    assert day >= 1 and plan["itinerary"][day]["window"][0] <= "07:00"
    assert any(w["code"] == "early_start" for w in plan["warnings"])


def test_a_trip_without_dates_uses_the_hours_every_open_day_shares_and_says_so():
    d, recs = trip(start_date=None, days=None)
    recs[0] = spot("c1", CENTRE, 0, hours={**all_days(), "mon": [["15:00", "21:00"]]})
    plan = build(d, recs)
    assert any(w["code"] == "hours_vary" and "c1" in w["text"] for w in plan["warnings"])
    first = next(i for day in plan["itinerary"] for i in day["items"] if i.get("place_id") == "c1" and i["kind"] == "visit")
    assert first["start"] >= "15:00"


def test_an_evening_only_place_goes_on_the_long_day_and_the_rest_fills_the_short_last_day():
    evening = all_days("18:00", "22:00")
    recs = [spot("c0", CENTRE, 0, hours=evening)] + [spot(f"c{i}", CENTRE, i) for i in range(1, 6)]
    plan = build(decision([r["id"] for r in recs]), recs)
    assert plan["ok"], plan["violations"]
    day1, day2 = visits(plan)
    assert "c0" in day1 and day2


def test_two_places_that_both_want_the_evening_share_a_day_by_giving_up_one_pin():
    from plan_fixtures import day_ctx

    from planning.build import _unpin
    from planning.route import order_day
    from planning.validate import validate
    music = {"live_music": "present"}                    # both want 18:00-20:00 on a day open until 21:00
    cx = day_ctx([rec("m1", 1, 1, features=music, visit=(60, 120, 150)), rec("m2", 1, 1, features=music, visit=(60, 120, 150))])
    r = order_day(["m1", "m2"], cx)
    assert validate([cx], [r], [], set(), None, None)    # as pinned, the day cannot hold both
    cx2, r2, dropped = _unpin(cx, r, ["m1", "m2"], [], None, None)
    assert len(dropped) == 1 and validate([cx2], [r2], [], set(), None, None) == []


def test_a_plan_that_gave_up_a_pin_still_passes_the_check_it_is_confirmed_with():
    """The pin was dropped on purpose and the user was told; re-validating the same plan later must agree."""
    from plan_fixtures import day_ctx

    from planning.build import _unpin
    from planning.route import order_day
    from planning.validate import validate
    from dataclasses import replace
    music = {"live_music": "present"}
    cx = day_ctx([rec("m1", 1, 1, features=music, visit=(60, 120, 150)), rec("m2", 1, 1, features=music, visit=(60, 120, 150))])
    _, r, dropped = _unpin(cx, order_day(["m1", "m2"], cx), ["m1", "m2"], [], None, None)
    assert validate([cx], [replace(r, unpinned=tuple(dropped))], [], set(), None, None) == []      # original ctx, pins intact
    assert validate([cx], [r], [], set(), None, None)                                                # undeclared: still refused
