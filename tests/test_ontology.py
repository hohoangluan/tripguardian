import pytest

from corpus.ontology import load, parse


def test_shipped_ontology_loads():
    ont = load()
    assert ont.version == 2
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
