"""The Trip agent loop: the model calls tools until it asks the user, finishes, or runs out of steps."""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable

import openai
from agents import AgentError

from corpus.llm import AGENT

from ..infrastructure.settings import Settings
from .tools import TurnTools


@dataclass
class Call:
    id: str
    name: str
    arguments: str


@dataclass
class Assistant:
    content: str = ""
    calls: list[Call] = field(default_factory=list)


Chat = Callable[[list[dict], list[dict], Callable[[str], None]], Awaitable[Assistant]]


def openai_chat(cfg: Settings) -> Chat:
    """One streamed chat-completions call with native function calling, on the Agent role's endpoint."""
    async def chat(messages: list[dict], tools: list[dict], on_say: Callable[[str], None]) -> Assistant:
        client, model = AGENT.client()
        out, parts = Assistant(), {}
        try:
            async with asyncio.timeout(cfg.total_s):
                stream = await client.chat.completions.create(
                    model=model, messages=messages, tools=tools, tool_choice="auto", temperature=0.2,
                    max_tokens=cfg.max_tokens, stream=True)
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta.content:
                        out.content += delta.content
                        on_say(delta.content)
                    for t in delta.tool_calls or ():
                        p = parts.setdefault(t.index, Call(t.id or f"call_{uuid.uuid4().hex[:8]}", "", ""))
                        if t.function and t.function.name:
                            p.name += t.function.name
                        if t.function and t.function.arguments:
                            p.arguments += t.function.arguments
        except (openai.OpenAIError, TimeoutError) as e:
            raise AgentError(f"agent call failed: {type(e).__name__}: {str(e)[:200]}") from e
        finally:
            await client.close()
        out.calls = [parts[i] for i in sorted(parts)]
        return out
    return chat


def _wire(call: Call) -> dict:
    return {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.arguments or "{}"}}


async def run_loop(chat: Chat, messages: list[dict], tools: TurnTools, on_say: Callable[[str], None],
                   max_steps: int) -> None:
    """Runs until a stopping tool succeeds, a wish ends up unmapped, the model answers in plain text, or max_steps calls are spent.
    The result is in `tools` (state, card, outcome, log). An AgentError keeps whatever facts were already written."""
    for _ in range(max_steps):
        reply = await chat(messages, tools.specs(), on_say)
        if not reply.calls:  # a plain answer: nothing to wait on, the engine opens a free-text card
            return
        messages.append({"role": "assistant", "content": reply.content or None, "tool_calls": [_wire(c) for c in reply.calls]})
        for call in reply.calls:
            try:
                args = json.loads(call.arguments or "{}")
                if not isinstance(args, dict):
                    raise ValueError
                result = tools.run(call.name, args)
            except ValueError:
                result = {"error": "arguments are not a JSON object"}
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False)})
            if tools.stopped:
                return
        if tools.unmapped:  # a wish no search feature expresses: the engine answers with a fixed reply, no more model calls
            return
    tools.log.append("step_cap")
