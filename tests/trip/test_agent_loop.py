import asyncio
from datetime import date

import pytest
from trip_fixtures import ScriptedChat, call, fact, reply, say

from trip.agent import AgentError, TurnTools, run_loop
from trip.infrastructure.settings import Settings
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


def test_a_refusal_that_stays_unresolved_for_three_turns_lands_in_unmapped(catalog):
    from trip.domain.state import TripState
    from trip.agent import TurnTools
    text = "đi với cả đoàn 12 người"
    counts: dict = {}
    state = TripState()
    for _ in range(3):
        t = TurnTools(state, text, 1, catalog, date(2026, 10, 8), [])
        t.refused.add("companions")  # the field was refused this turn and nothing fixed it
        counts = t.settle_refusals(counts)
        state = t.state
    assert counts == {} and t.unmapped == [text] and "auto_unmapped companions" in t.log
    assert any(u.phrase == text for u in state.unmapped)


def test_a_refusal_resolved_in_time_keeps_no_count(catalog):
    from trip.domain.state import TripState
    from trip.agent import TurnTools
    t = TurnTools(TripState(), "đi với gia đình", 1, catalog, date(2026, 10, 8), [])
    t.refused.add("companions")
    assert t.settle_refusals({}) == {"companions": 1}
    t2 = TurnTools(TripState(), "đi với gia đình", 2, catalog, date(2026, 10, 8), [])  # fixed next turn: not refused
    assert t2.settle_refusals({"companions": 1}) == {}


def test_a_plain_text_reply_ends_the_loop(catalog):
    tools, _, said = run(ScriptedChat(reply(text="Tháng 12 khá lạnh.")), catalog)
    assert said == ["Tháng 12 khá lạnh."] and tools.log == []


def test_the_loop_is_bounded(catalog):
    chat = ScriptedChat(*[reply(fact("days", "3", "3 ngày")) for _ in range(10)])
    tools, _, _ = run(chat, catalog, max_steps=3)
    assert chat.calls == 3 and "step_cap" in tools.log


def test_malformed_arguments_are_an_error_result_not_a_crash(catalog):
    from langchain_core.messages import AIMessageChunk
    bad = AIMessageChunk(content="", tool_call_chunks=[{"id": "c1", "name": "record_fact", "args": "{not json", "index": 0}])
    _, messages, _ = run(ScriptedChat(bad, say("Đi mấy ngày?")), catalog)
    assert "error" in messages[2]["content"]


def test_a_model_failure_propagates_after_the_facts_already_written(catalog):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày")))
    tools = TurnTools(TripState(), "đi 3 ngày", 1, catalog, date(2026, 10, 8))
    with pytest.raises(AgentError):
        asyncio.run(run_loop(chat, [{"role": "user", "content": "x"}], tools, lambda _: None, 6))
    assert tools.state.days.value == 3


def test_a_silent_unmapped_gets_one_nudge_for_text_then_ends(catalog):
    chat = ScriptedChat(reply(fact("unmapped", "chó", "chó", op="add")), say("Bạn kể thêm nhé?"))
    tools, _, said = run(chat, catalog, text="muốn có chó")
    assert chat.calls == 2 and tools.unmapped == ["chó"] and "unmapped_without_text" in tools.log
    assert said == ["Bạn kể thêm nhé?"]


def test_an_unmapped_with_text_ends_the_loop_without_another_model_call(catalog):
    chat = ScriptedChat(reply(fact("unmapped", "chó", "chó", op="add"), text="Muốn có chó đi cùng hả?"))
    tools, _, said = run(chat, catalog, text="muốn có chó")
    assert chat.calls == 1 and tools.unmapped == ["chó"] and said == ["Muốn có chó đi cùng hả?"]


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


def test_the_written_reply_is_not_sent_to_clef_so_no_wait_after_the_call(catalog):
    class Judge:
        def __init__(self):
            self.calls = 0

        def unsupported(self, quote, claim):
            return False

        def bad_reply(self, say, user=""):
            self.calls += 1
            return "promises results"

    judge = Judge()
    chat = ScriptedChat(reply(text="Bạn đi mấy ngày?"))
    tools = TurnTools(TripState(), "đi đà lạt", 1, catalog, date(2026, 10, 8), judge=judge)
    asyncio.run(run_loop(chat, [{"role": "user", "content": "x"}], tools, lambda _: None, 6, lambda: None))
    tools.close()
    assert chat.calls == 1 and judge.calls == 0 and tools.reply_problem() is None


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


def test_one_nudge_per_turn_a_claim_then_a_clef_back_ends(catalog):
    class Judge:
        def unsupported(self, quote, claim):
            return False

        def bad_reply(self, say, user=""):
            return "promises results" if "gợi ý" in say else None

    chat = ScriptedChat(reply(text="Mình đã ghi nhận bạn đi cùng bạn bè."),
                        reply(text="Mình sẽ gợi ý ngay."))
    tools = TurnTools(TripState(), "đi với bạn bè", 1, catalog, date(2026, 10, 8), judge=Judge())
    retries = []
    asyncio.run(run_loop(chat, [{"role": "user", "content": "x"}], tools, lambda _: None, 6,
                         lambda: retries.append(1)))
    tools.close()
    assert chat.calls == 2 and retries == [1]
    assert "claim_without_record" in tools.log and "clef_retry" not in tools.log


def test_a_tool_that_crashes_is_an_error_result_and_the_turn_goes_on(catalog, monkeypatch):
    tools = TurnTools(TripState(), "đi 3 ngày", 1, catalog, date(2026, 10, 8))

    def boom(name, args):
        raise RuntimeError("db gone")
    monkeypatch.setattr(tools, "run", boom)
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày")), say("Bạn đi mấy ngày?"))
    messages, said = [{"role": "user", "content": "x"}], []
    asyncio.run(run_loop(chat, messages, tools, said.append, 6))
    assert chat.calls == 2 and "tool_crash record_fact RuntimeError" in tools.log
    assert '"error"' in messages[2]["content"] and said == ["Bạn đi mấy ngày?"]


def test_repeated_tool_failures_stop_the_turn_with_the_fallback(catalog):
    chat = ScriptedChat(*[reply(fact("days", "9", "9 ngày")) for _ in range(10)])
    tools = TurnTools(TripState(), "đi 3 ngày", 1, catalog, date(2026, 10, 8))
    said = []
    asyncio.run(run_loop(chat, [{"role": "user", "content": "x"}], tools, said.append, 10))
    assert chat.calls == 4 and any("tool_fail_cap" in x for x in tools.log) and said == []  # the engine says the fallback


def test_hitting_the_step_cap_ends_silently_for_the_engine_to_fall_back(catalog):
    chat = ScriptedChat(*[reply(fact("days", "3", "3 ngày")) for _ in range(10)])
    tools = TurnTools(TripState(), "x", 1, catalog, date(2026, 10, 8))
    said = []
    asyncio.run(run_loop(chat, [{"role": "user", "content": "x"}], tools, said.append, 3))
    assert said == [] and "step_cap" in tools.log


def test_the_persisted_history_drops_a_sent_back_reply_and_its_note(catalog):
    chat = ScriptedChat(reply(text="Mình đã ghi nhận bạn đi cùng bạn bè."),
                        reply(fact("companions", "friends", "bạn bè", op="add")), say("Bạn đi mấy ngày?"))
    tools = TurnTools(TripState(), "đi với bạn bè", 1, catalog, date(2026, 10, 8))
    messages = [{"role": "system", "content": "prompt"}, {"role": "user", "content": "đi với bạn bè"}]
    asyncio.run(run_loop(chat, messages, tools, lambda _: None, 6, lambda: None))
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "tool"]  # the final text is said, not stored
    assert all("Mình đã ghi nhận" not in (m.get("content") or "") for m in messages)


def test_langchain_chat_returns_the_merged_message_with_raw_arguments(monkeypatch):
    from langchain_core.messages import AIMessageChunk
    from trip.agent import loop as loop_mod

    pieces = [AIMessageChunk(content="Đi mấy ", tool_call_chunks=[]),
              AIMessageChunk(content="ngày?", tool_call_chunks=[{"name": "record_fact", "args": '{"field": "da', "id": "c1", "index": 0}]),
              AIMessageChunk(content="", tool_call_chunks=[{"name": None, "args": 'ys"}', "id": None, "index": 0}]),
              AIMessageChunk(content="", tool_call_chunks=[{"name": "record_fact", "args": "{not json", "id": "c2", "index": 1}])]

    class FakeLLM:
        def bind_tools(self, tools, **kw):
            return self

        async def astream(self, msgs):
            for p in pieces:
                yield p

    class FakeClient:
        base_url, api_key = "http://x", "k"

        async def close(self):
            pass

    monkeypatch.setattr(loop_mod, "ChatOpenAI", lambda **kw: FakeLLM())
    monkeypatch.setattr(loop_mod, "AGENT", type("Role", (), {"client": staticmethod(lambda: (FakeClient(), "m")),
                                                             "reasoning": staticmethod(lambda: None)}))
    said = []
    out = asyncio.run(loop_mod.langchain_chat(Settings())([{"role": "user", "content": "x"}], [], said.append))
    assert "".join(said) == "Đi mấy ngày?" and out.text == "Đi mấy ngày?"
    assert [(t["id"], t["name"], t["args"]) for t in out.tool_call_chunks] == [
        ("c1", "record_fact", '{"field": "days"}'), ("c2", "record_fact", "{not json")]
