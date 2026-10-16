"""Review round 3 of the Trip redesign: defects found by running the 76 personas after part 4 (logs/bench_trip/after_p4).

G15 "đi 2 ngày với mẹ": the guard refused companions=parents for the quote "mẹ" (only "bố mẹ", "với mẹ" were words of
    the group), so the user was asked again who comes. "2 mẹ con" stays ambiguous: the speaker may be the mother.
G16 "dị ứng đậu phộng": signal=peanut_allergy was refused as outside the enum and nothing kept the words; the refusals
    then hit tool_fail_cap and the rest of the message (đi một mình, đi bộ với taxi) was lost. A6: a value outside a
    closed list is kept as the user's words (unmapped) with a warning, and a warning is not a tool failure.
G17 budget_unlimited="yes" was refused (4 times in the bench).
G18 schema_refused lines carried only the exception type, so the bench could not tell why 15 turns hit the cap.
"""

import asyncio
import json
from datetime import date

import pytest
from trip_fixtures import ScriptedChat, call, fact, reply, say

from trip import TripState
from trip.agent.loop import run_loop
from trip.agent.tools import TurnTools

TODAY = date(2026, 10, 15)


def turn(catalog, text, field, value, quote, how="said"):
    t = TurnTools(TripState(), text, 1, catalog, TODAY)
    out = t.run("record_fact", {"field": field, "op": "set" if field != "companions" else "add", "value": value,
                                "quote": quote, "how": how})
    return t, out


# ---------- G15: a parent named by one word ----------

@pytest.mark.parametrize("text, quote", [
    ("à mình muốn đi đà lạt 2 ngày với mẹ", "mẹ"),
    ("mẹ mình ngồi xe lăn, cả nhà 4 người", "mẹ mình"),
    ("dẫn bố đi chơi 3 ngày", "bố"),
    ("đi cùng ba má", "ba má"),
])
def test_g15_one_word_for_a_parent_names_the_parents_group(catalog, text, quote):
    t, out = turn(catalog, text, "companions", "parents", quote)
    assert "error" not in out, out
    assert set(t.state.companions.value) == {"parents"} and t.state.companions.source == "user"


@pytest.mark.parametrize("text, quote", [
    ("2 ngày, 2 mẹ con, đi bộ", "2 mẹ con"),  # the speaker may be the mother: who is the child?
    ("nhóm ba người đi chơi", "ba người"),  # "ba" is three here
    ("di voi me 2 ngay", "me"),  # no diacritics: "me" is not "mẹ" for sure
])
def test_g15_words_that_do_not_surely_name_a_parent_are_kept_not_mapped(catalog, text, quote):
    t, out = turn(catalog, text, "companions", "parents", quote)
    assert "parents" not in set(t.state.companions.value or ())
    if "mẹ con" in quote:
        assert "mẹ con" in " ".join(t.state.companions_other)  # A6: the words stay for the tab to ask about


# ---------- G16: outside a closed list = the user's words, kept ----------

@pytest.mark.parametrize("field, value, quote", [
    ("signal", "peanut_allergy", "dị ứng đậu phộng"),
    ("purpose", "party", "quẩy tới bến"),
    ("mobility", "bicycle", "đạp xe"),
])
def test_g16_a_value_outside_the_list_is_kept_as_the_users_words(catalog, field, value, quote):
    text = f"mình {quote} nha, đi 3 ngày"
    t, out = turn(catalog, text, field, value, quote)
    assert "error" not in out and "warning" in json.dumps(out, ensure_ascii=False)
    assert quote in [u.phrase for u in t.state.unmapped]


@pytest.mark.parametrize("value", ["unknown", "none", "null", "", "n/a"])
def test_g16_a_placeholder_value_writes_nothing_and_is_not_a_failure(catalog, value):
    t, out = turn(catalog, "đi 3 ngày", "mobility", value, "3 ngày")
    assert "error" not in out
    assert not t.state.mobility.known and not t.state.unmapped


def test_g16_a_value_outside_the_list_whose_quote_is_not_in_the_message_is_still_refused(catalog):
    t, out = turn(catalog, "đi 3 ngày", "signal", "peanut_allergy", "dị ứng đậu phộng")
    assert "error" in out and not t.state.unmapped


def test_g16_kept_words_do_not_stop_the_turn_before_the_rest_is_recorded(catalog):
    text = "mình ăn thuần chay và dị ứng đậu phộng, đi một mình 3 ngày, đi bộ với taxi"
    calls = [fact("signal", "vegan", "thuần chay"), fact("signal", "peanut_allergy", "dị ứng đậu phộng"),
             fact("purpose", "allergy", "dị ứng đậu phộng"), fact("signal", "nut_free", "đậu phộng"),
             fact("companions", "solo", "một mình", op="add"), fact("days", "3", "3 ngày"),
             fact("mobility", "walk", "đi bộ")]
    chat = ScriptedChat(reply(*calls), say("Mình đã ghi lại."))
    tools = TurnTools(TripState(), text, 1, catalog, TODAY)
    asyncio.run(run_loop(chat, [{"role": "user", "content": text}], tools, lambda _: None, 6))
    st = tools.state
    assert not any("tool_fail_cap" in x for x in tools.log), tools.log
    assert set(st.companions.value) == {"solo"} and st.days.value == 3 and st.mobility.value == "walk"
    assert "dị ứng đậu phộng" in [u.phrase for u in st.unmapped]


# ---------- G17: yes / no for a flag ----------

@pytest.mark.parametrize("value, expected", [("yes", True), ("true", True), ("có", True), ("no", False),
                                              ("false", False), ("không", False)])
def test_g17_a_flag_reads_yes_and_no(catalog, value, expected):
    t, out = turn(catalog, "tiền không thành vấn đề", "budget_unlimited", value, "tiền không thành vấn đề")
    assert "error" not in out, out
    assert t.state.budget_unlimited.value is expected


# ---------- G18: why a call was refused ----------

def test_g18_a_schema_refusal_logs_its_reason(catalog):
    bad = call("record_fact", field="days", op="set", value="3", quote="3 ngày", how="said", colour="red")
    chat = ScriptedChat(reply(bad), say("Bạn đi mấy ngày?"))
    tools = TurnTools(TripState(), "đi 3 ngày", 1, catalog, TODAY)
    asyncio.run(run_loop(chat, [{"role": "user", "content": "x"}], tools, lambda _: None, 6))
    line = next(x for x in tools.log if x.startswith("schema_refused"))
    assert len(line) > len("schema_refused ToolInvocationError") and len(line) <= 200
    assert "colour" in line
