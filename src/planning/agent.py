"""One agent call per typed message on the Planning screen (docs/specs/PLANNING_SPEC.md §Vòng người dùng sửa và góp
ý): prompt from the session's current laid-out trip, streamed `say`, typed plan. Same streaming guards as
src/decision/agent.py and src/trip/agent.py, kept here: modules only meet through public APIs."""

import asyncio
import json
import re
from typing import AsyncIterator, Callable

from pydantic import ValidationError

from corpus.llm import AGENT, PLANNING_TURN

from .guard import TurnPlan

LOOP_WS = 32  # guided decoding now and then emits whitespace until max_tokens; this many in a row means it started


class AgentError(Exception):
    """No usable plan in time; the turn falls back to the policy."""


class SayStream:
    """Pulls the "say" string out of a JSON object while it streams in."""

    def __init__(self):
        self.buf = ""
        self.sent = 0

    def feed(self, delta: str) -> str:
        self.buf += delta
        m = re.search(r'"say"\s*:\s*"', self.buf)
        if not m:
            return ""
        raw = self.buf[m.end():]
        end = _closing_quote(raw)
        raw = raw[:end] if end is not None else _trim_partial_escape(raw)
        try:
            text = json.loads('"' + raw + '"')
        except json.JSONDecodeError:
            return ""
        new, self.sent = text[self.sent:], max(self.sent, len(text))
        return new


def _closing_quote(raw: str) -> int | None:
    i = 0
    while i < len(raw):
        if raw[i] == "\\":
            i += 2
            continue
        if raw[i] == '"':
            return i
        i += 1
    return None


def _trim_partial_escape(raw: str) -> str:
    m = re.search(r"\\u[0-9a-fA-F]{0,3}$", raw)
    if m:
        return raw[:m.start()]
    tail = len(raw) - len(raw.rstrip("\\"))
    return raw[:-1] if tail % 2 else raw


def gemma_stream(fields: dict) -> AsyncIterator[str]:
    async def gen():
        client, model = AGENT.client()
        try:
            async for d in PLANNING_TURN.stream(client, model, **fields):
                yield d
        finally:
            await client.close()
    return gen()


class _Looping(AgentError):
    pass


async def run_agent(fields: dict, on_say: Callable[[str], None], cfg,
                    open_stream: Callable[[dict], AsyncIterator[str]] = gemma_stream) -> TurnPlan:
    """One call, or two when the first loops on whitespace; the second does not stream its say again."""
    deadline = asyncio.get_running_loop().time() + cfg.total_s
    try:
        return await _attempt(fields, on_say, cfg, open_stream, deadline)
    except _Looping:
        try:
            return await _attempt(fields, lambda s: None, cfg, open_stream, deadline)
        except _Looping as e:
            raise AgentError("output looped on whitespace twice") from e


async def _attempt(fields, on_say, cfg, open_stream, deadline) -> TurnPlan:
    loop = asyncio.get_running_loop()
    it = open_stream(fields).__aiter__()
    say, buf, first = SayStream(), [], True
    try:
        while True:
            timeout = cfg.first_token_s if first else deadline - loop.time()
            if timeout <= 0:
                raise AgentError(f"no complete answer in {cfg.total_s:.0f} s")
            try:
                delta = await asyncio.wait_for(it.__anext__(), timeout)
            except StopAsyncIteration:
                break
            first = False
            buf.append(delta)
            if new := say.feed(delta):
                on_say(new)
            tail = "".join(buf[-LOOP_WS:])[-LOOP_WS:]
            if len(tail) == LOOP_WS and not tail.strip():
                raise _Looping("whitespace loop")
    except asyncio.TimeoutError as e:
        raise AgentError("first token too slow" if first else "answer too slow") from e
    except AgentError:
        raise
    except Exception as e:  # openai errors, and httpx / OS errors a dropped stream raises unwrapped
        raise AgentError(f"{type(e).__name__}: {e}") from e
    finally:
        aclose = getattr(it, "aclose", None)
        if aclose:
            try:
                await aclose()
            except Exception:
                pass
    try:
        return TurnPlan.model_validate_json("".join(buf))
    except ValidationError as e:
        raise AgentError(f"bad plan: {str(e).splitlines()[0]}") from e
