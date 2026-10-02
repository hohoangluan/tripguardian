import pytest

from corpus.ontology import load, parse


def test_shipped_ontology_loads():
    ont = load()
    assert ont.version == 7
    for fid in ("steep_or_stairs", "long_walk"):
        assert ont.features[fid].values == ("present", "absent") and ont.features[fid].span_check
    assert ont.valid("weather_exposed", "sheltered") and ont.features["weather_exposed"].span_check
    assert ont.features["booking_needed"].span_check
    assert ont.features["visit_duration"].group == "operation" and ont.valid("visit_duration", "half_day")
    assert ont.valid("outdoor_seating", "present") and ont.valid("laptop_friendly", "present")
    assert ont.valid("vegetarian_options", "no")
    assert ont.features["steep_or_stairs"].span_check and ont.features["kids"].span_check
    assert ont.features["tourist_trap"].span_check and not ont.features["food_quality"].span_check
    for fid in ("hands_on_workshop", "pick_your_own", "cultural_show", "camping", "spacious"):
        assert ont.features[fid].values == ("present",)
    for fid in ("tourist_trap", "rough_road_access", "cash_only"):  # v7: hard filters need a value that can pass
        assert ont.features[fid].values == ("present", "absent")
    assert ont.valid("entry_fee", "free") and ont.valid("portion_size", "generous")
    assert ont.features["service_quality"].values == ("good", "mixed", "poor")
    assert ont.valid("crowd", "high") and not ont.valid("crowd", "packed") and not ont.valid("wifi", "present")
    assert ont.features["kids"].verify == "always" and ont.features["kids"].caution_values == ("unsuitable",)
    assert ont.features["scenic_view"].group == "experience"
    assert ont.valid_context("day_type", "weekend") and ont.valid_context("weather", "unknown")
    assert not ont.valid_context("day_type", "monday")
    assert "- crowd = low | medium | high:" in ont.prompt_text()
    assert "context day_type = weekday | weekend | holiday | unknown" in ont.prompt_text()


BASE = {"version": 1, "groups": ["experience"], "contexts": {"day_type": ["weekday"]}}
A = {"id": "a", "group": "experience", "values": ["present"], "hint": "x"}


def test_duplicate_id_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        parse({**BASE, "features": [A, A]})


def test_empty_values_rejected():
    with pytest.raises(ValueError, match="no values"):
        parse({**BASE, "features": [{**A, "values": []}]})


def test_unknown_group_rejected():
    with pytest.raises(ValueError, match="group"):
        parse({**BASE, "features": [{**A, "group": "vibes"}]})


def test_caution_value_outside_values_rejected():
    with pytest.raises(ValueError, match="caution"):
        parse({**BASE, "features": [{**A, "caution_values": ["absent"]}]})


def test_bad_verify_rejected():
    with pytest.raises(ValueError, match="verify"):
        parse({**BASE, "features": [{**A, "verify": "never"}]})


def test_bad_check_rejected():
    with pytest.raises(ValueError, match="check"):
        parse({**BASE, "features": [{**A, "check": "maybe"}]})


def test_span_checked_features_state_one_claim_per_value():
    ont = load()
    for f in ont.features.values():
        if f.span_check:
            assert set(f.claims) == set(f.values), f.id
    assert ont.features["wheelchair"].claims["unsuitable"] != ont.features["wheelchair"].claims["suitable"]


def test_span_check_without_claims_rejected():
    with pytest.raises(ValueError, match="claims"):
        parse({**BASE, "features": [{**A, "check": "span"}]})
