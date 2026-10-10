"""One agent call per typed message on the curation screen (docs/P3_PLACE_DECISION.md §18): prompt from the current view, streamed `say`,
typed plan. Streaming deadlines and retry are handled by the shared agents runtime."""

import functools
from collections.abc import AsyncIterator, Callable

from agents import AgentError, SayStream, run_structured  # AgentError, SayStream: re-exported for engine and tests

from corpus.llm import AGENT, DECISION_TURN
from corpus.ontology import load

from .guard import TurnPlan


@functools.cache
def features_text() -> str:
    return "\n".join(f"{f.id}: {'|'.join(f.values)}" for f in load().features.values())


def gemma_stream(fields: dict) -> AsyncIterator[str]:
    async def gen():
        client, model = AGENT.client()
        try:
            async for d in DECISION_TURN.stream(client, model, **fields):
                yield d
        finally:
            await client.close()
    return gen()


async def run_agent(fields: dict, on_say: Callable[[str], None], cfg,
                    open_stream: Callable[[dict], AsyncIterator[str]] = gemma_stream) -> TurnPlan:
    """Stream a typed plan with the shared runtime deadlines and retry policy."""
    return await run_structured(fields, on_say, cfg, TurnPlan, open_stream)
