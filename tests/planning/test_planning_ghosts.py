from plan_fixtures import CENTRE, CFG, decision, prepared, spot

from planning.build import schedule_trip
from planning.ghosts import fill, pool


def setup():
    recs = [spot("c1", CENTRE, 0), spot("c2", CENTRE, 1),
            spot("r1", CENTRE, 2, usable=("meal", "backup"), group="restaurant", name="Lẩu A"),
            spot("r2", CENTRE, 3, usable=("meal", "backup"), group="restaurant", name="Bánh căn B"),
            spot("k1", CENTRE, 4, usable=("meal", "backup"), group="dessert", name="Kem C")]
    d = decision(["c1", "c2"], days=1, base={"place_id": None, "text": "home", "lat": CENTRE[0], "lng": CENTRE[1]})
    trip = prepared(d, recs)
    return trip, recs, d


def test_an_empty_meal_slot_gets_a_real_open_place_never_a_snack_shop():
    trip, recs, d = setup()
    s = schedule_trip(trip)
    slots = fill(s.ctxs, s.results, pool(recs, d, CFG), {"c1", "c2"}, set(), [], trip.points)
    lunch = next(x for x in slots if x["kind"] == "lunch")
    assert lunch["items"] and lunch["items"][0]["place_id"] in {"r1", "r2"}
    assert "k1" not in {i["place_id"] for x in slots if x["kind"] in {"lunch", "dinner"} for i in x["items"]}


def test_breakfast_prefers_a_breakfast_dish_and_dismissed_places_stay_hidden():
    trip, recs, d = setup()
    s = schedule_trip(trip)
    slots = fill(s.ctxs, s.results, pool(recs, d, CFG), {"c1", "c2"}, {"r2"}, [], trip.points)
    assert all(i["place_id"] != "r2" for x in slots for i in x["items"])


def test_no_place_is_suggested_twice_in_a_day():
    trip, recs, d = setup()
    s = schedule_trip(trip)
    slots = fill(s.ctxs, s.results, pool(recs, d, CFG), {"c1", "c2"}, set(), [], trip.points)
    firsts = [x["items"][0]["place_id"] for x in slots if x["items"]]
    assert len(firsts) == len(set(firsts))


def run(recs, d, taken=("c1", "c2"), soft=(), dismissed=(), **fill_kw):
    trip = prepared(d, recs)
    s = schedule_trip(trip)
    return fill(s.ctxs, s.results, pool(recs, d, CFG), set(taken), set(dismissed), list(soft), trip.points, **fill_kw)


def lunch_of(slots):
    return next(x for x in slots if x["kind"] == "lunch")


def test_an_unknown_hard_filter_empties_the_pool_unless_it_says_flag():
    _, recs, d = setup()
    veg = {"feature": "vegetarian_options", "op": "eq", "value": "yes"}
    for hf in (veg, {**veg, "unknown_policy": "exclude"}, {"feature": "fit.wheelchair", "op": "eq", "value": "present"},
               {"feature": "fit.wheelchair", "op": "eq", "value": "present", "unknown_policy": "flag"}):
        d["trip_context"]["hard_filters"] = [hf]
        assert pool(recs, d, CFG) == [], hf
    d["trip_context"]["hard_filters"] = [{**veg, "unknown_policy": "flag"}]
    assert {p.id for p in pool(recs, d, CFG)} == {"r1", "r2", "k1"}


def test_a_flagged_unknown_filter_marks_the_suggestion_unverified():
    _, recs, d = setup()
    recs[3]["service"] = {"vegetarian_options": {"value": "yes", "distribution": {"yes": 3}, "status": "VERIFIED", "n": 3}}
    d["trip_context"]["hard_filters"] = [{"feature": "vegetarian_options", "op": "eq", "value": "yes",
                                          "unknown_policy": "flag"}]
    items = {i["place_id"]: i for x in run(recs, d) for i in x["items"]}
    assert items["r1"]["unverified"] == ["vegetarian_options"]
    assert "unverified" not in items["r2"]


def test_a_place_with_unknown_or_shaky_hours_says_so():
    _, recs, d = setup()
    recs[2]["operation"]["hours"] = None
    recs[3]["operation"]["hours"]["status"] = "OUTDATED"
    items = {i["place_id"]: i for x in run(recs, d) for i in x["items"]}
    assert items["r1"]["hours_unknown"] is True
    assert items["r2"]["hours_unknown"] is True


def test_a_place_with_known_hours_carries_no_hours_flag():
    _, recs, d = setup()
    items = {i["place_id"]: i for x in run(recs, d) for i in x["items"]}
    assert "hours_unknown" not in items["r1"]


VEG = {"feature": "vegetarian_options", "value": "yes", "weight": 1}


def with_taste(recs):
    recs[2]["service"] = {"vegetarian_options": {"value": "yes", "distribution": {"yes": 3}, "status": "VERIFIED", "n": 3}}
    return recs


def test_a_wanted_dish_outranks_a_better_taste_fit():
    _, recs, d = setup()
    with_taste(recs)
    recs.append(spot("r3", CENTRE, 5, usable=("meal", "backup"), group="restaurant", name="Cơm D"))
    assert lunch_of(run(recs, d, soft=[VEG]))["items"][0]["place_id"] == "r1"
    d["trip_context"]["wishes"] = {"dishes": [{"dish": "Cơm", "quote": "muốn ăn cơm", "place_ids": []}]}
    assert lunch_of(run(recs, d, soft=[VEG]))["items"][0]["place_id"] == "r3"       # r3's name carries the dish
    d["trip_context"]["wishes"] = {"dishes": [{"dish": "bún bò", "quote": "q", "place_ids": ["r3"]}]}
    assert lunch_of(run(recs, d, soft=[VEG]))["items"][0]["place_id"] == "r3"       # named by id
    assert lunch_of(run(recs, d, soft=[VEG], wanted=[]))["items"][0]["place_id"] == "r1"      # an explicit empty list wins


def test_a_dish_a_chosen_place_already_serves_is_not_wanted():
    _, recs, d = setup()
    with_taste(recs)
    d["trip_context"]["wishes"] = {"dishes": [{"dish": "bún bò", "quote": "q", "place_ids": ["r2", "c1"]}]}
    assert lunch_of(run(recs, d, soft=[VEG]))["items"][0]["place_id"] == "r1"


def test_a_place_that_is_a_long_detour_between_the_stops_is_rejected():
    _, recs, d = setup()
    # about 14 road minutes from the stop before lunch (inside the radius), and as far again from the way on
    recs.append(spot("rf", (CENTRE[0] + 0.036, CENTRE[1]), 0, usable=("meal", "backup"), group="restaurant", name="Quán xa"))
    shown = {i["place_id"] for x in run(recs, d) for i in x["items"]}
    assert "rf" not in shown and "r1" in shown


def two_clusters():
    """Two clusters about 50 road minutes apart; 70 restaurants halfway, out of reach of both (and nearest the centroid)."""
    far = (CENTRE[0] + 0.15, CENTRE[1])
    mid = (CENTRE[0] + 0.075, CENTRE[1])
    eat = dict(usable=("meal", "backup"), group="restaurant")
    recs = [spot("c1", CENTRE, 0), spot("c2", CENTRE, 1), spot("s1", far, 0), spot("s2", far, 1),
            spot("rc", CENTRE, 3, name="Quán Trung Tâm", **eat), spot("rs", far, 3, name="Quán Xa", **eat)]
    recs += [spot(f"f{i}", mid, 0, name=f"Quán {i}", **eat) for i in range(70)]
    d = decision(["c1", "c2", "s1", "s2"], days=2, base={"place_id": None, "text": "home", "lat": CENTRE[0], "lng": CENTRE[1]})
    return recs, d, far


def test_every_cluster_of_a_spread_trip_has_its_pool_places_not_just_those_nearest_the_centroid():
    recs, d, _ = two_clusters()
    assert {p.id for p in pool(recs, d, CFG)} == {"rc", "rs"}       # the 70 halfway are beyond both radii


def test_lunch_after_the_far_cluster_is_offered_the_far_places():
    recs, _, far = two_clusters()
    far_day = decision(["s1", "s2"], days=1, base={"place_id": None, "text": "home", "lat": far[0], "lng": far[1]})
    lunch = lunch_of(run(recs, far_day, taken=("s1", "s2")))
    assert [i["place_id"] for i in lunch["items"]] == ["rs"]


def test_an_explicit_null_unknown_policy_stays_fail_closed():
    from planning.lodging import sieve
    from plan_fixtures import stay
    veg = {"feature": "vegetarian_options", "op": "eq", "value": "yes", "unknown_policy": None}
    _, recs, d = setup()
    d["trip_context"]["hard_filters"] = [veg]
    assert pool(recs, d, CFG) == []
    parking = {"feature": "parking", "op": "ne", "value": "present"}
    raw = [{"id": "h1", "rec": stay("h1", *CENTRE, voices=20), "reviews": 20}]
    assert [c["id"] for c in sieve(raw, [parking], 0)] == ["h1"]                              # no policy: lodging flags it
    assert sieve(raw, [{**parking, "unknown_policy": None}], 0) == []                       # explicit None: excluded, as before


def engine_for(recs, store):
    from plan_fixtures import FakeLive, fake_matrix, no_geocode
    from planning import Engine
    return Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=store, geocode_fn=no_geocode, matrix_fn=fake_matrix,
                  sun_fn=lambda *a: (360, 1050), background=False)


def placed(view):
    return {i.get("place_id") for day in view["itinerary"] for i in day["items"]}


def test_the_view_shows_faded_suggestions_that_stay_off_the_timeline():
    from planning.session import Store
    _, recs, d = setup()
    view = engine_for(recs, Store(None)).create(d)["view"]
    ghosts = [x for x in view["ghosts"] if x["items"]]
    assert ghosts and all(x["day"] == 0 for x in ghosts)
    assert not {i["place_id"] for x in ghosts for i in x["items"]} & placed(view)
    assert view["unplaced"] == [] and view["metrics"] is not None


def test_replay_rebuilds_an_accepted_suggestion(tmp_path):
    from planning.session import Store
    _, recs, d = setup()
    e = engine_for(recs, Store(tmp_path))
    out = e.create(d)
    ghost = next(x for x in out["view"]["ghosts"] if x["items"])["items"][0]["place_id"]
    view = e.act(out["id"], {"type": "add_from_backup", "place": ghost, "day": 0})["view"]
    assert ghost in placed(view)
    assert ghost not in {i["place_id"] for x in view["ghosts"] for i in x["items"]}
    fresh = engine_for(recs, Store(tmp_path))
    again = fresh.act(out["id"], {"type": "dismiss_suggestion", "place": "nothing"})["view"]
    assert ghost in placed(again)


def test_a_dismissed_suggestion_is_hidden_for_the_session_and_the_days_do_not_change():
    from planning.session import ActionError, Store
    import pytest
    _, recs, d = setup()
    e = engine_for(recs, Store(None))
    out = e.create(d)
    first = next(x for x in out["view"]["ghosts"] if x["items"])["items"][0]["place_id"]
    res = e.act(out["id"], {"type": "dismiss_suggestion", "place": first})
    assert res["diff"]["scope"] == "none"
    assert res["view"]["itinerary"] == out["view"]["itinerary"]
    assert first not in {i["place_id"] for x in res["view"]["ghosts"] for i in x["items"]}
    assert res["view"]["state"]["dismissed"] == [first]
    with pytest.raises(ActionError):
        e.act(out["id"], {"type": "dismiss_suggestion"})
    undone = e.act(out["id"], {"type": "undo"})["view"]
    assert first in {i["place_id"] for x in undone["ghosts"] for i in x["items"]}
