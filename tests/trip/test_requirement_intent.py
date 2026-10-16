import json
from datetime import date

import pytest

from trip import Catalog, TripState, compile_search_input
from trip.agent import TurnTools, build_messages
from trip.domain.state import Evidence, Update, apply
from trip_fixtures import rec


def test_record_fact_preserves_intent_and_quote_across_compile():
    text = "Trong nhóm có một người ăn chay"
    t = TurnTools(TripState(), text, 1, Catalog(()), date(2026, 10, 10))
    result = t.run("record_fact", {"field": "hard", "op": "add", "value": "vegetarian_options=yes", "quote": text,
                                  "how": "said", "requirement": {"meaning": "vegetarian meal options", "scope": "eating",
                                                                  "subject": "member", "subject_count": 1}})
    assert result == {"ok": True}
    h = compile_search_input(t.state).hard_filters[0]
    assert (h.meaning, h.strength, h.scope, h.subject, h.subject_count) == (
        "vegetarian meal options", "mandatory", "eating", "member", 1)
    assert h.evidence[0].quote == text
    restored = type(h).model_validate_json(h.model_dump_json())
    assert restored == h


def test_intent_cannot_put_diet_on_sightseeing_or_hide_an_access_constraint():
    t = TurnTools(TripState(), "ăn chay, không leo dốc", 1, Catalog(()), date(2026, 10, 10))
    for value, quote, scope in [("vegetarian_options=yes", "ăn chay", "sightseeing"),
                                ("steep_or_stairs!=present", "không leo dốc", "eating")]:
        result = t.run("record_fact", {"field": "hard", "op": "add", "value": value, "quote": quote,
                                        "how": "said", "requirement": {"meaning": quote, "scope": scope,
                                                                        "subject": "traveler"}})
        assert result["ok"] is True and result["note"].startswith("warning:")
    assert [(h.feature, h.scope) for h in t.state.hard] == [("vegetarian_options", None), ("steep_or_stairs", None)]


def test_soft_intent_and_evidence_survive_compile():
    t = TurnTools(TripState(), "thích đồ chay", 1, Catalog(()), date(2026, 10, 10))
    assert t.run("record_fact", {"field": "soft", "op": "add", "value": "vegetarian_options=yes:love",
                                "quote": "thích đồ chay", "how": "said",
                                "requirement": {"meaning": "vegetarian food preference", "scope": "eating",
                                                "subject": "traveler"}}) == {"ok": True}
    w = compile_search_input(t.state).soft_weights[0]
    assert (w.scope, w.strength, w.evidence[0].quote) == ("eating", "preference", "thích đồ chay")
    assert not t.state.hard


def test_runtime_skill_is_loaded_in_real_agent_messages():
    messages = build_messages(TripState(), "ăn chay", [], None, date(2026, 10, 10), [])
    system = messages[0]["content"]
    assert "name: interpret-trip-requirements" in system
    assert "scope" in system and "vegan_options" in system and "activity!=alcohol_consumption" in system


def test_an_activity_requires_a_real_place_and_its_name_in_the_quote():
    r = rec(1, "Cafe Lunch", {})
    cat = Catalog.from_records([r], 1)
    t = TurnTools(TripState(), "ăn trưa ở Cafe Lunch", 1, cat, date(2026, 10, 10))
    args = {"field": "activity", "op": "add", "how": "said", "quote": t.text,
            "value": json.dumps({"place_id": r["place_fid"], "activity": "eating"})}
    assert t.run("record_fact", args) == {"ok": True}
    assert compile_search_input(t.state).activities == {r["place_fid"]: "eating"}
    assert "error" in t.run("record_fact", {**args, "quote": "ăn trưa"})
    assert "error" in t.run("record_fact", {**args, "value": json.dumps({"place_id": "invented", "activity": "eating"})})


def test_unresolved_ambiguity_cannot_be_recorded_as_a_mandatory_requirement():
    t = TurnTools(TripState(), "chay", 1, Catalog(()), date(2026, 10, 10))
    assert "error" in t.run("record_fact", {"field": "hard", "op": "add", "value": "vegetarian_options=yes",
                                           "quote": "chay", "how": "inferred",
                                           "requirement": {"meaning": "vegetarian meal options", "scope": "eating",
                                                           "subject": "unspecified", "ambiguity": "diet or preference"}})
    assert not t.state.hard


def test_time_preference_and_photo_purpose_survive_public_compile():
    text = "muốn chụp ảnh, ưu tiên đi dạo buổi chiều"
    t = TurnTools(TripState(), text, 1, Catalog(()), date(2026, 10, 10))
    assert t.run("record_fact", {"field": "purpose", "op": "set", "value": "photo", "quote": "muốn chụp ảnh",
                                "how": "said"}) == {"ok": True}
    args = {"field": "time_preference", "op": "add", "value": json.dumps({"activity": "walking", "period": "afternoon"}),
            "quote": "ưu tiên đi dạo buổi chiều", "how": "said"}
    assert t.run("record_fact", args) == {"ok": True}
    si = compile_search_input(t.state)
    assert si.context.purpose == "photo"
    pref = si.time_preferences[0]
    assert pref.activity == "walking" and pref.period == "afternoon"
    assert pref.evidence[0].quote == args["quote"]
    assert type(si).model_validate_json(si.model_dump_json()) == si
    assert "error" in t.run("record_fact", {**args, "value": '{"period":"imaginary"}'})
    assert "error" in t.run("record_fact", {**args, "value": '{"place_id":"invented","period":"morning"}'})


def test_clef_can_reject_an_unsupported_time_preference():
    class Judge:
        def unsupported(self, quote, claim):
            return True
    t = TurnTools(TripState(), "muốn chụp ảnh", 1, Catalog(()), date(2026, 10, 10), judge=Judge())
    assert "error" in t.run("record_fact", {"field": "time_preference", "op": "add", "value": '{"period":"evening"}',
                                           "quote": "muốn chụp ảnh", "how": "inferred"})
    assert not t.state.time_preferences


def test_global_venue_and_alcohol_prohibitions_cannot_be_narrowed_by_scope():
    from requirements import Requirement
    for feature, value in [("activity", "alcohol_consumption"), ("venue_category", "bar")]:
        with pytest.raises(ValueError):
            Requirement(feature=feature, value=value, op="ne", scope="eating")
