"""Trip LLM agent: a tool-calling loop over the Trip State (docs/P2_TRIP_UNDERSTANDING.md §4)."""

from agents import AgentError

from .client import openai_chat, strip_thought
from .loop import Assistant, Call, Chat, run_loop
from .prompts import build_messages, summarize, system_prompt
from .tools import SPECS, STOPPING, ToolExecutor, TurnTools

__all__ = ["AgentError", "Assistant", "Call", "Chat", "SPECS", "STOPPING", "ToolExecutor", "TurnTools",
           "build_messages", "openai_chat", "run_loop", "strip_thought", "summarize", "system_prompt"]
