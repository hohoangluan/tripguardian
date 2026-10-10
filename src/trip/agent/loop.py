"""The Trip agent loop, as a LangGraph StateGraph: the model calls tools until it asks the user, finishes, or runs out of steps."""

import json
from dataclasses import dataclass, field
from typing import Awaitable, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

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


class LoopState(TypedDict):
    """One turn's loop. `messages` stays the caller's own list: the engine reads the tool-call transcript from it."""

    chat: Chat
    messages: list[dict]
    tools: TurnTools
    on_say: Callable[[str], None]
    max_steps: int
    steps: int
    reply: Assistant | None


def _wire(call: Call) -> dict:
    return {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.arguments or "{}"}}


async def model_step(state: LoopState) -> dict:
    """One model call and Clef's checks on what it just said, sent together. A plain answer ends the loop: the engine
    then opens a free-text card, or the question the text ends on becomes one."""
    reply = await state["chat"](state["messages"], state["tools"].specs(), state["on_say"])
    state["tools"].prefetch(reply.calls, reply.content)  # Clef's checks on this reply, all sent at once
    if not reply.calls:  # a plain answer: nothing to wait on, the engine opens a free-text card
        return {"steps": state["steps"] + 1, "reply": reply}
    state["messages"].append({"role": "assistant", "content": reply.content or None,
                              "tool_calls": [_wire(c) for c in reply.calls]})
    return {"steps": state["steps"] + 1, "reply": reply}


def tool_step(state: LoopState) -> dict:
    """Each tool call of this reply, in order, its result written back for the next model call. Sequential on purpose:
    a stopping tool ends the turn, so the calls after it in the same reply must never run."""
    tools = state["tools"]
    for call in state["reply"].calls:
        try:
            args = json.loads(call.arguments or "{}")
            if not isinstance(args, dict):
                raise ValueError
            result = tools.run(call.name, args)
        except ValueError:
            result = {"error": "arguments are not a JSON object"}
        state["messages"].append({"role": "tool", "tool_call_id": call.id,
                                  "content": json.dumps(result, ensure_ascii=False)})
        if tools.stopped:
            break
    return {}


def budget_step(state: LoopState) -> dict:
    """The iteration guard: the steps this turn has spent are counted here, not by the model."""
    if state["steps"] >= state["max_steps"]:
        state["tools"].log.append("step_cap")
    return {}


def _route_budget(state: LoopState) -> str:
    return END if state["steps"] >= state["max_steps"] else "model_step"


def _route_model(state: LoopState) -> str:
    return "tool_step" if state["reply"] and state["reply"].calls else END


def _route_tools(state: LoopState) -> str:
    # a stopping tool opens a question the user must answer; an unmapped wish gets the engine's fixed reply
    return "budget_step" if not (state["tools"].stopped or state["tools"].unmapped) else END


def _build() -> StateGraph:
    graph = StateGraph(LoopState)
    graph.add_node("budget_step", budget_step)
    graph.add_node("model_step", model_step)
    graph.add_node("tool_step", tool_step)
    graph.add_edge(START, "budget_step")
    graph.add_conditional_edges("budget_step", _route_budget)
    graph.add_conditional_edges("model_step", _route_model)
    graph.add_conditional_edges("tool_step", _route_tools)
    return graph.compile(name="trip-agent-loop")


# Built once: the graph is stateless, every turn passes its own LoopState to ainvoke.
_LOOP = _build()


async def run_loop(chat: Chat, messages: list[dict], tools: TurnTools, on_say: Callable[[str], None],
                   max_steps: int) -> None:
    """Runs until a stopping tool succeeds, a wish ends up unmapped, the model answers in plain text, or max_steps calls are spent.
    The result is in `tools` (state, card, outcome, log). An AgentError keeps whatever facts were already written."""
    await _LOOP.ainvoke({"chat": chat, "messages": messages, "tools": tools, "on_say": on_say,
                         "max_steps": max_steps, "steps": 0, "reply": None},
                        {"recursion_limit": 3 * max_steps + 10})
