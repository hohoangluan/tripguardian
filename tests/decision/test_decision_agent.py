import asyncio
import json

import pytest

from decision.agent import AgentError, SayStream, run_agent
from decision.settings import default

CFG = default()
PLAN = {"say": "Mình đã bỏ Cầu Đất.", "updates": [{"op": "drop", "place": "P1", "value": "far", "quote": "xa"}]}


def stream_of(chunks, delay=0.0, first_delay=0.0):
    async def gen():
        await asyncio.sleep(first_delay)
        for c in chunks:
            await asyncio.sleep(delay)
            yield c
    return lambda fields: gen()


def chunks(obj, n=7):
    s = json.dumps(obj, ensure_ascii=False)
    return [s[i:i + n] for i in range(0, len(s), n)]


def test_say_stream_extracts_text_as_it_arrives():
    s = SayStream()
    got = "".join(s.feed(c) for c in chunks(PLAN, 3))
    assert got == "Mình đã bỏ Cầu Đất."


def test_run_agent_streams_say_and_returns_plan():
    said = []
    p = asyncio.run(run_agent({}, said.append, CFG, stream_of(chunks(PLAN))))
    assert "".join(said) == PLAN["say"] and p.updates[0].place == "P1"


def test_errors_become_agent_error():
    with pytest.raises(AgentError):
        asyncio.run(run_agent({}, lambda s: None, CFG, stream_of(['{"say": "x"'])))  # broken JSON
    with pytest.raises(AgentError):
        asyncio.run(run_agent({}, lambda s: None, CFG, stream_of([" " * 40, " " * 40])))  # whitespace loop twice
    slow = type(CFG)(**{**CFG.__dict__, "first_token_s": 0.05})
    with pytest.raises(AgentError):
        asyncio.run(run_agent({}, lambda s: None, slow, stream_of(chunks(PLAN), first_delay=0.3)))
