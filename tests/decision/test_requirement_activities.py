import pytest

from fixtures import feat, hard, love, si, srec

from decision import hard_check, run_pipeline
from decision.model import Cand
from decision.rank import preference_fit
from decision.screen import screen
from decision.settings import default
from decision.trip_days import trip_days
from requirements import Requirement, allowed


def test_cafe_and_market_use_the_selected_activity():
    veg = hard("vegetarian_options", "yes", "eq")
    cafe, market = srec("cafe"), srec("market", group="market")
    for rec in (cafe, market):
        assert hard_check(rec, veg, "eating") == "unknown"
        assert hard_check(rec, veg, "coffee") == "not_applicable"
        assert hard_check(rec, veg, "sightseeing") == "not_applicable"
    s = si(hard_filters=[veg], activities={"cafe": "eating"})
    c = Cand(cafe, "experience")
    screen(c, s, trip_days(s.context, default()), set())
    assert c.status == "unverified"


def test_vegan_needs_distinct_evidence_and_a_mixed_menu_can_be_vegetarian():
    mixed = srec("mixed", group="restaurant", usable=("meal",), features={"vegetarian_options": "yes"})
    assert hard_check(mixed, hard("vegetarian_options", "yes", "eq")) == "pass"
    assert hard_check(mixed, hard("vegan_options", "yes", "eq")) == "unknown"


def test_abstaining_from_alcohol_is_different_from_avoiding_bars():
    abstain = {"feature": "activity", "value": "alcohol_consumption", "op": "ne", "unknown_policy": "exclude"}
    bars = {"feature": "venue_category", "value": "bar", "op": "ne", "unknown_policy": "exclude"}
    bar = srec("bar", group="bar")
    restaurant = srec("meal", group="restaurant", usable=("meal",))
    assert hard_check(restaurant, abstain) == "pass"
    assert hard_check(bar, abstain) == "pass"
    assert hard_check(bar, bars) == "fail"
    assert hard_check(restaurant, bars) == "pass"
    assert hard_check(restaurant, abstain, "wine_tasting") == "fail"
    assert hard_check(bar, abstain, "tasting") == "unknown"


def test_generic_tasting_cannot_prove_wine_tasting():
    cafe = srec("tea", features={"tasting_available": "present"})
    req = hard("wine_tasting_available", "present", "eq")
    assert hard_check(cafe, req, "tasting") == "unknown"
    assert preference_fit(cafe, [love("wine_tasting_available")], "tasting")[0] == 0


def test_unknown_flag_is_preserved_but_explicit_failure_is_never_admitted():
    req = hard("vegetarian_options", "yes", "eq", "flag")
    assert allowed(srec("u", group="restaurant", usable=("meal",)), req)
    assert not allowed(srec("no", group="restaurant", usable=("meal",), features={"vegetarian_options": "no"}), req)


def test_explicit_scope_also_controls_ranking_denominator():
    museum = srec("museum", group="museum", features={"scenic_view": "present"})
    weights = [love("scenic_view"), {**love("noise", "quiet"), "scope": "accommodation"}]
    assert preference_fit(museum, weights)[0] == 1


def test_requirement_boundary_rejects_unknown_features_and_invalid_scope():
    with pytest.raises(ValueError):
        Requirement(feature="made_up", value="yes", op="eq")
    with pytest.raises(ValueError):
        Requirement(feature="vegan_options", value="yes", op="eq", scope="all")


def test_wine_preference_ranks_a_verified_offering_without_forcing_consumption():
    winery = srec("winery", group="tour", category="Winery", usable=("experience",),
                  features={"wine_tasting_available": "present"})
    assert preference_fit(winery, [love("wine_tasting_available")])[0] == 1
    abstain = {"feature": "activity", "value": "alcohol_consumption", "op": "ne", "unknown_policy": "exclude"}
    assert hard_check(winery, abstain) == "pass"
    assert preference_fit(winery, [love("wine_tasting_available")], "sightseeing")[0] == 0


def test_a_coffee_only_visit_is_not_checked_for_a_wine_activity():
    cafe = srec("coffee", features={"tasting_available": "present"})
    assert hard_check(cafe, hard("wine_tasting_available", "present", "eq"), "coffee") == "not_applicable"


def test_abstention_rejects_a_drinking_activity_that_explicitly_requires_alcohol():
    abstain = {"feature": "activity", "value": "alcohol_consumption", "op": "ne", "unknown_policy": "exclude"}
    required = srec("bar", group="bar", features={"alcohol_required": "yes"})
    assert hard_check(required, abstain, "drinking") == "fail"
