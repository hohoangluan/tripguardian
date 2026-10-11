from datetime import date

from trip import Catalog, TripState, compile_search_input, prepass
from trip.domain.coverage import admissible, coverage, verdict
from trip.domain.state import Evidence, Hard, Update, apply
from trip.domain.understanding import matching
from trip_fixtures import rec


def places():
    records = [rec(1, "Park", {}), rec(2, "Restaurant", {}),
               rec(3, "Mixed menu", {"vegetarian_options": ("yes", 3)}),
               rec(4, "Meat only", {"vegetarian_options": ("no", 3)})]
    for r, category in zip(records, ["Công viên", "Nhà hàng", "Nhà hàng", "Nhà hàng"]):
        r["identity"]["category"] = category
    return Catalog.from_records(records, n_min=1)


def diet():
    return Hard(feature="vegetarian_options", op="eq", value="yes", evidence=(Evidence(turn=1, quote="ăn chay"),))


def test_sightseeing_is_not_applicable_and_does_not_inflate_dining_coverage():
    cat, h = places(), diet()
    assert verdict(cat.places[0], h) == "not_applicable"
    assert admissible(cat.places[0], [h])
    cov = coverage(h, cat.places, 2)
    assert (cov.passed, cov.failed, cov.unknown, cov.level) == (1, 1, 1, "thin")
    assert matching(TripState(hard=(h,)), cat) == 2


def test_missing_restaurant_diet_evidence_remains_unknown():
    cat = places()
    assert verdict(cat.places[1], diet()) == "unknown"
    assert not admissible(cat.places[1], [diet()])


def test_vegan_prepass_does_not_become_vegetarian():
    proposals = prepass("Trong nhóm có một người ăn thuần chay", date(2026, 10, 10)).proposals
    assert any(p.field == "signal" and p.value == "vegan" for p in proposals)
    assert not any(p.field == "signal" and p.value == "vegetarian" for p in proposals)


def test_food_preference_does_not_create_a_mandatory_diet_signal():
    proposals = prepass("Mình thích đồ chay, bạn mình thích ăn chay", date(2026, 10, 10)).proposals
    assert not any(p.field == "signal" and p.value in ("vegetarian", "vegan") for p in proposals)
