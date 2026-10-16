from plan_fixtures import CFG, SOUTH, FakeLive, fake_matrix, fixed_sun, no_geocode, sample_trip, stay

from planning.variants import build_lodging_variants


def hit(i, price=None, lat=None, lng=None):
    return stay(f"h{i}", lat if lat is not None else SOUTH[0] + i * 0.001, lng if lng is not None else SOUTH[1],
                name=f"Homestay {i}", price=price)


def run(d, recs, stays, weather=None):
    return build_lodging_variants(d, recs + stays, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode,
                                  matrix_fn=fake_matrix, sun_fn=fixed_sun, weather=weather)


def test_without_any_anchor_point_the_no_lodging_option_wins_least_travel():
    d, recs = sample_trip()  # no base / entry / exit: days already start and end nowhere
    out = run(d, recs, [hit(0)])
    lt = next(v for v in out["variants"] if v["id"] == "main")
    assert lt["lodging"]["id"] is None
    assert any(r["id"] is None for r in out["lodging"]["candidates"])
    assert any(r["id"] == "h0" for r in out["lodging"]["candidates"])


def test_no_served_stay_in_the_area_still_gives_the_no_lodging_variant():
    d, recs = sample_trip()
    out = run(d, recs, [])
    assert out["ok"] and all(r["id"] is None for r in out["lodging"]["candidates"])
    assert "lodging_unavailable" in {w["code"] for w in out["warnings"]}


def test_low_cost_never_prefers_the_pricier_candidate_when_travel_time_is_tied():
    d, recs = sample_trip(budget=3_000_000, days=3)
    cheap = hit(0, price=200_000, lat=SOUTH[0], lng=SOUTH[1])
    pricey = hit(1, price=2_000_000, lat=SOUTH[0], lng=SOUTH[1])
    out = run(d, recs, [cheap, pricey])
    main, = out['variants']
    assert main['id'] == 'main'
    assert main['lodging']['id'] != 'h1'
    assert {c['id']: c['price_vnd'] for c in out['lodging']['candidates'] if c['id']} == {'h0': 200000, 'h1': 2000000}


def test_the_same_input_gives_the_same_output():
    d, recs = sample_trip()
    a = run(d, recs, [hit(0), hit(1)])
    b = run(d, recs, [hit(0), hit(1)])
    assert a == b


def test_no_lodging_is_not_counted_as_an_unknown_cost():
    d, recs = sample_trip()  # 8 places, all with no known cost
    out = run(d, recs, [hit(0, price=None)])
    lt = next(v for v in out["variants"] if v["id"] == "main")
    assert lt["lodging"]["id"] is None
    assert lt["metrics"]["cost_unknown"] == 8  # the 8 places only, not +1 for "no lodging" having no price


def test_no_valid_schedule_for_any_lodging_goes_back_to_place_decision():
    d, recs = sample_trip()
    d["confirmed"].append({"id": "gone", "name": "Gone", "role": "anchor", "flags": [], "relaxed": []})
    out = run(d, recs, [hit(0)])
    assert not out["ok"] and out["lodging"] is None and out["back_to_decision"]["places"] == ["gone"]
