import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from tests.agents.test_runtime import Plan
from trip.settings import Settings


def gate(monkeypatch, waiting=2):
    from agents.limit import ProcessLimiter
    import agents.runtime as runtime
    limiter = ProcessLimiter(max_parallel=1, max_waiting=waiting)
    monkeypatch.setattr(runtime, '_limiter', limiter)
    return limiter


def test_process_limit_across_event_loops(monkeypatch):
    from agents import run_structured
    limiter = gate(monkeypatch)
    lock, start = threading.Lock(), threading.Barrier(3)
    active = maximum = 0
    async def stream(fields):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        try:
            await asyncio.sleep(0.025)
            yield '{"say":"ok","value":1}'
        finally:
            with lock:
                active -= 1
    def worker():
        start.wait()
        return asyncio.run(run_structured({}, lambda s: None, Settings(first_token_s=1,total_s=1), Plan, stream))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        start.wait()
        assert [f.result().value for f in futures] == [1, 1]
    assert maximum == 1
    assert limiter.counts == (0, 0)


def test_full_queue_expiry_cancellation_and_release(monkeypatch):
    from agents import AgentError, run_structured
    limiter = gate(monkeypatch, waiting=1)
    async def scenario():
        started, finish = asyncio.Event(), asyncio.Event()
        async def stream(fields):
            started.set()
            await finish.wait()
            yield '{"say":"ok","value":1}'
        cfg = Settings(first_token_s=1, total_s=1)
        def launch(settings=cfg):
            return asyncio.create_task(run_structured({}, lambda s: None, settings, Plan, stream))
        active = launch()
        await started.wait()
        waiter = launch()
        await asyncio.sleep(0)
        with pytest.raises(AgentError, match='queue full'):
            await launch()
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert limiter.counts == (1, 0)
        with pytest.raises(AgentError, match='queue deadline'):
            await launch(Settings(first_token_s=1, total_s=0.01))
        assert limiter.counts == (1, 0)
        active.cancel()
        with pytest.raises(asyncio.CancelledError):
            await active
        assert limiter.counts == (0, 0)
        finish.set()
        assert (await launch()).value == 1
    asyncio.run(scenario())
    assert limiter.counts == (0, 0)


def test_stream_error_releases_permit(monkeypatch):
    from agents import AgentError, run_structured
    limiter = gate(monkeypatch)
    async def stream(fields):
        raise OSError('disconnect')
        yield ''
    with pytest.raises(AgentError):
        asyncio.run(run_structured({}, lambda s: None, Settings(), Plan, stream))
    assert limiter.counts == (0, 0)


def test_permit_tool_requires_declared_tool():
    from agents import load_skill, permit_tool
    skill = load_skill('src/trip/skills.yaml')
    assert permit_tool(skill, 'trip.compile').access == 'read'
    with pytest.raises(ValueError):
        permit_tool(skill, 'decision.compare')
