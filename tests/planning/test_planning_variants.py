import json

from plan_fixtures import CFG, SOUTH, FakeLive, fake_matrix, fixed_sun, no_geocode, sample_trip, spot

from planning.variants import build_variants

WET = {"weather_exposed": "present"}


def run(d, recs, weather=None):
    return build_variants(d, recs, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                          sun_fn=fixed_sun, weather=weather)


def day_of(variant, pid):
    return next(d["day"] for d in variant["itinerary"] for i in d["items"] if i.get("place_id") == pid)


def wet_south():
    """The sample trip with the three southern places open to the weather, and a last day long enough to hold
    either cluster (the default 15:00 departure leaves no room to swap them)."""
    d, recs = sample_trip(checkout_at="20:00")
    recs[4:7] = [spot(f"s{i + 1}", SOUTH, i, features=WET) for i in range(3)]
    return d, recs


def test_a_plain_trip_whose_objectives_agree_gives_one_variant_and_says_so():
    d, recs = sample_trip()                                   # normal pace: least_travel and diverse
    out = run(d, recs)
    assert out["ok"] and [v["objective"] for v in out["variants"]] == ["least_travel"]
    assert "variants_same" in {w["code"] for w in out["warnings"]}


def test_rain_where_the_least_travel_plan_puts_the_open_air_places_gives_a_second_variant_that_moves_them():
    d, recs = wet_south()
    rainy_day = day_of(run(d, recs)["variants"][0], "s1")
    date = ["2026-12-12", "2026-12-13"][rainy_day - 1]
    out = run(d, recs, weather={date: {"rain_prob": 0.9, "source": "open-meteo", "fetched_at": "t"}})
    by_obj = {v["objective"]: v for v in out["variants"]}
    assert set(by_obj) == {"least_travel", "weather_robust"}
    assert day_of(by_obj["least_travel"], "s1") == rainy_day and day_of(by_obj["weather_robust"], "s1") != rainy_day
    assert by_obj["weather_robust"]["metrics"]["rain_exposed"] < by_obj["least_travel"]["metrics"]["rain_exposed"]
    assert out["provenance"]["weather"] == [{"source": "open-meteo", "fetched_at": "t"}]


def test_every_variant_carries_its_itinerary_measures_robustness_and_backups_and_the_table_compares_them():
    d, recs = wet_south()
    out = run(d, recs, weather={"2026-12-12": {"rain_prob": 0.9}, "2026-12-13": {"rain_prob": 0.9}})
    assert out["chosen"] is None and out["back_to_decision"] is None
    for i, v in enumerate(out["variants"]):
        assert v["id"] == f"v{i + 1}" and len(v["itinerary"]) == 2
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
    assert out["back_to_decision"] == {"reason": "no_valid_variant", "places": ["gone"],
                                       "reasons": [{"kind": "anchor", "place_id": "gone", "day": None, "minutes": 0}]}
    assert [v["kind"] for v in out["violations"]] == ["anchor"]


def test_a_day_window_violation_names_the_places_crowded_onto_that_day():
    d, recs = sample_trip(days=1, checkout_at="12:00")        # one short day, too little room for eight places
    out = run(d, recs)
    assert not out["ok"] and [v["kind"] for v in out["violations"]] == ["day_window"]
    assert out["back_to_decision"]["places"]                     # not empty: day_window carries no place_id itself
    assert [r["kind"] for r in out["back_to_decision"]["reasons"]] == ["day_window"]


def test_a_trip_with_no_places_is_one_empty_solid_variant():
    d, recs = sample_trip()
    d["confirmed"] = []
    (v,) = run(d, recs)["variants"]
    assert all(day["items"] == [] for day in v["itinerary"]) and v["robustness"]["level"] == "solid"
    assert v["backups"] == {"places": [], "on_delay": []}


def test_a_variant_that_does_not_fit_the_days_is_dropped_and_named():
    d, recs = sample_trip(checkout_at="20:00", checkin_at="11:00", max_leg=10)
    recs[4:7] = [spot(f"s{i + 1}", SOUTH, i, features=WET) for i in range(3)]
    d["trip_context"]["context"]["checkout_at"] = None          # the last day ends at 15:00 again: too short for the
                                                               # 5-place centre cluster, and a max_leg_min of 10
                                                               # forbids combining it with the south cluster either
    out = run(d, recs, weather={"2026-12-13": {"rain_prob": 0.9}})    # rain where the open-air places go
    codes = [w["code"] for w in out["warnings"]]
    assert [v["objective"] for v in out["variants"]] == ["least_travel"]
    want = {"code": "variant_invalid", "text": "Vững trước thời tiết: không xếp được lịch hợp lệ, bỏ phương án này."}
    assert want in out["warnings"]
    assert codes.count("variants_same") == 1                 # diverse did agree with least_travel: that one is
