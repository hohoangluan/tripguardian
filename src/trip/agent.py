"""One agent call per free-text turn: prompt from prefetched facts, streamed say, typed plan (docs/TRIP_UNDERSTANDING.md §4, §14)."""

import functools
import json
import re
from datetime import date
from typing import AsyncIterator, Callable

from agents import AgentError, SayStream, run_structured

from corpus.llm import AGENT, TRIP_TURN

from .guard import TurnPlan
from .prepass import Prepass
from .questions import Question
from .settings import Settings
from .state import SCALARS, Base, TripState, ontology


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
        "idle_left": max(0, cfg.idle_limit - state.meta.idle_streak),
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


async def run_agent(fields: dict, on_say: Callable[[str], None], cfg: Settings,
                    open_stream: Callable[[dict], AsyncIterator[str]] = gemma_stream) -> TurnPlan:
    """Stream a typed plan with the shared runtime deadlines and retry policy."""
    return await run_structured(fields, on_say, cfg, TurnPlan, open_stream)
