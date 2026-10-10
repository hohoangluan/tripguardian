import asyncio

import pytest
from trip_fixtures import ScriptedChat, ask, fact, reply

from datetime import date

from trip.agent import AgentError, TurnTools, run_loop
from trip.domain.state import TripState


def run(chat, catalog, text="đi 3 ngày với bạn bè", max_steps=6):
    tools = TurnTools(TripState(), text, 1, catalog, date(2026, 10, 8))
    messages = [{"role": "user", "content": text}]
    said = []
    asyncio.run(run_loop(chat, messages, tools, said.append, max_steps))
    return tools, messages, said


def test_the_loop_stops_at_the_first_stopping_tool_and_skips_the_rest(catalog):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày"), ask("Đi bằng gì?", "Xe máy", "Ô tô"), ask("Đi cùng ai?", "Một mình", "Bạn bè")))
    tools, messages, _ = run(chat, catalog)
    assert chat.calls == 1 and tools.card.text == "Đi bằng gì?"
    assert [m["role"] for m in messages] == ["user", "assistant", "tool", "tool"]


def test_tool_results_go_back_to_the_model_and_the_loop_goes_on(catalog):
    chat = ScriptedChat(reply(fact("days", "9", "9 ngày")), reply(fact("days", "3", "3 ngày")),
                        reply(ask("Đi bằng gì?", "Xe máy", "Ô tô")))
    tools, messages, _ = run(chat, catalog)
    assert chat.calls == 3 and tools.state.days.value == 3
    assert messages[2]["role"] == "tool" and "error" in messages[2]["content"]
    assert messages[1]["tool_calls"][0]["id"] == messages[2]["tool_call_id"]


def test_a_plain_text_reply_ends_the_loop_with_no_card(catalog):
    tools, _, said = run(ScriptedChat(reply(text="Tháng 12 khá lạnh.")), catalog)
    assert tools.card is None and said == ["Tháng 12 khá lạnh."]


def test_the_loop_is_bounded(catalog):
    chat = ScriptedChat(*[reply(fact("days", "3", "3 ngày")) for _ in range(10)])
    tools, _, _ = run(chat, catalog, max_steps=3)
    assert chat.calls == 3 and "step_cap" in tools.log and tools.card is None


def test_no_steps_means_no_model_call(catalog):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày")))
    tools, _, _ = run(chat, catalog, max_steps=0)
    assert chat.calls == 0 and "step_cap" in tools.log and tools.card is None


def test_the_loop_writes_the_tool_calls_into_the_callers_own_message_list(catalog):
    # the engine reads the messages the loop built to show the turn's tool calls; a state copy would break it
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày"), ask("Đi bằng gì?", "Xe máy", "Ô tô")))
    tools, messages, _ = run(chat, catalog)
    assert messages is not None and [m["role"] for m in messages] == ["user", "assistant", "tool", "tool"]
    assert messages[1]["tool_calls"][0]["function"]["name"] in ("record_fact", "ask_choice")


def test_malformed_arguments_are_an_error_result_not_a_crash(catalog):
    from trip.agent import Assistant, Call
    bad = Assistant(calls=[Call("c1", "record_fact", "{not json")])
    tools, messages, _ = run(ScriptedChat(bad, reply(ask("Đi mấy ngày?", "1-2", "3-4"))), catalog)
    assert "error" in messages[2]["content"] and tools.card is not None


def test_a_model_failure_propagates_after_the_facts_already_written(catalog):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày")))
    tools = TurnTools(TripState(), "đi 3 ngày", 1, catalog, date(2026, 10, 8))
    with pytest.raises(AgentError):
        asyncio.run(run_loop(chat, [{"role": "user", "content": "x"}], tools, lambda _: None, 6))
    assert tools.state.days.value == 3


def test_an_unmapped_wish_ends_the_loop_without_another_model_call(catalog):
    chat = ScriptedChat(reply(fact("unmapped", "chó", "chó", op="add")), reply(ask("?", "a", "b")))
    tools, _, _ = run(chat, catalog, text="muốn có chó")
    assert chat.calls == 1 and tools.unmapped == ["chó"] and tools.card is None


def test_a_reasoning_block_in_the_reply_is_never_shown():
    from trip.agent import strip_thought
    assert strip_thought("<|channel>thought\nkế hoạch<channel|>Mình hiểu rồi.") == "Mình hiểu rồi."
    assert strip_thought("<b>Chào") == "<b>Chào"  # text that only starts like the marker
    assert strip_thought("<|channel>thought only") == ""
    # Gemma also writes an empty block after its text
    assert strip_thought("Bạn đi mấy ngày?\n\n<|channel>thought\n<channel|>") == "Bạn đi mấy ngày?\n\n"


def test_each_model_call_gets_its_own_http_client(catalog, cfg):
    # langchain lru_caches one httpx client per (base_url, timeout): sharing it across turns dies with
    # "Event loop is closed" (each turn runs on a fresh asyncio loop). The client owns its httpx client and
    # closes it after the call. No network: construction only.
    import httpx

    from trip.agent.client import _build_llm
    params = {"model": "m", "api_key": "k", "base_url": "http://127.0.0.1:1"}
    h1, h2 = httpx.AsyncClient(), httpx.AsyncClient()
    try:
        a, b = _build_llm(cfg, params, h1), _build_llm(cfg, params, h2)
        assert a.root_async_client._client is h1
        assert b.root_async_client._client is h2
    finally:
        import asyncio

        async def close():
            await h1.aclose()
            await h2.aclose()
        asyncio.run(close())
