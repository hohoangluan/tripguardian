"""Graph nodes for a free-text turn. Session lock and persistence stay in Engine.turn()."""

import asyncio
from typing import TYPE_CHECKING

from agents import AgentError

from ..domain import values
from ..domain.guard import drop_questions, guard
from ..domain.heuristics import simple_frame
from ..domain.policy import next_question
from ..domain.prepass import prepass
from ..domain.questions import rank_questions, required
from ..domain.state import settle, with_meta
from ..domain.traits import compared_places
from .prompt import prompt_fields
from .tools import ToolExecutor

if TYPE_CHECKING:
    from ..api.engine import Engine
    from .state import TextTurn


def prepare_text(engine: "Engine", data: "TextTurn") -> dict:
    from ..api.engine import mark, touched

    s, inp = data["session"], data["inp"]
    text = inp.text.strip()
    st, prev = s.state, s.card
    before = st
    turn = st.meta.turn + 1
    engine._close_card(s)
    s.transcript.append({"role": "user", "text": text, "turn": turn, "kind": "text"})
    pre = prepass(text, engine.today())
    data["emit"]("preview", {"fields": [{"target": p.field, "value": values.jsonable(p.value), "quote": p.quote}
                                        for p in pre.proposals]})
    st = with_meta(st, turn=turn, unsure_streak=0)
    hold = prev if prev and prev.qid not in st.meta.asked and st.meta.held != prev.qid else None
    if prev and not hold:
        st = mark(st, prev)
    st = engine._deterministic(st, text, pre, turn)
    simple = simple_frame(text, pre)
    if hold and touched(hold, before, st):
        st, hold = mark(st, hold), None
    req = required(st, engine.catalog, engine.cfg)
    ranked = rank_questions(st, engine.catalog, engine.cfg)[:5]
    heard = " ".join(t["text"] for t in s.transcript if t["role"] == "user")
    compared = [] if simple else compared_places(text, engine.catalog)
    fields = {} if simple else prompt_fields(st, text, pre, req, ranked, engine.cfg,
                                             prev.text if prev else None, engine.today(), s.transcript[:-1],
                                             compared=compared)
    if fields:
        fields["_tool_executor"] = ToolExecutor(engine.catalog, engine.today())
    return {"text": text, "turn": turn, "before": before, "previous": prev, "state": st, "held": hold,
            "pre": pre, "simple": simple, "req": req, "ranked": ranked, "heard": heard,
            "fields": fields, "streamed": [], "compared": compared}


def reason_text(engine: "Engine", data: "TextTurn") -> dict:
    from ..api.engine import FALLBACK_SAY

    st = data["state"]
    if data.get("simple"):
        st = settle(st)
        q = next_question(st, engine.catalog, engine.cfg)
        return {"state": st, "question": q, "say": "Mình đã ghi nhận thông tin chuyến đi.",
                "log": ["heuristic:frame"]}
    streamed: list[str] = data.get("streamed") or []
    emit = data["emit"]

    def on_say(delta: str) -> None:
        streamed.append(delta)
        emit("say", {"delta": delta})

    try:
        plan = asyncio.run(engine.agent(data["fields"], on_say))
    except AgentError as exc:
        st = settle(st)
        q = next_question(st, engine.catalog, engine.cfg)
        return {"state": st, "question": q, "say": FALLBACK_SAY,
                "log": [f"agent_fallback: {exc}"], "streamed": streamed}
    g = guard(plan, st, data["text"], data["turn"], engine.catalog, engine.cfg, data["heard"],
              compared=data.get("compared"))
    return {"state": g.state, "question": g.question, "say": g.say,
            "log": [*g.log, *data["fields"].get("_tool_log", [])], "streamed": streamed}


def finalize_text(engine: "Engine", data: "TextTurn") -> dict:
    from ..api.engine import NUDGE_SAY, TYPED_WINS, mark, touched

    s = data["session"]
    emit, chips = data["emit"], data.get("chips")
    st, before, prev = data["state"], data["before"], data["previous"]
    hold, q, say, log = data.get("held"), data["question"], data.get("say") or "", data.get("log") or []
    turn = data["turn"]
    if hold and touched(hold, before, st):
        st, hold = mark(st, hold), None
        if q and prev and q.qid == prev.qid:
            q, say = next_question(st, engine.catalog, engine.cfg), drop_questions(say)
    elif hold:
        st = with_meta(st, held=hold.qid)
    st, q, say = engine._idle(before, st, prev, q, say)
    typed = [f"“{f.evidence[-1].quote}”" for k, v in (chips or {}).items()
             if (f := getattr(st, k)).value != v and f.evidence and f.evidence[-1].quote]
    if typed:
        say = f"{say} {TYPED_WINS.format(', '.join(typed))}".strip()
    if prev and prev.tier == 1 and prev.qid != "frame" and q and q.qid == prev.qid:
        say = f"{say} {NUDGE_SAY}".strip()
    streamed = data.get("streamed") or []
    if say != "".join(streamed):
        emit("say", {"replace": say})
    if say:
        s.transcript.append({"role": "agent", "text": say, "turn": turn, "kind": "say"})
    if log:
        s.transcript.append({"role": "system", "text": "; ".join(log), "turn": turn})
    s.state = st
    engine._advance(s, emit, q)
    return {}
