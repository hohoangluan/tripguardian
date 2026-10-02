import pytest
from plan_fixtures import CFG, decision, rec

from live import Unavailable
from planning.lodging import candidates, price_cap, search_area, shortlist, sieve
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
    assert price_cap({"budget_vnd": 3_000_000}, 3, CFG) == round(3_000_000 * CFG.lodging_share / 3)
    assert price_cap({"budget_vnd": None}, 3, CFG) is None
    assert price_cap({"budget_vnd": 1_000_000}, 0, CFG) is None


def cand(i, reviews=10, price=None, amenities=()):
    return {"id": f"h{i}", "name": f"Homestay {i}", "lat": CENTRE[0] + i * 0.001, "lng": CENTRE[1], "rating": 4.5,
           "reviews": reviews, "price_vnd": price, "amenities": list(amenities)}


def test_sieve_drops_too_few_reviews_but_keeps_what_it_cannot_verify():
    raw = [cand(0, reviews=1), cand(1, reviews=20), cand(2, reviews=20, amenities=["parking"])]
    hard = [{"feature": "parking", "op": "ne", "value": "present"}]
    out = sieve(raw, hard, CFG.min_reviews)
    assert {c["id"] for c in out} == {"h1"}  # h0: too few reviews; h2: hard filter evidence against it


def test_shortlist_keeps_the_k_candidates_closest_to_any_centre():
    raw = [cand(i) for i in range(10)]
    centres = [{"lat": CENTRE[0], "lng": CENTRE[1], "radius_km": 3.0}]
    assert [c["id"] for c in shortlist(raw, centres, 3)] == ["h0", "h1", "h2"]


def test_candidates_merges_two_centres_without_duplicates_and_passes_the_price_cap_through():
    places = by(rec("a", *CENTRE), rec("b", 11.60, 108.10))
    seen = []

    def fake(center, radius_km, check_in, check_out, price_max, live_cfg):
        seen.append(price_max)
        return [cand(0), cand(1)]  # same ids from both centres: a duplicate to drop

    out = candidates(places, decision(["a", "b"], budget=3_000_000, days=3), CFG, fake, None)
    assert len(seen) == 2 and all(p == round(3_000_000 * CFG.lodging_share / 2) for p in seen)
    assert sorted(c["id"] for c in out) == ["h0", "h1"]


def test_a_dead_lodging_source_at_one_centre_still_returns_what_the_other_found():
    places = by(rec("a", *CENTRE), rec("b", 11.60, 108.10))

    def flaky(center, *a):
        if round(center[0], 2) == round(CENTRE[0], 2):
            raise Unavailable("blocked")
        return [cand(0)]

    out = candidates(places, decision(["a", "b"]), CFG, flaky, None)
    assert [c["id"] for c in out] == ["h0"]


def test_no_places_means_no_candidates():
    assert candidates({}, decision([]), CFG, lambda *a: pytest.fail("no call"), None) == []
