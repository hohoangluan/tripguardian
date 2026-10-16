"""Lodging by taste (docs/PLANNING.md ⓐ): served stays only, taste before location, unknown never penalised, evidence
against a hard filter drops, the trip's price cap holds; a lodging the user has (booked, or picked at Lựa chọn)
anchors every day."""

import pytest
from plan_fixtures import CENTRE, CFG, FakeLive, decision, fake_matrix, no_geocode, rec, sample_trip

from planning.engine import Engine
from planning.lodging import booked, candidates, from_record, rank, with_booked_base
from planning.places import build_places, resolve_point
from planning.session import Store

QUIET = {"feature": "noise", "value": "quiet", "context": None, "weight": 1.0, "source": "user"}
LABELS = {"feature": {"noise": "Độ ồn", "kids": "Hợp trẻ em", "steep_or_stairs": "Dốc, bậc thang"},
          "value": {"quiet": "yên tĩnh"}}


def stay(pid, i, features=None, voices=20, price=None, night=None):
    r = rec(pid, CENTRE[0] + i * 0.001, CENTRE[1], group="stay", features=features, name=f"Stay {pid}")
    r["provenance"] = {"voices": voices, "as_of": "2026-10-01", "rating_trend": {"recent_mean": 4.6}}
    r["operation"]["price_per_person"] = {"value": {"min_vnd": price}} if price else None
    r["operation"]["price_per_night"] = ({"value": night, "status": "VERIFIED", "as_of": "2026-10-08",
                                          "source": "gmaps_list", "kind": "estimate"} if night else None)
    return r


def trip(soft=(QUIET,), **kw):
    d = decision(["a"], **kw)
    d["trip_context"]["soft_weights"] = list(soft)
    return d


def places():
    r = rec("a", *CENTRE)
    (p,), _ = build_places(decision(["a"]), {"a": r}, CFG)
    return {"a": p}


def many_stays(n, **kw):
    return [stay(f"s{i}", i % 10, **kw) for i in range(n)]


def test_candidates_are_the_served_stays_in_the_area():
    far = rec("far", CENTRE[0] + 0.5, CENTRE[1], group="stay", name="Far")
    far["provenance"] = {"voices": 20}
    out = candidates(places(), trip(), CFG, many_stays(3) + [far, rec("cafe", *CENTRE)])
    assert {c["source"] for c in out} == {"corpus"} and {c["id"] for c in out} == {"s0", "s1", "s2"}


def test_no_served_stay_gives_no_candidate():
    assert candidates(places(), trip(), CFG, [rec("cafe", *CENTRE)]) == []


def test_the_price_a_night_from_the_hotel_list_wins_over_the_review_reference():
    c = from_record(stay("s", 1, price=80000, night=467000))
    assert (c["price_vnd"], c["price_at"]) == (467000, "2026-10-08")
    assert from_record(stay("s", 1, price=80000))["price_vnd"] is None


def test_a_lodging_that_fits_the_taste_ranks_above_a_nearer_one_that_does_not():
    fits = stay("quiet", 5, features={"noise": "quiet"})
    near = stay("near", 0)
    cands = candidates(places(), trip(), CFG, [fits, near])
    out = rank(cands, trip(), {"quiet": 25, "near": 2}, CFG, LABELS)
    assert [c["id"] for c in out] == ["quiet", "near"]
    assert out[0]["fit"] == [{"text": "Độ ồn: yên tĩnh", "mentions": 3, "quote": None, "feature": "noise"}]


def test_unknown_is_not_penalised_but_evidence_against_a_wish_is():
    loud = stay("loud", 1, features={"noise": "loud"})
    blank = stay("blank", 1)
    d = trip(soft=[QUIET, {**QUIET, "feature": "steep_or_stairs", "value": "present", "weight": -1.0}])
    stairs = stay("stairs", 1, features={"steep_or_stairs": "present"})
    out = {c["id"]: c["score"] for c in rank([from_(loud), from_(blank), from_(stairs)], d, {}, CFG)}
    assert out["blank"] > out["stairs"]  # avoided and confirmed: a minus
    assert out["blank"] == out["loud"]    # another value than the loved one is no evidence against it


def from_(r):
    return from_record(r)


def test_who_travels_along_counts_as_a_wish():
    d = trip(soft=[])
    d["trip_context"]["context"]["companions"] = ["kids"]
    kid = stay("kid", 1, features={"kids": "suitable"})
    out = rank([from_(kid), from_(stay("other", 1))], d, {}, CFG, LABELS)
    assert out[0]["id"] == "kid" and out[0]["fit"][0]["text"] == "Hợp trẻ em"


def test_a_physical_hard_filter_drops_unknown_and_failing_evidence():
    hard = [{"feature": "steep_or_stairs", "op": "ne", "value": "present"}]
    stays = [stay("stairs", 1, features={"steep_or_stairs": "present"}), stay("flat", 2),
             stay("level", 3, features={"steep_or_stairs": "absent"})]
    out = candidates(places(), trip(hard=hard), CFG, stays)
    assert {c["id"] for c in out} == {"level"}
    assert all(c["unverified"] == [] for c in out)


CARD = {"polarity": {"noise": ["quiet", "moderate", "loud"], "cleanliness": ["clean", "dirty"],
                     "parking": ["easy", "hard"], "steep_or_stairs": ["absent", "present"]},
        "center": {"name": "trung tâm Đà Lạt", "lat": CENTRE[0], "lng": CENTRE[1]}, "near_min": 12,
        "speed_kmh": {"motorbike": 25, "car": 25, "walk": 22}, "road_factor": 1.4}


def engine(recs):
    return Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                  sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), background=False, labels=LABELS, card_cfg=CARD)


def only_card(r, **kw):
    d, recs = sample_trip(**kw)
    out = engine(recs + [r]).lodging_options({**d, "confirmed": []})
    return next(c for c in out["candidates"] if c["id"] == r["id"])


def test_a_lodging_card_has_the_kind_area_and_rating_like_any_place_card():
    r = stay("s", 3)
    r["identity"].update({"category": "Khách sạn 3 sao", "area": "Phường 1"})
    c = only_card(r)
    assert (c["category"], c["area"], c["rating"]) == ("Khách sạn 3 sao", "Phường 1", 4.6)  # rating: recent_mean


def test_the_card_says_why_it_suits_from_what_reviewers_confirm_when_the_user_said_nothing():
    c = only_card(stay("s", 3, features={"noise": "quiet", "cleanliness": "clean", "steep_or_stairs": "absent"}))
    texts = [w["text"] for w in c["why"]]
    assert "Độ ồn: yên tĩnh, 3 người nhắc" in texts and any(t.startswith("cleanliness: clean") for t in texts)
    assert not any("steep" in (w["sid"] or "") for w in c["why"])  # "absent stairs" is not a strength to show
    assert len(c["why"]) <= 4 and all(w["sid"] for w in c["why"] if "Gần" not in w["text"])


def test_what_the_user_wants_comes_first_in_why():
    d, recs = sample_trip()
    d["trip_context"]["soft_weights"] = [QUIET]
    r = stay("s", 3, features={"noise": "quiet", "cleanliness": "clean"})
    out = engine(recs + [r]).lodging_options({**d, "confirmed": []})
    assert out["candidates"][0]["why"][0]["sid"] == "noise"
    assert [w["sid"] for w in out["candidates"][0]["why"]].count("noise") == 1


def test_the_card_names_the_distance_to_the_centre_and_says_near_when_it_is():
    c = only_card(stay("s", 3))
    assert c["location"]["center"] == "trung tâm Đà Lạt" and c["location"]["minutes"] == 1
    assert "Gần trung tâm Đà Lạt, ≈1 phút (ước tính)" in [w["text"] for w in c["why"]]
    far = stay("far", 0)
    far["identity"].update({"lat": 11.9029, "lng": 108.4482})  # about 4 km south
    cf = only_card(far)
    assert cf["location"]["minutes"] > 1 and cf["location"]["km"] > 3
    assert not any("Gần" in w["text"] for w in cf["why"])


def test_the_bad_sides_reviewers_confirm_are_the_tradeoffs():
    c = only_card(stay("s", 3, features={"parking": "hard", "noise": "quiet"}))
    assert [t["sid"] for t in c["tradeoffs"]] == ["parking"] and "theo 3 người" in c["tradeoffs"][0]["text"]
    assert only_card(stay("t", 3, features={"noise": "quiet"}))["tradeoffs"] == []


def test_the_card_says_how_sure_it_is_from_the_number_of_reviewers():
    for voices, level in ((50, "high"), (20, "medium"), (6, "low")):
        c = only_card(stay("s", 3, voices=voices))
        assert c["confidence"]["level"] == level and f"{voices} người" in c["confidence"]["reason"]


def test_no_budget_known_puts_the_price_in_the_tradeoffs():
    c = only_card(stay("s", 3, night=500000))
    assert any("500" in t["text"] for t in c["tradeoffs"])


def test_the_engine_ranks_served_stays_and_leaves_out_one_over_the_cap():
    d, recs = sample_trip(budget=1_000_000)  # 2 people x 2 days -> 1 night: cap 1.2M
    d["trip_context"]["soft_weights"] = [QUIET]
    stays = [stay("s_quiet", 3, features={"noise": "quiet"}, night=500000), stay("s_plain", 0, night=2_500_000)]
    e = engine(recs + stays)
    sid = e.create(d, None)["id"]
    lod = e.lodging(sid)
    assert lod["status"] == "ready"
    assert [c["id"] for c in lod["candidates"]] == ["s_quiet"]  # s_plain: its price a night is over the cap
    (c,) = lod["candidates"]
    assert c["source"] == "corpus" and c["fit"] == [{"text": "Độ ồn: yên tĩnh", "mentions": 3, "quote": None}]
    assert c["avg_min"] is not None and c["price_vnd"] == 500000 and c["price_at"] == "2026-10-08"


def test_lodging_options_rank_the_stays_around_a_selection_without_a_session():
    d, recs = sample_trip()
    d["trip_context"]["soft_weights"] = [QUIET]
    e = engine(recs + [stay("s_quiet", 3, features={"noise": "quiet"}), stay("s_plain", 0)])
    out = e.lodging_options(d)
    assert out["status"] == "ready" and [c["id"] for c in out["candidates"]] == ["s_quiet", "s_plain"]
    assert not e._base  # no session was made
    d["trip_context"]["context"].update({"lodging_booked": "yes", "lodging": {"text": "X", "lat": 11.93, "lng": 108.42}})
    assert [c["id"] for c in e.lodging_options(d)["candidates"]] == ["s_quiet", "s_plain"]  # booked: may still change it


def test_lodging_options_list_the_stays_by_taste_before_any_place_is_chosen():
    d, recs = sample_trip()
    d["trip_context"]["soft_weights"] = [QUIET]
    e = engine(recs + [stay("s_quiet", 3, features={"noise": "quiet"}), stay("s_plain", 0)])
    out = e.lodging_options({**d, "confirmed": []})
    assert out["status"] == "ready" and [c["id"] for c in out["candidates"]] == ["s_quiet", "s_plain"]
    assert all(c["avg_min"] is None for c in out["candidates"])  # no place to measure to yet


def test_the_list_holds_every_stay_one_page_at_a_time():
    d, recs = sample_trip()
    e = engine(recs + many_stays(CFG.lodging_list_k + 5))
    first = e.lodging_options({**d, "confirmed": []})
    assert len(first["candidates"]) == CFG.lodging_list_k and first["total"] == CFG.lodging_list_k + 5
    rest = e.lodging_options({**d, "confirmed": []}, offset=CFG.lodging_list_k)
    assert len(rest["candidates"]) == 5
    assert not {c["id"] for c in first["candidates"]} & {c["id"] for c in rest["candidates"]}
    assert CFG.lodging_list_k > CFG.lodging_k


def test_stays_around_the_selection_come_first_then_every_other_stay():
    d, recs = sample_trip()
    far = stay("s_far", 0)
    far["identity"].update({"lat": 12.5, "lng": 109.5})  # outside any search area around the chosen places
    e = engine(recs + [stay("s_near", 0), far])
    out = e.lodging_options(d)
    assert [c["id"] for c in out["candidates"]] == ["s_near", "s_far"] and out["total"] == 2
    assert out["candidates"][0]["avg_min"] is not None and out["candidates"][1]["avg_min"] is None


def test_a_lodging_picked_at_lua_chon_anchors_every_day_with_its_price():
    d, recs = sample_trip()
    d["lodging"] = {"kind": "corpus", "id": "s_plain", "text": "Stay s_plain", "lat": CENTRE[0], "lng": CENTRE[1],
                    "price_vnd": 467000}
    point = booked(d)
    assert (point["id"], point["place_id"], point["price_vnd"]) == ("@home", "s_plain", 467000)
    assert with_booked_base(d)["trip_context"]["context"]["base"]["text"] == "Stay s_plain"
    e = engine(recs + [stay("s_plain", 0)])
    out = e.create(d, None)
    assert out["view"]["lodging"]["status"] == "booked" and out["view"]["state"]["lodging_point"]["price_vnd"] == 467000
    sid = out["id"]
    e.act(sid, {"type": "pick_variant", "id": e.variants(sid)[0]["id"]})
    for day in e.load(sid)["view"]["itinerary"]:
        legs = [i for i in day["items"] if i["kind"] == "travel"]
        if legs:  # every day leaves the lodging and comes back to it
            assert legs[0]["from"] == "@home" and legs[-1]["to"] == "@home"


def test_a_booked_lodging_anchors_every_day_and_nothing_is_suggested():
    d, recs = sample_trip()
    hotel = {"place_id": None, "text": "Ana Mandara Villas", "lat": 11.9301, "lng": 108.4205, "province": None,
             "kind": "address"}
    d["trip_context"]["context"].update({"lodging_booked": "yes", "lodging": hotel})
    assert booked(d)["id"] == "@home"
    assert with_booked_base(d)["trip_context"]["context"]["base"] == {"place_id": None, "text": "Ana Mandara Villas",
                                                                      "lat": 11.9301, "lng": 108.4205}
    e = engine(recs)
    out = e.create(d, None)
    assert out["view"]["lodging"] == {"status": "booked", "candidates": []}
    state = out["view"]["state"]
    assert state["lodging_touched"] and state["lodging_point"]["source"] == "user"
    assert (state["lodging_point"]["lat"], state["lodging_point"]["lng"]) == (11.9301, 108.4205)
    sid = out["id"]
    e.act(sid, {"type": "pick_variant", "id": e.variants(sid)[0]["id"]})
    first = next(i for i in e.load(sid)["view"]["itinerary"][0]["items"] if i["kind"] == "travel")
    assert first["kind"] == "travel" and first["from"] == "@home"  # the day leaves from the hotel
    assert e.lodging(sid)["status"] == "booked"


def test_a_base_with_a_point_needs_no_geocoding():
    pt, why = resolve_point({"place_id": None, "text": "Ana Mandara", "lat": 11.93, "lng": 108.42}, {},
                            lambda t: pytest.fail("no geocoding"))
    assert why is None and (pt.lat, pt.lng, pt.source) == (11.93, 108.42, "user")


def test_a_lodging_picked_at_lua_chon_replaces_the_one_the_trip_already_had():
    d, _ = sample_trip()
    d["trip_context"]["context"].update({"lodging_booked": "yes", "lodging": {"text": "Đã đặt", "lat": 11.93, "lng": 108.42}})
    assert (booked(d)["text"], booked(d)["lat"]) == ("Đã đặt", 11.93)
    d["lodging"] = {"kind": "address", "id": None, "text": "Chỗ mới", "lat": 11.95, "lng": 108.45, "price_vnd": None}
    assert (booked(d)["text"], booked(d)["lat"]) == ("Chỗ mới", 11.95)  # one lodging for the trip: the pick wins
    assert with_booked_base(d)["trip_context"]["context"]["base"]["text"] == "Chỗ mới"
