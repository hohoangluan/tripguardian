import json
from dataclasses import replace

from plan_fixtures import CFG, SOUTH, FakeLive, fake_matrix, fixed_sun, no_geocode, sample_trip, spot

from planning.variants import build_variants

WET = {"weather_exposed": "present"}


def run(d, recs, weather=None, cfg=CFG):
    return build_variants(d, recs, cfg=cfg, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                          sun_fn=fixed_sun, weather=weather)


def day_of(variant, pid):
    return next(d["day"] for d in variant["itinerary"] for i in d["items"] if i.get("place_id") == pid)


def wet_south():
    """The sample trip with the three southern places open to the weather, and a last day long enough to hold
    either cluster (the default 15:00 departure leaves no room to swap them)."""
    d, recs = sample_trip(leave_at="20:00")
    recs[4:7] = [spot(f"s{i + 1}", SOUTH, i, features=WET) for i in range(3)]
    return d, recs


def test_a_plain_trip_has_one_main_plan():
    d, recs = sample_trip()                                   # normal pace: least_travel and diverse
    out = run(d, recs)
    assert out["ok"] and [v["id"] for v in out["variants"]] == ["main"]
    assert out["overload"] is None


def test_rain_changes_measurements_without_adding_another_plan():
    d, recs = wet_south()
    rainy_day = day_of(run(d, recs)['variants'][0], 's1')
    date = ['2026-12-12', '2026-12-13'][rainy_day - 1]
    out = run(d, recs, weather={date: {'rain_prob': 0.9, 'source': 'open-meteo', 'fetched_at': 't'}})
    main, = out['variants']
    assert main['id'] == 'main' and out['overload'] is None
    assert main['metrics']['rain_exposed'] > 0
    assert {i['place_id'] for day in main['itinerary'] for i in day['items'] if i['kind'] == 'visit'} == {r['id'] for r in recs}
    assert out['provenance']['weather'] == [{'source': 'open-meteo', 'fetched_at': 't'}]


def test_every_variant_carries_its_itinerary_measures_robustness_and_backups_and_the_table_compares_them():
    d, recs = wet_south()
    out = run(d, recs, weather={"2026-12-12": {"rain_prob": 0.9}, "2026-12-13": {"rain_prob": 0.9}})
    assert out["chosen"] is None and out["back_to_decision"] is None
    for i, v in enumerate(out["variants"]):
        assert v["id"] in {"main", "fit", "travel", "cost"}
        assert len(v["itinerary"]) == 2
        assert v["robustness"]["level"] in ("solid", "feasible", "fragile")
        assert {"places", "on_delay"} <= set(v["backups"])
    rows = out["comparison"]
    assert [r["variant"] for r in rows] == [v["id"] for v in out["variants"]]
    assert min(r["travel_vs_best"] for r in rows) == 0
    wet = [p for v in out["variants"] for p in v["backups"]["places"] if "rain" in p["reasons"]]
    assert wet and all(p["none_text"] == "Không có phương án thay." for p in wet)     # the pool is empty


def test_the_same_input_gives_the_same_variants_and_the_output_is_plain_json():
    d, recs = wet_south()
    weather = {"2026-12-12": {"rain_prob": 0.9}}
    first = run(d, recs, weather)
    assert first == run(d, recs, weather) and json.loads(json.dumps(first)) == first


def test_without_a_forecast_the_output_says_weather_was_not_considered():
    d, recs = sample_trip()
    out = run(d, recs)
    assert "weather_unknown" in {w["code"] for w in out["warnings"]} and out["provenance"]["weather"] == []


def test_a_forecast_covering_only_some_days_still_says_weather_was_not_fully_considered():
    d, recs = sample_trip(days=2)
    out = run(d, recs, weather={"2026-12-12": {"rain_prob": 0.9}})       # day 2 has no entry
    assert "weather_unknown" in {w["code"] for w in out["warnings"]}


def test_forecast_entries_with_a_missing_or_null_fetched_at_or_a_null_day_do_not_crash_the_provenance_list():
    d, recs = sample_trip(days=2)
    weather = {"2026-12-12": {"rain_prob": 0.9, "source": "open-meteo", "fetched_at": None},
               "2026-12-13": None}
    out = run(d, recs, weather)
    assert out["provenance"]["weather"] == [{"source": "open-meteo", "fetched_at": None}]


def test_no_valid_variant_goes_back_to_place_decision_with_the_places_that_broke_it():
    d, recs = sample_trip()
    d["confirmed"].append({"id": "gone", "name": "Gone", "role": "anchor", "flags": [], "relaxed": []})
    out = run(d, recs)
    assert not out["ok"] and out["variants"] == [] and out["comparison"] == []
    assert out["back_to_decision"] == {"reason": "no_valid_variant", "places": ["gone"], "leftover": []}
    assert [v["kind"] for v in out["violations"]] == ["anchor"]


def test_short_day_offers_directions_with_explicit_drops():
    d, recs = sample_trip(days=1, leave_at="12:00")        # one short day, too little room for eight places
    out = run(d, recs)
    assert out["ok"]
    assert out['keep_all'] is None
    assert out['overload']['missing_min'] > 0
    assert any(v['available'] for v in out['variants'])
    assert all(v['dropped'] for v in out['variants'] if v['available'])


def test_a_trip_with_no_places_is_one_empty_solid_variant():
    d, recs = sample_trip()
    d["confirmed"] = []
    (v,) = run(d, recs)["variants"]
    assert all(day["items"] == [] for day in v["itinerary"]) and v["robustness"]["level"] == "solid"
    assert v["backups"] == {"places": [], "on_delay": []}


def test_an_objective_never_leaves_out_a_place_another_split_fits():
    d, recs = sample_trip(leave_at="20:00", arrive_at="10:00", max_leg=10)
    recs[4:7] = [spot(f"s{i + 1}", SOUTH, i, features=WET) for i in range(3)]
    # Five ordinary centre visits keep one cluster; meal venues are assigned independently.
    recs[-1]["usable_as"] = ["experience", "backup"]
    d["trip_context"]["context"]["leave_at"] = None          # the last day ends at 15:00 again: too short for the
                                                               # 5-place centre cluster, and a max_leg_min of 10
                                                               # forbids combining it with the south cluster either
    # A robust baseline isolates objective rejection from overload-profile composition.
    cfg = replace(CFG, fill_ratio=1.0, meal_durations={'lunch': 60, 'dinner': 60}, meals_per_day=2, meal_windows={k: v for k, v in CFG.meal_windows.items() if k != 'breakfast'})
    out = run(d, recs, weather={"2026-12-13": {"rain_prob": 0.9}}, cfg=cfg)
    codes = [w["code"] for w in out["warnings"]]
    assert [v["id"] for v in out["variants"]] == ["main"]
    # Keeping the open-air places off the rainy day would leave a centre place out: the layout keeps every place
    # (spec section 7: never drop while there is room), so weather_robust is the same plan, not an invalid one.
    assert "variant_invalid" not in codes
    assert {i["place_id"] for d in out["variants"][0]["itinerary"] for i in d["items"] if i["kind"] == "visit"} == \
        {r["id"] for r in recs}
    assert out["overload"] is None and [v["id"] for v in out["variants"]] == ["main"]                 # diverse did agree with least_travel: that one is
