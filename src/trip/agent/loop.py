"""The Trip agent loop: the model calls tools until it asks the user, finishes, or runs out of steps."""

import asyncio
import inspect
import json
import logging
import operator
import re
import time
import uuid
from typing import Annotated, Awaitable, Callable, Literal, TypedDict

import httpx
import openai
from agents import AgentError
from langchain_core.messages import AIMessage, AIMessageChunk, convert_to_messages
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from langgraph.graph import END, START, StateGraph

from corpus.llm import AGENT

from ..domain.text import fold
from ..domain.guard import trim_say
from ..infrastructure.settings import Settings
from .tools import WISH_FIELDS, TurnTools, lc_tools

# Words in a reply that say something was written down. Such a reply with no record_fact in the turn is retried once.
CLAIM = ("da ghi", "ghi nhan", "ghi lai", "da cap nhat", "cap nhat lai", "da luu", "hieu la", "da hieu", "minh hieu")
REPLY_NOTE = ("Câu trả lời vừa rồi bị chặn vì: {why}. Viết lại một câu ngắn: không hứa kết quả, không nêu số hay "
              "địa điểm mà user chưa nói.")
RETRY_NOTE = ("Bạn vừa nói đã ghi nhận nhưng chưa gọi record_fact lần nào trong lượt này. Nếu tin nhắn mới nhất có "
              "một fact, hãy gọi record_fact cho fact đó ngay. Nếu không, đừng nói là đã ghi nhận.")
UNMAPPED_TEXT_NOTE = ("Bạn vừa ghi unmapped cho mong muốn này. Viết ngay một câu ngắn bằng lời user: nhắc lại mong muốn "
                      "và hỏi đúng MỘT câu tư vấn đưa nó về giá trị ghi được (hai cách hiểu cụ thể gắn với enum của field đó). "
                      "Không gọi thêm tool nào nữa.")
# Error results allowed in one turn before the loop stops calling tools and says the fallback.
MAX_TOOL_FAILS = 4
# The notes above are only ever sent to the model; this is how the persisted history recognises them.
NOTE_HEADS = tuple(n[:24] for n in (REPLY_NOTE.format(why=""), RETRY_NOTE, UNMAPPED_TEXT_NOTE))
log = logging.getLogger(__name__)


# Chat returns the merged LangChain message: `.text` is the reply, `.tool_call_chunks` the calls with raw argument strings.
# A chat may also take `on_args`: it is then handed the record_fact arguments written so far, while the call streams.
Chat = Callable[[list[dict], list[BaseTool], Callable[[str], None]], Awaitable[AIMessageChunk]]
THOUGHT_OPEN, THOUGHT_CLOSE = "<|channel>", "<channel|>"


class LoopState(TypedDict):
    """Checkpointed turn state: plain data only. The model, tools, pool and callbacks ride in the nodes'
    closure, never in here (they hold threads and futures and cannot serialize). `nudged` is the turn's
    single second chance: the first of claim-back, clef-back or unmapped-silence consumes it."""
    messages: Annotated[list, operator.add]
    steps: int
    fails: int  # error results so far this turn
    nudged: bool
    has_say: bool
    reply_content: str  # the latest assistant reply's text
    reply_calls: list  # its tool calls as plain {id, name, arguments} dicts
    ended: bool  # the turn is over: the routers send it to END


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


# BACKUP (2026-10-14): openai_chat, thay bằng langchain_chat. Để bật lại: bỏ dấu # và import Assistant/Call.
# def openai_chat(cfg: Settings) -> Chat:
#     """One streamed chat-completions call with native function calling, on the Agent role's endpoint."""
#     async def chat(messages: list[dict], tools: list[dict], on_say: Callable[[str], None]) -> Assistant:
#         client, model = AGENT.client()
#         out, parts, visible = Assistant(), {}, Visible()
#
#         def show(text: str) -> None:
#             if text:
#                 out.content += text
#                 on_say(text)
#         try:
#             async with asyncio.timeout(cfg.total_s):
#                 stream = await client.chat.completions.create(
#                     model=model, messages=messages, tools=tools, tool_choice="auto", temperature=0.2,
#                     max_tokens=cfg.max_tokens, stream=True)
#                 async for chunk in stream:
#                     if not chunk.choices:
#                         continue
#                     delta = chunk.choices[0].delta
#                     if delta.content:
#                         show(visible.feed(delta.content))
#                     for t in delta.tool_calls or ():
#                         p = parts.setdefault(t.index, Call(t.id or f"call_{uuid.uuid4().hex[:8]}", "", ""))
#                         if t.function and t.function.name:
#                             p.name += t.function.name
#                         if t.function and t.function.arguments:
#                             p.arguments += t.function.arguments
#                 show(visible.end())
#         except (openai.OpenAIError, TimeoutError) as e:
#             raise AgentError(f"agent call failed: {type(e).__name__}: {str(e)[:200]}") from e
#         finally:
#             await client.close()
#         out.calls = [parts[i] for i in sorted(parts)]
#         return out
#     return chat


def langchain_chat(cfg: Settings) -> Chat:
    """One streamed call on langchain_openai. Returns the merged message, not a copy of it: LangChain's `tool_calls`
    would turn broken JSON into {}, hiding the error from the loop, so the raw argument strings are read from
    `tool_call_chunks`. The reasoning block the model writes into the text is filtered here, before the loop sees it.
    The endpoint still comes from AGENT.client(): only the client library changes."""
    async def chat(messages: list[dict], tools: list[dict], on_say: Callable[[str], None],
                   on_args: Callable[[str], None] | None = None) -> AIMessageChunk:
        client, model = AGENT.client()
        # an HTTP client of this call's own: each turn runs in a fresh event loop, and LangChain's shared default
        # client stays bound to the loop that first used it
        http = httpx.AsyncClient(timeout=cfg.total_s)
        effort = AGENT.reasoning()
        llm = ChatOpenAI(model=model, base_url=str(client.base_url), api_key=client.api_key, temperature=0.2,
                         max_tokens=cfg.max_tokens, timeout=cfg.total_s, max_retries=0, http_async_client=http,
                         **({"reasoning_effort": effort, "extra_body": AGENT.cache_key("trip_turn")} if effort else {}))
        full, visible, shown = None, Visible(), ""

        def show(text: str) -> None:
            nonlocal shown
            if text:
                shown += text
                on_say(text)
        try:
            async with asyncio.timeout(cfg.total_s):
                async for chunk in llm.bind_tools(tools, tool_choice="auto").astream(convert_to_messages(messages)):
                    if full is None and on_args is not None:
                        on_args(None)  # the first chunk: the model has read the prompt (timing only)
                    full = chunk if full is None else full + chunk  # merges tool-call pieces by index
                    show(visible.feed(chunk.text))
                    if on_args is not None and chunk.tool_call_chunks:
                        for t in full.tool_call_chunks:
                            if t.get("name") == "record_fact":
                                on_args(t.get("args") or "")
                show(visible.end())
        except (openai.OpenAIError, TimeoutError) as e:
            raise AgentError(f"agent call failed: {type(e).__name__}: {str(e)[:200]}") from e
        finally:
            await http.aclose()
            await client.close()
        # the reasoning markers are gone from the text the loop sees; the tool-call pieces stay raw
        return AIMessageChunk(content=shown, tool_call_chunks=full.tool_call_chunks if full else [])
    return chat


def route_from_agent(state: LoopState) -> Literal["execute", "review", "__end__"]:
    """A model reply with tool calls is executed; a plain reply is reviewed; a turn that ended stops."""
    if state["ended"]:
        return END
    return "execute" if state["reply_calls"] else "review"


def route_back_to_agent(state: LoopState) -> Literal["agent", "__end__"]:
    """After tools or review: the model goes again unless the turn ended."""
    return END if state["ended"] else "agent"


def is_error(content: str) -> bool:
    """A tool result counts as failed when it is an error object, or the plain-text error ToolNode writes for an
    unknown tool."""
    try:
        return "error" in json.loads(content)
    except (ValueError, TypeError):
        return True


async def run_loop(chat: Chat, messages: list[dict], tools: TurnTools, on_say: Callable[[str], None],
                   max_steps: int, on_retry: Callable[[], None] = lambda: None) -> None:
    """Run one turn through the agent graph (agent -> execute | review).

    Same contract as the hand-rolled loop it replaces: `messages` grows in place, results stay on `tools`,
    text streams through `on_say`. A rejected fact never silently turns into an unrelated question: the agent
    must correct it or clarify the rejected field. The turn gets a single second chance
    (`nudged`): the first of claim-back, clef-back or unmapped-silence consumes it.
    The turn checkpoints to memory after every node; resuming a turn from a checkpoint is wired but the
    engine always starts fresh (see MemorySaver below).
    """

    async def agent_node(state: LoopState) -> dict:
        if state["steps"] >= max_steps:
            tools.log.append("step_cap")
            return {"ended": True}
        steps = state["steps"] + 1
        started, hs = False, state["has_say"]

        def on_call_say(delta: str) -> None:
            nonlocal started, hs
            if not delta:
                return
            if not started:
                if hs:
                    on_retry()
                    tools.forget_replies()
                started = hs = True
            on_say(delta)

        started_at = time.monotonic()
        tools.preview_reset()
        reply = await (chat(state["messages"], offered, lambda delta: None, on_args=tools.preview) if streams_args
                       else chat(state["messages"], offered, lambda delta: None))
        tools.timings.append(f"t_call {time.monotonic() - started_at:.1f}")  # where a slow turn spends its time
        text = trim_say(reply.text)
        calls = [{"id": t["id"] or f"call_{uuid.uuid4().hex[:8]}", "name": t["name"] or "",
                  "arguments": t["args"]}
                 for t in sorted(reply.tool_call_chunks, key=lambda t: t["index"] or 0)]
        for c in calls:
            try:
                args = json.loads(c["arguments"])
                if not isinstance(args, dict):
                    raise ValueError
                if c["name"] == "record_fact" and isinstance(args.get("say"), str) and args["say"].strip() and not text:
                    text = trim_say(args["say"])  # the reply written with the facts is the turn's text
            except (ValueError, TypeError):
                c["arguments"] = "{}"
                c["argument_error"] = "arguments were not valid JSON for an object; retry with a JSON object"
        on_call_say(text)
        tools.prefetch(calls, text)  # Clef starts checking now, while the tools run or the review waits
        return {"steps": steps, "has_say": hs, "reply_content": text, "reply_calls": calls,
                "messages": [{"role": "assistant", "content": text or None,
                              "tool_calls": [{"id": c["id"], "type": "function",
                                              "function": {"name": c["name"], "arguments": c["arguments"]}}
                                             for c in calls]}] if calls else []}

    async def review_node(state: LoopState) -> dict:
        """A reply with no tool call: a claim with nothing recorded, or a reply Clef sends back, gets the turn's one
        second chance; anything else ends the turn."""
        text = state["reply_content"]
        if not state["nudged"] and not tools.recorded and any(c in fold(text) for c in CLAIM):
            # the reply says it wrote something, but no record_fact ran: the streamed text is dropped and the
            # model gets one more try, told what it claimed
            tools.log.append("claim_without_record")
            on_retry()
            return {"nudged": True, "has_say": False,
                    "messages": [{"role": "assistant", "content": text}, {"role": "system", "content": RETRY_NOTE}]}
        if not state["nudged"] and (why := await asyncio.to_thread(tools.reply_problem)):
            # Clef sent the reply back (a promise, or a fact nobody gave): the model is told why and writes again
            tools.log.append(f"clef_retry {why}")
            on_retry()
            tools.forget_replies()
            return {"nudged": True, "has_say": False,
                    "messages": [{"role": "assistant", "content": text},
                                 {"role": "system", "content": REPLY_NOTE.format(why=why)}]}
        if tools.refused:
            tools.log.append(f"refusal_unresolved {sorted(tools.refused)}")
        return {"ended": True}

    offered = lc_tools(tools)
    streams_args = "on_args" in inspect.signature(chat).parameters  # a scripted chat in tests may not take it
    def refuse_call(e: Exception) -> str:
        """A call the input model refuses (an unknown key, a value outside its enum) never reaches TurnTools: the
        model reads the validation error, and the turn log records it."""
        text = str(e)
        tool = re.search(r"tool '([^']+)'", text)
        detail = text.split("with error:", 1)[-1]  # the kwargs come before it; the reason is what the bench needs
        detail = " | ".join(x.strip() for x in detail.splitlines() if x.strip() and not x.strip().startswith("Please fix"))
        tools.log.append(f"schema_refused {tool[1] if tool else type(e).__name__}: {detail}"[:300])
        return str(e)
    tool_node = ToolNode(offered, handle_tool_errors=refuse_call)

    async def execute_node(state: LoopState) -> dict:
        """Runs the reply's tool calls one at a time through ToolNode, in the model's order: a fact can depend on the
        one before it, and TurnTools is not safe to share between threads. A call whose arguments are not a JSON
        object never reaches a tool: the model gets the error for that call."""
        out: list[dict] = []
        fails = state["fails"]
        tools.settled = False
        for c in state["reply_calls"]:
            try:
                if c.get("argument_error"):
                    raise ValueError(c["argument_error"])
                args = json.loads(c["arguments"] or "{}")
                if not isinstance(args, dict):
                    raise ValueError
                done = await tool_node.ainvoke({"messages": [AIMessage(content="", tool_calls=[
                    {"id": c["id"], "name": c["name"], "args": args, "type": "tool_call"}])]})
                content = done["messages"][0].content
            except ValueError:
                content = json.dumps({"error": c.get("argument_error", "arguments are not a JSON object")})
            out.append({"role": "tool", "tool_call_id": c["id"], "content": content})
            if is_error(content):
                fails += 1
                if fails >= MAX_TOOL_FAILS:
                    tools.log.append(f"tool_fail_cap {fails}")
                    return {"messages": out, "fails": fails, "ended": True}
            if tools.asked is not None:  # a card was asked for: the engine builds it, the turn ends here
                return {"messages": out, "fails": fails, "ended": True}
            if tools.unmapped:
                if not state["nudged"] and not (state["reply_content"] or "").strip():
                    # recorded but said nothing: one more round for the consultative question, then it ends
                    tools.log.append("unmapped_without_text")
                    return {"messages": out + [{"role": "system", "content": UNMAPPED_TEXT_NOTE}],
                            "nudged": True, "fails": fails}
                return {"messages": out, "fails": fails, "ended": True}
        # a rejected fact must not silently turn into an unrelated question: the agent corrects it, clarifies
        # the rejected field
        only = state["reply_calls"][0] if len(state["reply_calls"]) == 1 else {}
        if (tools.refused and tools.refused <= WISH_FIELDS and (state["reply_content"] or "").strip()
                and only.get("name") == "record_fact"):
            # only tastes were refused and the reply is written: no second call for them. Each is kept as a wish in
            # the user's words (the summary shows it as not applied) and the next turn sees why it was refused.
            tools.keep_refused_wishes(json.loads(only["arguments"] or "{}"), out)
            tools.log.append(f"refusal_kept {sorted(tools.refused)}")
            return {"messages": out, "fails": fails, "ended": True}
        if tools.refused:
            tools.log.append(f"resolve_refusal {sorted(tools.refused)}")
        elif tools.settled and (state["reply_content"] or "").strip() and len(state["reply_calls"]) == 1:
            # the facts and the reply came in one call and every fact stood: no second call is needed
            return {"messages": out, "fails": fails, "ended": True}
        return {"messages": out, "fails": fails}

    graph = StateGraph(LoopState)
    graph.add_node("agent", agent_node)
    graph.add_node("review", review_node)
    graph.add_node("execute", execute_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_from_agent)
    graph.add_conditional_edges("review", route_back_to_agent)
    graph.add_conditional_edges("execute", route_back_to_agent)
    compiled = graph.compile(checkpointer=MemorySaver())
    # Every agent call counts one step and each execute or review follows one agent call, so the graph never needs
    # more than 2 * max_steps + 1 super-steps. The framework limit is only a backstop against a graph bug.
    final = await compiled.ainvoke({"messages": list(messages), "steps": 0, "fails": 0, "nudged": False,
                                    "has_say": False, "reply_content": "", "reply_calls": [], "ended": False},
                                   {"configurable": {"thread_id": f"trip-{uuid.uuid4().hex[:8]}"},
                                    "recursion_limit": 2 * max_steps + 4})
    messages[:] = persisted(final["messages"])


def persisted(msgs: list[dict]) -> list[dict]:
    """The history the caller keeps: a reply that was sent back, and the note that sent it back, are dropped.
    Notes are only ever appended at the tail of a turn, so the prompt prefix the model saw stays unchanged."""
    out: list[dict] = []
    for m in msgs:
        if m["role"] == "system" and (m.get("content") or "").startswith(NOTE_HEADS):
            if out and out[-1]["role"] == "assistant" and not out[-1].get("tool_calls"):
                out.pop()
            continue
        out.append(m)
    return out
