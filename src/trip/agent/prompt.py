"""Prompt construction for the Trip agent: static instruction plus append-only history."""

import functools
import json
import re
from datetime import date

from langchain_core.messages import AIMessage, ChatMessage, HumanMessage, SystemMessage

from corpus.llm import TRIP_TURN

from ..domain.prepass import Prepass
from ..domain.questions import Question
from ..domain.state import SCALARS, Base, TripState, ontology
from ..infrastructure.settings import Settings


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
                  ranked: list[tuple[Question, float]], cfg: Settings, last_question: str | None, today: date,
                  transcript: list[dict] | None = None, compared=()) -> dict:
    hits = [{"field": p.field, "value": _plain(p.value), "quote": p.quote} for p in pre.proposals]
    hits += [{"ambiguous": q, "may_mean": list(k)} for q, k in pre.ambiguous]
    history = [HumanMessage(t["text"]) if t["role"] == "user" else AIMessage(t["text"])
               for t in (transcript or []) if t["role"] in ("user", "agent")]
    context = {
        "state": json.loads(summarize(state)),
        "last_question": last_question or "none",
        "experience": state.meta.experience or "unknown",
        "prepass": hits,
        "required": f"{required.qid}: {required.text}" if required else "none",
        "candidates": [{"qid": q.qid, "text": q.text} for q, _ in ranked[:5]],
        "budget": max(0, cfg.turn_budget - state.meta.adaptive_turns),
        "idle_left": max(0, cfg.idle_limit - state.meta.idle_streak),
        "today": today.isoformat(),
        "compared_places": list(compared),
    }
    return {
        "messages": [
            SystemMessage(TRIP_TURN.render(features=_features(), today=today.isoformat())),
            *history,
            ChatMessage(role="developer", content="CURRENT CONTEXT\n" + json.dumps(context, ensure_ascii=False)),
            HumanMessage(text),
        ],
    }
