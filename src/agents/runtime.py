"""Shared structured streaming; business policy remains in the calling module."""

import asyncio
import json
import re
from typing import AsyncIterator, Callable, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from .limit import CapacityError, load_limiter


_limiter = load_limiter()


class RuntimeSettings(Protocol):
    first_token_s: float
    total_s: float


PlanT = TypeVar("PlanT", bound=BaseModel)


class AgentError(Exception):
    """The agent did not give a usable plan in time; the turn falls back to the policy."""


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


LOOP_WS = 32  # guided decoding now and then emits whitespace until max_tokens; this many in a row means it started


async def run_structured(fields: dict, on_say: Callable[[str], None], cfg: RuntimeSettings, schema: type[PlanT],
                    open_stream: Callable[[dict], AsyncIterator[str]]) -> PlanT:
    """One call, or two when the first loops on whitespace; the second does not stream its say again."""
    deadline = asyncio.get_running_loop().time() + cfg.total_s
    try:
        async with _limiter.permit(deadline):
            try:
                return await _attempt(fields, on_say, cfg, schema, open_stream, deadline)
            except _Looping:
                try:
                    return await _attempt(fields, lambda s: None, cfg, schema, open_stream, deadline)
                except _Looping as e:
                    raise AgentError("output looped on whitespace twice") from e
    except CapacityError as e:
        raise AgentError(str(e)) from e


class _Looping(AgentError):
    pass


async def _next_token(it: AsyncIterator[str], timeout: float, deadline: float) -> str:
    # The absolute deadline also interrupts slow cleanup after the first-token cancellation.
    async with asyncio.timeout_at(deadline):
        return await asyncio.wait_for(it.__anext__(), timeout)


async def _attempt(fields: dict, on_say: Callable[[str], None], cfg: RuntimeSettings,
                   schema: type[PlanT], open_stream: Callable[[dict], AsyncIterator[str]], deadline: float) -> PlanT:
    loop = asyncio.get_running_loop()
    it = None
    say, buf, first = SayStream(), [], True
    try:
        it = open_stream(fields).__aiter__()
        while True:
            remaining = deadline - loop.time()
            timeout = min(cfg.first_token_s, remaining) if first else remaining
            if timeout <= 0:
                raise AgentError(f"no complete answer in {cfg.total_s:.0f} s")
            try:
                delta = await _next_token(it, timeout, deadline)
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
                remaining = max(0.0, deadline - loop.time())
                await asyncio.wait_for(aclose(), timeout=remaining)
            except Exception:
                pass
    try:
        return schema.model_validate_json("".join(buf))
    except ValidationError as e:
        raise AgentError(f"bad plan: {str(e).splitlines()[0]}") from e
