"""One agent call per typed message on the Planning screen (docs/P4_PLANNING.md §Vòng người dùng sửa và góp
ý): prompt from the session's current laid-out trip, streamed `say`, typed plan. Streaming deadlines and retry are handled by the shared agents runtime."""

from collections.abc import AsyncIterator, Callable

from agents import AgentError, SayStream, run_structured  # AgentError, SayStream: re-exported for engine and tests

from corpus.llm import AGENT, PLANNING_TURN

from .guard import TurnPlan

def gemma_stream(fields: dict) -> AsyncIterator[str]:
    async def gen():
        client, model = AGENT.client()
        try:
            async for d in PLANNING_TURN.stream(client, model, **fields):
                yield d
        finally:
            await client.close()
    return gen()


async def run_agent(fields: dict, on_say: Callable[[str], None], cfg,
                    open_stream: Callable[[dict], AsyncIterator[str]] = gemma_stream) -> TurnPlan:
    """Stream a typed plan with the shared runtime deadlines and retry policy."""
    return await run_structured(fields, on_say, cfg, TurnPlan, open_stream)
