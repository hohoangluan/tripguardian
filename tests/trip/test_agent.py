import asyncio
import json
from datetime import date

import pytest

from corpus.llm import TRIP_TURN
from corpus.llm.tasks import TRIP_FIELDS
from trip.agent import AgentError, SayStream, prompt_fields, run_agent
from trip.guard import PlanUpdate
from trip.prepass import prepass
from trip.questions import c_effort
from trip.settings import Settings
from trip.state import TripState, ontology

PLAN = {"say": "Mình hiểu rồi.", "updates": [], "next": {"kind": "ask", "qid": "pace", "custom_text": "",
                                                       "custom_chips": [], "reason": ""}}


def test_say_stream_handles_split_escapes():
    s, out = SayStream(), []
    for piece in ['{"say": "Chào b', 'ạn \\"x\\" và \\u00', 'e0 nhé", "upd', 'ates": []}']:
        out.append(s.feed(piece))
    assert "".join(out) == 'Chào bạn "x" và à nhé'


def test_prompt_renders_with_every_field():
    st = TripState()
    f = prompt_fields(st, "đi 3 ngày", prepass("đi 3 ngày", date(2026, 10, 2)), c_effort(st), [], Settings(),
                      "Câu trước?", date(2026, 10, 2))
    text = TRIP_TURN.render(**f)
    assert "REQUIRED: c_effort" in text and "đi 3 ngày" in text
    assert all(fid in text for fid in ontology().features)


def test_schema_fields_match_the_guard():
    assert set(TRIP_FIELDS) == set(PlanUpdate.model_fields["field"].annotation.__args__)


def fake(chunks, delay=0.0):
    def open_stream(fields):
        async def gen():
            for c in chunks:
                await asyncio.sleep(delay)
                yield c
        return gen()
    return open_stream


def test_run_agent_streams_say_and_returns_plan():
    raw = json.dumps(PLAN, ensure_ascii=False)
    said = []
    plan = asyncio.run(run_agent({}, said.append, Settings(), open_stream=fake([raw[:12], raw[12:30], raw[30:]])))
    assert "".join(said) == "Mình hiểu rồi." and plan.next.qid == "pace"


def test_run_agent_times_out_on_first_token():
    with pytest.raises(AgentError):
        asyncio.run(run_agent({}, lambda s: None, Settings(first_token_s=0.05), open_stream=fake(["{}"], delay=0.5)))


def test_run_agent_rejects_bad_json():
    with pytest.raises(AgentError):
        asyncio.run(run_agent({}, lambda s: None, Settings(), open_stream=fake(['{"say": "x"'])))


def attempts(*runs):
    """open_stream that plays one chunk list per call."""
    calls = []

    def open_stream(fields):
        chunks = runs[len(calls)]
        calls.append(1)

        async def gen():
            for c in chunks:
                yield c
        return gen()
    open_stream.calls = calls
    return open_stream


def test_whitespace_loop_is_cut_and_retried_once():
    raw = json.dumps(PLAN, ensure_ascii=False)
    looping = ['{"say": "Mình", "updates": [', " " * 20, " " * 20, " \n" * 400]
    said = []
    stream = attempts(looping, [raw])
    plan = asyncio.run(run_agent({}, said.append, Settings(), open_stream=stream))
    assert plan.next.qid == "pace" and len(stream.calls) == 2
    assert "".join(said) == "Mình"  # the retry does not stream its say again


def test_whitespace_loop_twice_gives_up():
    looping = ['{"say": "x", "updates": [', " " * 64]
    with pytest.raises(AgentError):
        asyncio.run(run_agent({}, lambda s: None, Settings(), open_stream=attempts(looping, looping)))


def test_dropped_connection_mid_stream_becomes_agent_error():
    import httpx

    def open_stream(fields):
        async def gen():
            yield '{"say": "a'
            raise httpx.ReadError("connection closed")
        return gen()
    with pytest.raises(AgentError):
        asyncio.run(run_agent({}, lambda s: None, Settings(), open_stream=open_stream))
