from datetime import date

import pytest

from trip.agent.tools import ToolExecutor


def test_relative_date_tool_resolves_a_weekday(catalog):
    tool = ToolExecutor(catalog, date(2026, 10, 8))
    assert tool.run("resolve_relative_date", {"expression": "thứ 4 tuần sau"},
                    "Thứ 4 tuần sau tôi sẽ đi") == {
                        "status": "ok", "start_date": "2026-10-14", "weekday": "thứ Tư"}


def test_relative_date_tool_rejects_a_made_up_argument(catalog):
    tool = ToolExecutor(catalog, date(2026, 10, 8))
    with pytest.raises(ValueError, match="user message"):
        tool.run("resolve_relative_date", {"expression": "ngày mai"}, "thứ 4 tuần sau tôi đi")


def test_place_lookup_tool_uses_the_catalog_only(catalog):
    tool = ToolExecutor(catalog, date(2026, 10, 8))
    result = tool.run("search_places", {"query": "Vườn"}, "Tôi muốn ghé Vườn")
    assert result["places"] == [{"id": "0x11:0x1", "name": "Vườn Phẳng Lặng Xanh", "category": "Quán cà phê"}]


from trip.agent import TurnTools
from trip.domain.state import TripState  # noqa: E402


def tools(catalog, text="Mình đi 3 ngày với bố mẹ", state=None):
    return TurnTools(state or TripState(), text, 1, catalog, date(2026, 10, 8), [])


def test_record_fact_writes_through_the_guard_and_refuses_a_made_up_quote(catalog):
    t = tools(catalog)
    assert t.run("record_fact", {"field": "days", "op": "set", "value": "3", "quote": "3 ngày", "how": "said"}) == {"ok": True}
    assert t.state.days.value == 3
    out = t.run("record_fact", {"field": "days", "op": "set", "value": "9", "quote": "9 ngày", "how": "said"})
    assert "error" in out and t.state.days.value == 3


def test_the_model_has_no_way_to_end_the_conversation(catalog):
    t = tools(catalog)
    assert "finish" not in [s["function"]["name"] for s in t.specs()]
    assert "error" in t.run("finish", {"outcome": "ready", "message": "Xong."})


def test_an_unknown_tool_or_bad_arguments_come_back_as_errors(catalog):
    t = tools(catalog)
    assert "error" in t.run("rm_rf", {})
    assert "error" in t.run("record_fact", {"field": "days"})


def test_search_features_finds_a_feature_by_its_meaning_and_admits_when_none_fits(catalog):
    t = tools(catalog)
    ids = [f["id"] for f in t.run("search_features", {"query": "vật nuôi thú"})["features"]]
    assert "animals" in ids
    assert t.run("search_features", {"query": "zzzz qqqq"})["features"] == []
    assert "error" in t.run("search_features", {"query": "  "})


def test_a_wish_stored_as_unmapped_is_remembered_for_the_fixed_reply(catalog):
    t = tools(catalog, text="mình muốn có chó")
    t.run("record_fact", {"field": "unmapped", "op": "add", "value": "chó", "quote": "muốn có chó", "how": "said"})
    assert t.unmapped == ["muốn có chó"]
    bad = t.run("record_fact", {"field": "soft", "op": "add", "value": "khong_co=present", "quote": "muốn có chó", "how": "said"})
    assert "error" in bad and t.unmapped == ["muốn có chó"]  # a malformed feature is the agent's to fix, not unmapped


def test_search_features_ignores_words_that_match_every_hint(catalog):
    t = tools(catalog)
    assert t.run("search_features", {"query": "chó"})["features"] == []  # "cho" is the word for "for"


def test_writing_the_unmapped_field_directly_also_ends_the_turn_with_the_fixed_reply(catalog):
    t = tools(catalog, text="thích chỗ có cá heo bay")
    t.run("record_fact", {"field": "unmapped", "op": "add", "value": "cá heo bay", "quote": "cá heo bay", "how": "said"})
    assert t.unmapped == ["cá heo bay"]


def test_search_features_returns_a_value_the_agent_can_copy(catalog):
    from trip.domain.guard import record_fact
    hit = next(f for f in tools(catalog).run("search_features", {"query": "vật nuôi thú"})["features"] if f["id"] == "animals")
    value = hit["use"].split()[0]  # "animals=present:love"
    st, note = record_fact(TripState(), "soft", "add", value, "thú", "said", "thích thú", 1, catalog)
    assert note == "" and "animals=present" in st.soft


def test_every_soft_and_hard_example_in_the_system_prompt_is_valid():
    import re

    from trip.agent.prompt import system_prompt
    from trip.domain.state import ontology
    from trip.domain.values import split_weight
    text = system_prompt()
    soft = re.findall(r"field soft, op add, value ([a-z_]+=[a-z_]+:(?:love|avoid))", text)
    hard = re.findall(r"field hard, op add, value ([a-z_]+)(?:!=|=)([a-z_]+)", text)
    assert soft and hard
    for raw in soft:
        feature, value = split_weight(raw)[0].split("=")
        assert ontology().valid(feature, value), raw
    for feature, value in hard:
        assert ontology().valid(feature, value), (feature, value)


def test_every_clef_check_of_a_reply_is_sent_before_any_tool_runs_and_the_tools_reuse_them(catalog):
    from trip_fixtures import call
    asked = []

    class Judge:
        def unsupported(self, quote, claim):
            asked.append(("v", quote))
            return False

        def bad_reply(self, say):
            asked.append(("s", say))
            return None

    t = TurnTools(TripState(), "thích yên tĩnh, đi với bạn", 1, catalog, date(2026, 10, 8), judge=Judge())
    calls = [call("record_fact", field="soft", op="add", value="noise=quiet:love", quote="yên tĩnh", how="inferred")]
    t.prefetch(calls, "Mình hiểu rồi.")
    for c in [*t.checks.values(), *t.replies]:
        c.result()
    assert sorted(a[0] for a in asked) == ["s", "v"]
    t.run("record_fact", {"field": "soft", "op": "add", "value": "noise=quiet:love", "quote": "yên tĩnh", "how": "inferred"})
    assert len(asked) == 2 and t.reply_problem() is None  # nothing was asked twice
    t.close()


def test_prompt_walk_example_uses_the_same_polarity_as_the_prepass():
    from trip.agent.prompt import SYSTEM
    from trip.domain.prepass import prepass
    assert "long_walk!=present" in SYSTEM and "long_walk=present" not in SYSTEM
    hard = [p.value for p in prepass("mẹ không đi bộ xa được", date(2026, 10, 8)).proposals if p.field == "hard"]
    assert hard == [{"feature": "long_walk", "op": "ne", "value": "present"}]


def test_questions_are_never_offered_as_tools(catalog):
    tools = TurnTools(TripState(), "x", 1, catalog, date(2026, 10, 8))
    assert not {"ask_choice", "ask_text"} & {s["function"]["name"] for s in tools.specs()}


def test_every_field_has_a_way_to_say_other():
    from typing import get_args

    from trip.agent.prompt import SYSTEM
    from trip.domain.guard import FieldName
    block = SYSTEM[SYSTEM.index("OTHER (the wish fits no value"):SYSTEM.index("Literal field values")]
    missing = [f for f in get_args(FieldName) if f not in block]
    assert missing == [], missing
    assert "companions, mobility" in block and "unmapped" in block
