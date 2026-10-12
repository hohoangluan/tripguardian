import asyncio
from datetime import date

import pytest
from trip_fixtures import ScriptedChat, call, fact, reply, say

from trip.agent import AgentError, TurnTools, run_loop
from trip.domain.state import TripState


def run(chat, catalog, text="đi 3 ngày với bạn bè", max_steps=6):
    tools = TurnTools(TripState(), text, 1, catalog, date(2026, 10, 8))
    messages = [{"role": "user", "content": text}]
    said = []
    asyncio.run(run_loop(chat, messages, tools, said.append, max_steps))
    return tools, messages, said


def test_tool_results_go_back_to_the_model_and_the_loop_goes_on(catalog):
    chat = ScriptedChat(reply(fact("days", "9", "9 ngày")), reply(fact("days", "3", "3 ngày")),
                        say("Bạn đi bằng gì?"))
    tools, messages, said = run(chat, catalog)
    assert chat.calls == 3 and tools.state.days.value == 3
    assert messages[2]["role"] == "tool" and "error" in messages[2]["content"]
    assert messages[1]["tool_calls"][0]["id"] == messages[2]["tool_call_id"]
    assert said == ["Bạn đi bằng gì?"]


def test_a_refusal_can_be_explicitly_dropped(catalog):
    chat = ScriptedChat(reply(fact("companions", "family", "gia đình", op="add")),
                        reply(call("drop_refusal", field="companions")), reply(text="Nhóm đi thì mình chưa rõ."))
    tools, _, _ = run(chat, catalog, text="đi với gia đình")
    assert chat.calls == 3 and not tools.refused and "drop_refusal companions" in tools.log


def test_a_plain_text_reply_ends_the_loop(catalog):
    tools, _, said = run(ScriptedChat(reply(text="Tháng 12 khá lạnh.")), catalog)
    assert said == ["Tháng 12 khá lạnh."] and tools.log == []


def test_the_loop_is_bounded(catalog):
    chat = ScriptedChat(*[reply(fact("days", "3", "3 ngày")) for _ in range(10)])
    tools, _, _ = run(chat, catalog, max_steps=3)
    assert chat.calls == 3 and "step_cap" in tools.log


def test_malformed_arguments_are_an_error_result_not_a_crash(catalog):
    from trip.agent import Assistant, Call
    bad = Assistant(calls=[Call("c1", "record_fact", "{not json")])
    _, messages, _ = run(ScriptedChat(bad, say("Đi mấy ngày?")), catalog)
    assert "error" in messages[2]["content"]


def test_a_model_failure_propagates_after_the_facts_already_written(catalog):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày")))
    tools = TurnTools(TripState(), "đi 3 ngày", 1, catalog, date(2026, 10, 8))
    with pytest.raises(AgentError):
        asyncio.run(run_loop(chat, [{"role": "user", "content": "x"}], tools, lambda _: None, 6))
    assert tools.state.days.value == 3


def test_an_unmapped_wish_ends_the_loop_without_another_model_call(catalog):
    chat = ScriptedChat(reply(fact("unmapped", "chó", "chó", op="add")), say("Bạn kể thêm nhé?"))
    tools, _, _ = run(chat, catalog, text="muốn có chó")
    assert chat.calls == 1 and tools.unmapped == ["chó"]


def test_a_reasoning_block_in_front_of_the_reply_is_never_shown():
    from trip.agent.loop import Visible
    v = Visible()
    shown = "".join(v.feed(d) for d in ["<|chan", "nel>thought\n", "kế hoạch<chan", "nel|>Mình ", "hiểu rồi."]) + v.end()
    assert shown == "Mình hiểu rồi."
    v = Visible()
    assert "".join(v.feed(d) for d in ["<", "b>Chào"]) + v.end() == "<b>Chào"  # text that only starts like the marker
    v = Visible()
    assert v.feed("<|channel>thought only") + v.end() == ""
    v = Visible()  # Gemma also writes an empty block after its text
    assert "".join(v.feed(d) for d in ["Bạn đi mấy ngày?\n\n<|cha", "nnel>thought\n<channel|>"]) + v.end() == "Bạn đi mấy ngày?\n\n"


def test_a_reply_that_claims_a_write_with_no_record_gets_one_retry_and_the_claim_is_dropped(catalog):
    chat = ScriptedChat(reply(text="Mình đã ghi nhận bạn đi cùng anh họ."),
                        reply(fact("companions", "friends", "bạn bè", op="add")), say("Bạn đi mấy ngày?"))
    tools = TurnTools(TripState(), "đi với anh họ, kiểu bạn bè", 1, catalog, date(2026, 10, 8))
    retries, said = [], []
    asyncio.run(run_loop(chat, [{"role": "user", "content": "x"}], tools, said.append, 6, lambda: retries.append(1)))
    assert chat.calls == 3 and retries == [1] and "claim_without_record" in tools.log
    assert tools.state.companions.known and said[-1] == "Bạn đi mấy ngày?"


def test_a_second_claim_without_a_record_is_not_retried_again(catalog):
    chat = ScriptedChat(reply(text="Mình đã ghi nhận rồi."), reply(text="Mình đã ghi lại."))
    tools = TurnTools(TripState(), "đi với anh họ", 1, catalog, date(2026, 10, 8))
    retries = []
    asyncio.run(run_loop(chat, [{"role": "user", "content": "x"}], tools, lambda _: None, 6, lambda: retries.append(1)))
    assert chat.calls == 2 and retries == [1]


def test_a_plain_reply_without_a_claim_is_not_retried(catalog):
    chat = ScriptedChat(reply(text="Bạn đi mấy ngày?"))
    tools = TurnTools(TripState(), "x", 1, catalog, date(2026, 10, 8))
    retries = []
    asyncio.run(run_loop(chat, [{"role": "user", "content": "x"}], tools, lambda _: None, 6, lambda: retries.append(1)))
    assert chat.calls == 1 and retries == []


def test_a_reply_that_says_it_understood_a_group_with_no_record_is_retried(catalog):
    chat = ScriptedChat(reply(text="Mình hiểu là bạn muốn đi giống bạn bè."),
                        reply(fact("companions", "friends", "bạn bè", op="add")), say("Bạn đi tháng mấy?"))
    tools = TurnTools(TripState(), "đi giống bạn bè", 1, catalog, date(2026, 10, 8))
    retries = []
    asyncio.run(run_loop(chat, [{"role": "user", "content": "x"}], tools, lambda _: None, 6, lambda: retries.append(1)))
    assert chat.calls == 3 and retries == [1] and tools.state.companions.known


def test_a_reply_clef_sends_back_is_written_again_with_the_reason(catalog):
    class Judge:
        def __init__(self):
            self.calls = 0

        def unsupported(self, quote, claim):
            return False

        def bad_reply(self, say):
            self.calls += 1
            return "promises results" if "gợi ý" in say and self.calls == 1 else None

        def repeats(self, question, known):
            return False

    chat = ScriptedChat(reply(text="Mình sẽ gợi ý ngay."), say("Bạn đi mấy ngày?"))
    tools = TurnTools(TripState(), "đi 3 ngày", 1, catalog, date(2026, 10, 8), judge=Judge())
    retries, messages = [], [{"role": "user", "content": "x"}]
    asyncio.run(run_loop(chat, messages, tools, lambda _: None, 6, lambda: retries.append(1)))
    tools.close()
    assert chat.calls == 2 and retries == [1] and "clef_retry promises results" in tools.log
    assert "chặn vì: promises results" in messages[-1]["content"] and tools.reply_problem() is None


def test_a_repeated_record_is_answered_not_written_again_and_the_loop_ends_in_text(catalog):
    chat = ScriptedChat(reply(fact("companions", "friends", "bạn bè", op="add")),
                        reply(fact("companions", "friends", "bạn bè", op="add")),
                        say("Mình hiểu là bạn đi với bạn bè."))
    tools = TurnTools(TripState(), "đi với bạn bè", 1, catalog, date(2026, 10, 8))
    said = []
    asyncio.run(run_loop(chat, [{"role": "user", "content": "x"}], tools, said.append, 6))
    assert chat.calls == 3 and tools.state.companions.known
    assert tools.log.count("record_fact companions=friends") == 2
    assert said == ["Mình hiểu là bạn đi với bạn bè."]
