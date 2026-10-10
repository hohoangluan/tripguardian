from datetime import date

import pytest

from trip.agent import ToolExecutor


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


def tools(catalog, text="Mình đi 3 ngày với bố mẹ", state=None, may_ask=True):
    return TurnTools(state or TripState(), text, 1, catalog, date(2026, 10, 8), [], may_ask)


def test_record_fact_writes_through_the_guard_and_refuses_a_made_up_quote(catalog):
    t = tools(catalog)
    assert t.run("record_fact", {"field": "days", "op": "set", "value": "3", "quote": "3 ngày", "how": "said"}) == {"ok": True}
    assert t.state.days.value == 3
    out = t.run("record_fact", {"field": "days", "op": "set", "value": "9", "quote": "9 ngày", "how": "said"})
    assert "error" in out and t.state.days.value == 3


def test_ask_choice_makes_a_custom_card_and_stops_the_turn(catalog):
    t = tools(catalog)
    t.run("ask_choice", {"text": "Bạn đi bằng gì?", "options": ["Xe máy", "Ô tô"], "multi": False, "reason": "x"})
    assert t.stopped and t.card.custom and [c.label for c in t.card.chips] == ["Xe máy", "Ô tô"]


@pytest.mark.parametrize("options", [["Một"], ["a"] * 7, ["a", "b" * 41]])
def test_ask_choice_needs_two_to_six_short_options(catalog, options):
    t = tools(catalog)
    out = t.run("ask_choice", {"text": "?", "options": options, "multi": False, "reason": "x"})
    assert "error" in out and not t.stopped and t.card is None


def test_the_model_has_no_way_to_end_the_conversation(catalog):
    t = tools(catalog)
    assert "finish" not in [s["function"]["name"] for s in t.specs()]
    assert "error" in t.run("finish", {"outcome": "ready", "message": "Xong."}) and not t.stopped


def test_a_wish_typed_after_the_questions_cannot_ask(catalog):
    t = tools(catalog, may_ask=False)
    assert "ask_choice" not in [s["function"]["name"] for s in t.specs()]
    assert "error" in t.run("ask_text", {"text": "?"}) and not t.stopped


def test_an_unknown_tool_or_bad_arguments_come_back_as_errors(catalog):
    t = tools(catalog)
    assert "error" in t.run("rm_rf", {})
    assert "error" in t.run("record_fact", {"field": "days"})


def test_open_quiz_tool_starts_resumes_or_restarts(catalog):
    from trip.domain.state import with_meta

    t = tools(catalog, "mở phần câu hỏi")
    assert "open_quiz" in [s["function"]["name"] for s in t.specs()]
    assert t.run("open_quiz", {}) == {"ok": True} and t.opened and t.stopped
    t = tools(catalog, "làm lại trắc nghiệm", with_meta(TripState(), phase="review"))
    assert "open_quiz" in [s["function"]["name"] for s in t.specs()]
    assert t.run("open_quiz", {}) == {"ok": True} and t.opened and t.stopped
    t = tools(catalog, "hỏi tiếp đi", with_meta(TripState(), phase="paused"))  # quiz on hold: resume it
    assert t.run("open_quiz", {}) == {"ok": True} and t.opened and t.stopped
    t = tools(catalog, may_ask=False)  # a quiet turn cannot reopen either
    assert "open_quiz" not in [s["function"]["name"] for s in t.specs()]


def test_search_features_finds_a_feature_by_its_meaning_and_admits_when_none_fits(catalog):
    t = tools(catalog)
    ids = [f["id"] for f in t.run("search_features", {"query": "vật nuôi thú"})["features"]]
    assert "animals" in ids
    assert t.run("search_features", {"query": "zzzz qqqq"})["features"] == []
    assert "error" in t.run("search_features", {"query": "  "})


def test_a_wish_stored_as_unmapped_is_remembered_for_the_fixed_reply(catalog):
    t = tools(catalog, text="mình muốn có chó")
    t.run("record_fact", {"field": "unmapped", "op": "add", "value": "chó", "quote": "muốn có chó", "how": "said"})
    assert t.unmapped == ["muốn có chó"] and not t.stopped
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

    from trip.agent import system_prompt
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


def test_a_card_carries_the_agents_example_answer_for_its_text_box(catalog):
    t = tools(catalog)
    t.run("ask_text", {"text": "Hai bạn đi vào tháng mấy?", "placeholder": "cuối tháng 12, hoặc 20/12"})
    assert t.card.placeholder == "cuối tháng 12, hoặc 20/12" and t.card.text == "Hai bạn đi vào tháng mấy?"
    t = tools(catalog)
    t.run("ask_choice", {"text": "Đi bằng gì?", "options": ["Xe máy", "Ô tô"], "multi": False, "reason": "x", "placeholder": "xe đạp điện"})
    assert t.card.placeholder == "xe đạp điện"
    t = tools(catalog)
    t.run("ask_text", {"text": "Mấy ngày?"})  # optional: the screen falls back to its own example
    assert t.card.placeholder == ""


def test_every_clef_check_of_a_reply_is_sent_before_any_tool_runs_and_the_tools_reuse_them(catalog):
    from trip_fixtures import call
    asked = []

    class Judge:
        def unsupported(self, quote, claim):
            asked.append(("v", quote))
            return False

        def repeats(self, question, known):
            asked.append(("r", question))
            return False

        def bad_reply(self, say):
            asked.append(("s", say))
            return None

    t = TurnTools(TripState(), "thích yên tĩnh, đi với bạn", 1, catalog, date(2026, 10, 8), judge=Judge())
    calls = [call("record_fact", field="soft", op="add", value="noise=quiet:love", quote="yên tĩnh", how="inferred"),
             call("ask_text", text="Bạn đi mấy ngày?")]
    t.prefetch(calls, "Mình hiểu rồi.")
    for c in t.checks.values():
        c.result()
    assert sorted(a[0] for a in asked) == ["r", "s", "v"]
    t.run("record_fact", {"field": "soft", "op": "add", "value": "noise=quiet:love", "quote": "yên tĩnh", "how": "inferred"})
    t.run("ask_text", {"text": "Bạn đi mấy ngày?", "placeholder": ""})
    assert len(asked) == 3 and t.reply_problem() is None  # nothing was asked twice
    t.close()
