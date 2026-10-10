"""The Trip agent's model client: one LangChain ChatOpenAI call per turn step."""

import json
import re
import uuid
from contextlib import suppress
from collections.abc import Callable

from langchain_openai import ChatOpenAI

from agents import AgentError

import httpx

from corpus.llm import AGENT

from ..infrastructure.settings import Settings
from .loop import Assistant, Call, Chat

THOUGHT_OPEN, THOUGHT_CLOSE = "<|channel>", "<channel|>"
_THOUGHT_RE = re.compile(re.escape(THOUGHT_OPEN) + r".*?" + re.escape(THOUGHT_CLOSE), re.S)


def strip_thought(text: str) -> str:
    """Reasoning blocks some models (Gemma) write into one non-streamed reply, "<|channel>thought ...<channel|>",
    in front of the reply or after it. A block is dropped; an unclosed marker drops to the end of the text, like the
    old streaming filter did when the stream ended inside a thought."""
    out = _THOUGHT_RE.sub("", text or "")
    i = out.find(THOUGHT_OPEN)
    return out[:i] if i >= 0 else out


def _build_llm(cfg: Settings, params: dict, http_client: httpx.AsyncClient) -> ChatOpenAI:
    # Our own httpx client, closed by the caller after the call: langchain lru_caches one httpx client per
    # (base_url, timeout), and reusing it across turns dies with "Event loop is closed" (each turn runs on a fresh
    # asyncio loop). The httpx.Timeout (unhashable, not a float) is a second lock on the same door.
    return ChatOpenAI(model=params["model"], api_key=params["api_key"], base_url=params["base_url"],
                      temperature=0.2, max_tokens=cfg.max_tokens, request_timeout=httpx.Timeout(cfg.total_s),
                      http_async_client=http_client).with_config({"run_name": "trip-agent"})


def openai_chat(cfg: Settings) -> Chat:
    """One chat-completions call per turn step, through LangChain's ChatOpenAI (streaming off: the turn shows only
    after Clef lets it through). The Agent role's endpoint still comes from corpus.llm; tracing lights up in
    LangSmith whenever LANGSMITH_TRACING is set in the environment."""
    async def chat(messages: list[dict], tools: list[dict], on_say: Callable[[str], None]) -> Assistant:
        http = httpx.AsyncClient()
        try:
            bound = _build_llm(cfg, AGENT.llm_params(), http)
            bound = bound.bind_tools(tools) if tools else bound
            try:
                msg = await bound.ainvoke(messages)
            except Exception as e:  # Exception, not BaseException: engine cancels this awaitable, and CancelledError must propagate
                raise AgentError(f"agent call failed: {type(e).__name__}: {str(e)[:200]}") from e
        finally:
            with suppress(Exception):
                await http.aclose()
        content = strip_thought(msg.content if isinstance(msg.content, str) else "")
        calls = [Call(id=t.get("id") or f"call_{uuid.uuid4().hex[:8]}", name=t.get("name", ""),
                      arguments=json.dumps(t.get("args") or {}, ensure_ascii=False))
                 for t in (msg.tool_calls or [])]
        if content:
            on_say(content)
        return Assistant(content=content, calls=calls)
    return chat
