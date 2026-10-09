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
THOUGHT_OPEN, THOUGHT_CLOSE = "<|channel>", "<channel|>"


class Visible:
    """Streamed text minus the reasoning blocks some models (Gemma) write into the content:
    "<|channel>thought ...<channel|>", in front of the reply or after it. A block is held back until it closes, then
    dropped; text that only might be the start of a marker waits for the next delta."""

    def __init__(self):
        self.buf, self.thought = "", False

    def feed(self, delta: str) -> str:
        self.buf += delta
        out = ""
        while True:
            if self.thought:
                i = self.buf.find(THOUGHT_CLOSE)
                if i < 0:
                    return out
                self.buf, self.thought = self.buf[i + len(THOUGHT_CLOSE):].lstrip(), False
                continue
            i = self.buf.find(THOUGHT_OPEN)
            if i >= 0:
                out += self.buf[:i]
                self.buf, self.thought = self.buf[i + len(THOUGHT_OPEN):], True
                continue
            keep = next((k for k in range(min(len(self.buf), len(THOUGHT_OPEN) - 1), 0, -1)
                         if THOUGHT_OPEN.startswith(self.buf[-k:])), 0)  # a marker may be cut between deltas
            out += self.buf[:len(self.buf) - keep]
            self.buf = self.buf[len(self.buf) - keep:]
            return out.replace(THOUGHT_CLOSE, "")

    def end(self) -> str:
        """Held text when the stream ends: a partial marker is text after all; an unclosed thought is dropped."""
        out, self.buf = ("" if self.thought else self.buf), ""
        return out


def openai_chat(cfg: Settings) -> Chat:
    """One streamed chat-completions call with native function calling, on the Agent role's endpoint."""
    async def chat(messages: list[dict], tools: list[dict], on_say: Callable[[str], None]) -> Assistant:
        client, model = AGENT.client()
        out, parts, visible = Assistant(), {}, Visible()

        def show(text: str) -> None:
            if text:
                out.content += text
                on_say(text)
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
                        show(visible.feed(delta.content))
                    for t in delta.tool_calls or ():
                        p = parts.setdefault(t.index, Call(t.id or f"call_{uuid.uuid4().hex[:8]}", "", ""))
                        if t.function and t.function.name:
                            p.name += t.function.name
                        if t.function and t.function.arguments:
                            p.arguments += t.function.arguments
                show(visible.end())
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
        tools.prefetch(reply.calls, reply.content)  # Clef's checks on this reply, all sent at once
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
