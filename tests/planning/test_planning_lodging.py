import pytest
from plan_fixtures import CFG, decision, rec, stay

from planning.lodging import candidates, from_record, price_cap, search_area, shortlist, sieve
from planning.places import build_places

CENTRE = (11.9404, 108.4583)


def place(r):
    (p,), _ = build_places(decision([r["id"]]), {r["id"]: r}, CFG)
    return p


def by(*recs):
    return {r["id"]: place(r) for r in recs}


def test_search_area_is_the_visit_weighted_centre_of_one_tight_cluster():
    a = by(rec("a", 11.94, 108.45, visit=(10, 10, 10)), rec("b", 11.941, 108.451, visit=(10, 100, 10)))
    [centre] = search_area(a, "motorbike", CFG)
    assert centre["lat"] == pytest.approx(11.9406, abs=1e-3)  # pulled toward b's longer typical visit
    assert centre["radius_km"] == CFG.radius_km["motorbike"]


def test_places_far_apart_split_into_two_centres():
    a = by(rec("a", 11.94, 108.45), rec("b", 11.941, 108.451), rec("c", 11.60, 108.10))
    assert len(search_area(a, "car", CFG)) == 2


def test_no_places_has_no_search_area():
    assert search_area({}, "car", CFG) == []


def test_price_cap_is_the_lodging_share_of_budget_over_the_nights_or_unknown():
    assert price_cap({"budget_vnd": 3_000_000, "days": 4, "people": 2}, 3, CFG) == round(24_000_000 * CFG.lodging_share / 3)
    assert price_cap({"budget_vnd": None}, 3, CFG) is None
    assert price_cap({"budget_vnd": 1_000_000}, 0, CFG) is None


def cand(i, reviews=10, price=None):
    return {"id": f"h{i}", "name": f"Homestay {i}", "lat": CENTRE[0] + i * 0.001, "lng": CENTRE[1], "rating": 4.5,
           "reviews": reviews, "price_vnd": price}


def test_sieve_drops_too_few_reviews_and_evidence_against_but_keeps_what_it_cannot_verify():
    parking = stay("h2", *CENTRE, voices=20, features={"parking": "present"})
    raw = [from_record(stay("h0", *CENTRE, voices=1)), from_record(stay("h1", *CENTRE, voices=20)), from_record(parking)]
    hard = [{"feature": "parking", "op": "ne", "value": "present"}]
    out = sieve(raw, hard, CFG.min_reviews)
    assert [(c["id"], c["unverified"]) for c in out] == [("h1", ["parking"])]  # h0: too few reviews; h2: evidence


def test_shortlist_keeps_the_k_candidates_closest_to_any_centre():
    raw = [cand(i) for i in range(10)]
    centres = [{"lat": CENTRE[0], "lng": CENTRE[1], "radius_km": 3.0}]
    assert [c["id"] for c in shortlist(raw, centres, 3)] == ["h0", "h1", "h2"]


def test_candidates_drops_a_stay_outside_every_centres_search_radius():
    places = by(rec("a", *CENTRE))
    far = stay("far", 11.60, 108.10)
    assert candidates(places, decision(["a"]), CFG, [far]) == []


def test_candidates_cover_two_centres_and_hold_the_price_cap():
    places = by(rec("a", *CENTRE), rec("b", 11.60, 108.10))
    cap = round(3_000_000 * 3 * 2 * CFG.lodging_share / 2)
    stays = [stay("h0", *CENTRE), stay("h1", 11.6005, 108.10, price=cap), stay("h2", *CENTRE, price=cap + 1)]
    out = candidates(places, decision(["a", "b"], budget=3_000_000, days=3), CFG, stays)
    assert sorted(c["id"] for c in out) == ["h0", "h1"]


def test_no_places_means_no_candidates():
    assert candidates({}, decision([]), CFG, [stay("h0", *CENTRE)]) == []


from planning.lodging import progress_event


def test_progress_event_names_every_candidate_with_its_price():
    ev = progress_event([cand(0, price=300000), cand(1)], baseline_travel_min=120)
    assert ev == {"event": "progress", "stage": "lodging_scored",
                 "candidates": [{"id": "h0", "name": "Homestay 0", "price_vnd": 300000},
                                {"id": "h1", "name": "Homestay 1", "price_vnd": None}],
                 "baseline_travel_min": 120}
