"""Review round 4 of the Trip redesign: the tool input schemas refused calls whose meaning was right.

Bench after part 5 (logs/bench_trip/after_p5, Gemma LAN): 78 schema refusals in 102 turns, 10/76 sessions at
tool_fail_cap. With the reason now logged (G18), most were our schema, not the model:
S1 record_fact without `how` (14): {"field": "people", "value": "2", "quote": "2 người"} was refused. The guard checks
   the quote anyway; a missing `how` means the user said it.
S2 ask_user (≈50): one question sent at the top level instead of inside `questions`, a header longer than 12 characters
   ("Nhịp độ chuyến đi"), no `why`. ask.check re-checks every question after the schema, so the schema only needs the
   shape; it trims what is too long instead of refusing.
S3 the schema_refused log line stopped right before the reason ("… with error:"); it must carry the validation detail.
Model mistakes stay refused: a field name that does not exist ("서_date"), an op outside the list.
"""

import asyncio
import json
from datetime import date

import pytest
from pydantic import ValidationError
from trip_fixtures import ScriptedChat, call, reply, say

from trip import TripState
from trip.agent.loop import run_loop
from trip.agent.tool_schemas import AskUser, RecordFact
from trip.agent.tools import TurnTools

TODAY = date(2026, 10, 15)


def test_s1_record_fact_without_how_is_said():
    args = RecordFact.model_validate({"field": "people", "op": "set", "quote": "2 người", "value": "2"})
    assert args.facts[0].how == "said"  # a single fact is a list of one (record_fact takes every fact in one call)


def test_s1_the_guard_still_checks_the_quote_of_a_call_without_how(catalog):
    t = TurnTools(TripState(), "đi 2 người", 1, catalog, TODAY)
    ok = t.run("record_fact", RecordFact.model_validate(
        {"field": "people", "op": "set", "quote": "2 người", "value": "2"}).model_dump(exclude_none=True))
    assert "error" not in ok and t.state.people.value == 2
    bad = t.run("record_fact", RecordFact.model_validate(
        {"field": "days", "op": "set", "quote": "5 ngày", "value": "5"}).model_dump(exclude_none=True))
    assert "error" in bad and not t.state.days.known


@pytest.mark.parametrize("args", [
    {"field": "서_date", "op": "set", "quote": "30/4", "value": "2027-04-30", "how": "said"},
    {"field": "days", "op": "replace", "quote": "3 ngày", "value": "3", "how": "said"},
])
def test_s1_model_mistakes_are_still_refused(args):
    with pytest.raises(ValidationError):
        RecordFact.model_validate(args)


OPTION = {"label": "Thong thả", "description": "Đi ít nơi", "writes": [{"field": "pace", "op": "set", "value": "slow"}]}
OPTION2 = {"label": "Đi nhiều", "description": "Ghé nhiều nơi", "writes": [{"field": "pace", "op": "set", "value": "packed"}]}


def test_s2_one_question_at_the_top_level_is_one_question():
    a = AskUser.model_validate({"question": "Bạn muốn đi nhịp nào?", "header": "Nhịp độ", "why": "Để chia lịch.",
                                "options": [OPTION, OPTION2]})
    assert len(a.questions) == 1 and a.questions[0].header == "Nhịp độ" and len(a.questions[0].options) == 2


def test_s2_options_alone_borrow_the_question_from_nothing_and_are_refused():
    with pytest.raises(ValidationError):  # no question text at all: nothing to ask
        AskUser.model_validate({"options": [OPTION, OPTION2]})


def test_s2_too_long_text_is_trimmed_not_refused_and_why_may_be_missing():
    q = {"question": "Bạn muốn đi thong thả hay ghé nhiều nơi trong mỗi ngày của chuyến đi Đà Lạt sắp tới cùng cả nhà mình?",
         "header": "Nhịp độ chuyến đi", "multi": False,
         "options": [dict(OPTION, label="Thong thả, nghỉ ngơi nhiều để mẹ không mệt và có thời gian chụp ảnh thật đẹp"),
                     dict(OPTION2, description="Ghé thật nhiều nơi nổi tiếng, xuất phát sớm và về khuya, phù hợp người khỏe")]}
    a = AskUser.model_validate({"questions": [q]})
    got = a.questions[0]
    assert got.why == "" and len(got.header) <= 24 and got.header.startswith("Nhịp độ")
    assert len(got.question) <= 140 and len(got.options[0].label) <= 60 and len(got.options[1].description) <= 140
    assert not got.header.endswith(" ") and not got.options[0].label.endswith(" ")


def test_s2_unknown_keys_inside_an_option_are_ignored():
    a = AskUser.model_validate({"questions": [{"question": "Nhịp nào?", "header": "Nhịp độ", "why": "x",
                                               "options": [dict(OPTION, id="a", icon="leaf"), OPTION2]}]})
    assert [o.label for o in a.questions[0].options] == ["Thong thả", "Đi nhiều"]


def test_s3_the_schema_refusal_log_carries_the_validation_detail(catalog):
    bad = call("record_fact", field="서_date", op="set", value="2027-04-30", quote="30/4", how="said")
    chat = ScriptedChat(reply(bad), say("Bạn đi ngày nào?"))
    tools = TurnTools(TripState(), "đi 30/4", 1, catalog, TODAY)
    asyncio.run(run_loop(chat, [{"role": "user", "content": "x"}], tools, lambda _: None, 6))
    line = next(x for x in tools.log if x.startswith("schema_refused"))
    assert "record_fact" in line and "field" in line and "with error:" not in line.rstrip()[-12:]
    assert len(line) <= 300


# ---------- S4: the next three causes in the bench after the S1-S3 fix (after_p5b) ----------

def test_s4_a_topic_beside_the_questions_is_ignored():
    a = AskUser.model_validate({"topic": "nhịp độ", "questions": [{"question": "Nhịp nào?", "header": "Nhịp độ",
                                                                  "options": [OPTION, OPTION2]}]})
    assert len(a.questions) == 1


def test_s4_an_unknown_axis_is_a_place_axis():
    a = AskUser.model_validate({"question": "Nhịp nào?", "header": "Nhịp độ",
                                "options": [dict(OPTION, axis="pace"), dict(OPTION2, axis="vibe")]})
    assert [o.axis for o in a.questions[0].options] == ["place", "place"]


def test_s4_a_visual_question_with_too_few_photos_becomes_a_plain_question():
    a = AskUser.model_validate({"question": "Kiểu nào?", "header": "Gu", "visual": True, "options": [OPTION, OPTION2]})
    assert a.questions[0].visual is False and len(a.questions[0].options) == 2
