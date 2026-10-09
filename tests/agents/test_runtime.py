import asyncio
import json

import pytest
from pydantic import BaseModel

from trip.infrastructure.settings import Settings


class Plan(BaseModel):
    say: str
    value: int


def run(stream, cfg=None, said=None):
    from agents import run_structured
    return asyncio.run(run_structured({}, (said if said is not None else []).append,
                                     cfg or Settings(first_token_s=0.01, total_s=0.05), Plan, stream))


def chunks(*parts):
    async def gen(fields):
        for part in parts:
            yield part
    return gen


def test_split_json_and_escapes():
    said = []
    plan = run(chunks('{"say":"Hi \\u00', 'e0 \\"yes\\"",', '"value":2}'), said=said)
    assert plan.value == 2
    assert ''.join(said) == 'Hi à "yes"'


@pytest.mark.parametrize('mode', ['first', 'total', 'json', 'network', 'open'])
def test_errors_close_stream(mode):
    from agents import AgentError
    closed = []
    async def gen(fields):
        try:
            if mode == 'first':
                await asyncio.sleep(0.1)
            yield '{"say":"x"'
            if mode == 'total':
                await asyncio.sleep(0.1)
            if mode == 'network':
                raise OSError('disconnected')
        finally:
            closed.append(True)
    def opening(fields):
        raise OSError('open failed')
    with pytest.raises(AgentError):
        run(opening if mode == 'open' else gen)
    assert mode == 'open' or closed == [True]


def test_retry_once_and_suppress_second_say():
    calls, closed, said = [], [], []
    async def gen(fields):
        calls.append(1)
        try:
            if len(calls) == 1:
                yield '{"say":"first",'
                yield ' ' * 32
            else:
                yield json.dumps({'say': 'second', 'value': 3})
        finally:
            closed.append(1)
    assert run(gen, said=said).value == 3
    assert said == ['first'] and len(calls) == len(closed) == 2


def test_retry_uses_remaining_total_deadline_for_first_token():
    from agents import AgentError
    calls = []
    async def gen(fields):
        calls.append(1)
        if len(calls) == 1:
            yield '{"say":"x",'
            await asyncio.sleep(0.035)
            yield ' ' * 32
        else:
            await asyncio.sleep(0.035)
            yield '{"say":"ok","value":1}'
    with pytest.raises(AgentError):
        run(gen, Settings(first_token_s=0.04, total_s=0.05))
    assert len(calls) == 2


def test_whitespace_twice_stops():
    from agents import AgentError
    calls = []
    async def gen(fields):
        calls.append(1)
        yield ' ' * 32
    with pytest.raises(AgentError, match='twice'):
        run(gen)
    assert len(calls) == 2


@pytest.mark.parametrize("fail", [False, True])
def test_slow_stream_close_obeys_total_deadline_and_releases_quota(fail):
    from agents import AgentError
    from agents.runtime import _limiter
    import time

    closed = []
    class SlowClose:
        sent = False
        def __aiter__(self):
            return self
        async def __anext__(self):
            if self.sent:
                if fail:
                    raise OSError("disconnected")
                raise StopAsyncIteration
            self.sent = True
            return '{"say":"ok","value":1}'
        async def aclose(self):
            try:
                await asyncio.sleep(0.15)
            finally:
                closed.append(True)
    started = time.monotonic()
    if fail:
        with pytest.raises(AgentError):
            run(lambda fields: SlowClose(), Settings(first_token_s=0.01, total_s=0.03))
    else:
        assert run(lambda fields: SlowClose(), Settings(first_token_s=0.01, total_s=0.03)).value == 1
    assert time.monotonic() - started < 0.12
    assert closed == [True]
    assert _limiter.counts == (0, 0)


def test_first_token_timeout_does_not_wait_for_generator_cancellation_cleanup():
    from agents import AgentError
    from agents.runtime import _limiter
    import time

    async def gen(fields):
        try:
            await asyncio.sleep(1)
            yield '{"say":"ok","value":1}'
        finally:
            await asyncio.sleep(0.15)
    started = time.monotonic()
    with pytest.raises(AgentError):
        run(gen, Settings(first_token_s=0.005, total_s=0.01))
    assert time.monotonic() - started < 0.10
    assert _limiter.counts == (0, 0)
