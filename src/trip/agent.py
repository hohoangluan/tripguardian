"""One agent call per free-text turn: prompt from prefetched facts, streamed say, typed plan (docs/TRIP_UNDERSTANDING.md §4, §14)."""

import asyncio
import functools
import json
import re
from datetime import date
from typing import AsyncIterator, Callable

from pydantic import ValidationError

from corpus.llm import AGENT, TRIP_TURN

from .guard import TurnPlan
from .prepass import Prepass
from .questions import Question
from .settings import Settings
from .state import SCALARS, Base, TripState, ontology


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


@functools.cache
def _features() -> str:
    o = ontology()
    lines = [f"{f.id}: {'|'.join(f.values)} - {re.split(r'[;(:]', f.hint)[0].strip()[:70]}" for f in o.features.values()]
    return "\n".join(lines) + "\ncontexts: " + "; ".join(f"{k}: {'|'.join(v)}" for k, v in o.contexts.items())


def _plain(v):
    if isinstance(v, (frozenset, set)):
        return sorted(v)
    if isinstance(v, Base):
        return v.text
    return v.isoformat() if isinstance(v, date) else v


def summarize(state: TripState) -> str:
    out: dict = {}
    for f in SCALARS + ("companions",):
        x = getattr(state, f)
        if x.known:
            out[f] = {"value": _plain(x.value), "source": x.source}
    if state.soft:
        out["soft"] = {k: f.value for k, f in state.soft.items()}
    if state.hard:
        out["hard"] = [f"{h.feature}{'!=' if h.op == 'ne' else '='}{h.value}" for h in state.hard]
    if state.anchors:
        out["anchors"] = [a.text for a in state.anchors]
    if state.signals:
        out["signals"] = [s.kind + ("" if s.handled else " (open)") for s in state.signals]
    if state.unmapped:
        out["unmapped"] = [u.phrase for u in state.unmapped]
    return json.dumps(out, ensure_ascii=False, default=str)


def prompt_fields(state: TripState, text: str, pre: Prepass, required: Question | None,
                  ranked: list[tuple[Question, float]], cfg: Settings, last_question: str | None, today: date) -> dict:
    hits = [{"field": p.field, "value": _plain(p.value), "quote": p.quote} for p in pre.proposals]
    hits += [{"ambiguous": q, "may_mean": list(k)} for q, k in pre.ambiguous]
    return {
        "features": _features(),
        "state": summarize(state),
        "text": text,
        "prepass": json.dumps(hits, ensure_ascii=False, default=str),
        "required": f"{required.qid}: {required.text}" if required else "none",
        "candidates": "\n".join(f"{q.qid}: {q.text}" for q, _ in ranked[:5]) or "none",
        "budget": max(0, cfg.turn_budget - state.meta.adaptive_turns),
        "experience": state.meta.experience or "unknown",
        "last_question": last_question or "none",
        "today": today.isoformat(),
    }


def gemma_stream(fields: dict) -> AsyncIterator[str]:
    async def gen():
        client, model = AGENT.client()
        try:
            async for d in TRIP_TURN.stream(client, model, **fields):
                yield d
        finally:
            await client.close()
    return gen()


LOOP_WS = 32  # guided decoding now and then emits whitespace until max_tokens; this many in a row means it started


async def run_agent(fields: dict, on_say: Callable[[str], None], cfg: Settings,
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


class _Looping(AgentError):
    pass


async def _attempt(fields: dict, on_say: Callable[[str], None], cfg: Settings,
                   open_stream: Callable[[dict], AsyncIterator[str]], deadline: float) -> TurnPlan:
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
