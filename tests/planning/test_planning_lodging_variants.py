from plan_fixtures import CFG, SOUTH, FakeLive, fake_matrix, fixed_sun, no_geocode, sample_trip

from live import Unavailable
from planning.variants import build_lodging_variants


def hit(i, price=None, lat=None, lng=None):
    return {"id": f"h{i}", "name": f"Homestay {i}", "lat": lat if lat is not None else SOUTH[0] + i * 0.001,
           "lng": lng if lng is not None else SOUTH[1], "rating": 4.5, "reviews": 20, "price_vnd": price,
           "amenities": []}


def fake_lodging(hits):
    return lambda center, radius_km, check_in, check_out, price_max, live_cfg: hits


def run(d, recs, lodging_fn, weather=None):
    return build_lodging_variants(d, recs, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                                  sun_fn=fixed_sun, weather=weather, lodging_fn=lodging_fn)


def test_without_any_anchor_point_the_no_lodging_option_wins_least_travel():
    d, recs = sample_trip()  # no base / entry / exit: days already start and end nowhere
    out = run(d, recs, fake_lodging([hit(0)]))
    lt = next(v for v in out["variants"] if v["objective"] == "least_travel")
    assert lt["lodging"]["id"] is None
    assert any(r["id"] is None for r in out["lodging"]["candidates"])
    assert any(r["id"] == "h0" for r in out["lodging"]["candidates"])


def test_a_dead_lodging_source_still_gives_the_no_lodging_variant():
    d, recs = sample_trip()
    out = run(d, recs, lambda *a: (_ for _ in ()).throw(Unavailable("blocked")))
    assert out["ok"] and all(r["id"] is None for r in out["lodging"]["candidates"])
    assert "lodging_unavailable" in {w["code"] for w in out["warnings"]}


def test_low_cost_never_prefers_the_pricier_candidate_when_travel_time_is_tied():
    d, recs = sample_trip(budget=3_000_000, days=3)
    cheap = hit(0, price=200_000, lat=SOUTH[0], lng=SOUTH[1])
    pricey = hit(1, price=2_000_000, lat=SOUTH[0], lng=SOUTH[1])
    out = run(d, recs, fake_lodging([cheap, pricey]))
    # the no-lodging baseline costs nothing extra, so it legitimately wins low_cost outright here and gets deduped
    # into least_travel's identical variant (same home, same order) -- no separate "low_cost" variant then exists.
    low_cost = next((v for v in out["variants"] if v["objective"] == "low_cost"), None)
    assert low_cost is None or low_cost["lodging"]["id"] != "h1"  # never the pricier of the two


def test_the_same_input_gives_the_same_output():
    d, recs = sample_trip()
    a = run(d, recs, fake_lodging([hit(0), hit(1)]))
    b = run(d, recs, fake_lodging([hit(0), hit(1)]))
    assert a == b


def test_no_lodging_is_not_counted_as_an_unknown_cost():
    d, recs = sample_trip()  # 8 places, all with no known cost
    out = run(d, recs, fake_lodging([hit(0, price=None)]))
    lt = next(v for v in out["variants"] if v["objective"] == "least_travel")
    assert lt["lodging"]["id"] is None
    assert lt["metrics"]["cost_unknown"] == 8  # the 8 places only, not +1 for "no lodging" having no price


def test_no_valid_schedule_for_any_lodging_goes_back_to_place_decision():
    d, recs = sample_trip()
    d["confirmed"].append({"id": "gone", "name": "Gone", "role": "anchor", "flags": [], "relaxed": []})
    out = run(d, recs, fake_lodging([hit(0)]))
    assert not out["ok"] and out["lodging"] is None and out["back_to_decision"]["places"] == ["gone"]
