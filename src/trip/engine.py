"""One conversation turn (docs/plans/TRIP_UNDERSTANDING_SPEC.md §5).

answer / edit / show are deterministic. text runs prepass -> agent (streamed) -> guard; any agent failure is answered
by the policy with the same state.
"""

import asyncio
from datetime import date
from typing import Awaitable, Callable, Literal

from pydantic import ValidationError

from . import values
from .agent import AgentError, prompt_fields
from .catalog import Catalog
from .compile import compile_search_input
from .guard import TurnPlan, guard
from .policy import next_question
from .prepass import Prepass, prepass
from .questions import Question, rank_questions, required
from .resolve import URL, anchor_for, search
from .sessions import Session, SessionStore
from .settings import Settings
from .state import SCALARS, Evidence, Frozen, Meta, TripState, Update, apply, apply_drafts, settle, with_meta
from .understanding import view as understanding

Emit = Callable[[str, dict], None]
Agent = Callable[[dict, Callable[[str], None]], Awaitable[TurnPlan]]

GREETING = "Chào bạn! Mình hỏi vài câu ngắn để hiểu chuyến Đà Lạt của bạn trước khi chọn chỗ."
FALLBACK_SAY = "Mình ghi lại được một phần; câu bạn gõ mình chưa hiểu hết, bạn có thể nói lại theo cách khác."
SAFETY_SAY = "Còn một câu để tránh xếp nhầm chỗ không hợp, bạn trả lời giúp mình nhé."
MISSING_SAY = "Mình cần biết thêm điều này trước khi tìm chỗ."
NUDGE_SAY = "Câu này bạn chọn một ý bên dưới giúp mình nhé (hoặc Bỏ qua)."
DONE_SAY = "Xong rồi, mình đi tìm chỗ hợp với chuyến này."
BAD_VALUE = "Giá trị này mình chưa đọc được, bạn thử lại nhé."


class TurnInput(Frozen):
    kind: Literal["text", "answer", "edit", "show"]
    text: str = ""
    qid: str = ""
    chips: tuple[str, ...] = ()
    value: str | None = None
    target: str = ""


def card(q: Question | None) -> dict | None:
    if q is None:
        return None
    d = q.model_dump(mode="json", exclude={"exit_drafts"})
    d["chips"] = [{"id": c.id, "label": c.label, "row": c.row} for c in q.chips]
    return d


class Engine:
    def __init__(self, catalog: Catalog, cfg: Settings, store: SessionStore, agent: Agent,
                 today: Callable[[], date] = date.today):
        self.catalog, self.cfg, self.store, self.agent, self.today = catalog, cfg, store, agent, today

    # ---------- reads ----------

    def create(self, experience: str | None = None, start_with: str | None = None) -> dict:
        state = TripState(meta=Meta(experience=experience, start_with=start_with))
        s = self.store.new(state)
        s.card = next_question(state, self.catalog, self.cfg)
        s.transcript.append({"role": "agent", "text": GREETING, "turn": 0})
        self.store.save(s)
        return self.view(s)

    def load(self, sid: str) -> dict:
        return self.view(self.store.get(sid))

    def view(self, s: Session) -> dict:
        return {"id": s.id,
                "transcript": [{k: t[k] for k in ("role", "text", "turn")} for t in s.transcript
                               if t["role"] in ("user", "agent")],
                "understanding": understanding(s.state, self.catalog, self.cfg),
                "card": card(s.card)}

    def places(self, q: str) -> list[dict]:
        return [{"id": p.id, "name": p.name, "category": p.category} for p in search(q, self.catalog)]

    # ---------- turns ----------

    def turn(self, sid: str, inp: TurnInput, emit: Emit) -> None:
        s = self.store.get(sid)
        gone = False

        def safe(event: str, data: dict) -> None:
            # a closed browser tab must not leave the turn half applied: finish it, stop writing
            nonlocal gone
            if gone:
                return
            try:
                emit(event, data)
            except OSError:
                gone = True

        with s.lock:
            try:
                getattr(self, f"_{inp.kind}")(s, inp, safe)
            finally:
                self.store.save(s)

    def _answer(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        q = s.card
        if q is None or q.qid != inp.qid:
            emit("error", {"message": "Câu này đã qua, bạn trả lời câu mới nhất nhé."})
            emit("card", card(s.card))
            return
        if "show" in inp.chips:
            return self._show(s, inp, emit)
        exit_ = next((x for x in ("skip", "unsure") if x in inp.chips), None)
        chosen = [c for c in q.chips if c.id in inp.chips]
        if q.custom and not exit_:
            text = ", ".join([c.label for c in chosen] + ([inp.text.strip()] if inp.text.strip() else []))
            return self._text(s, TurnInput(kind="text", text=text), emit)
        turn = s.state.meta.turn + 1
        st = s.state
        try:
            if exit_:
                st = apply_drafts(st, q.exit_drafts, turn, tool=f"chip:{q.qid}:{exit_}")
                st = with_meta(st, skipped=st.meta.skipped | {q.qid}, unsure_streak=st.meta.unsure_streak + 1)
            else:
                for c in chosen:
                    st = apply_drafts(st, c.drafts, turn, tool=f"chip:{q.qid}:{c.id}", quote=c.label)
                if inp.value and q.input_field:
                    st = apply(st, Update(field=q.input_field, value=values.parse(q.input_field, inp.value, self.catalog),
                                          source="user", confidence="high",
                                          evidence=Evidence(turn=turn, tool=f"input:{q.qid}")))
                st = with_meta(st, unsure_streak=0)
        except (ValueError, ValidationError):
            emit("error", {"message": BAD_VALUE})
            return
        label = {"skip": "Bỏ qua", "unsure": "Không chắc"}.get(exit_ or "") or \
            ", ".join(c.label for c in chosen) or (inp.value or "")
        self._close_card(s)
        s.transcript.append({"role": "user", "text": label or "…", "turn": turn, "kind": "answer", "qid": q.qid})
        st = with_meta(st, turn=turn, asked=st.meta.asked + (q.qid,),
                       adaptive_turns=st.meta.adaptive_turns + int(q.tier >= 2))
        s.state, s.card = settle(st), None
        if inp.text.strip():
            return self._text(s, TurnInput(kind="text", text=inp.text), emit)
        self._advance(s, emit)

    def _text(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        text = inp.text.strip()
        if not text:
            emit("card", card(s.card))
            return
        st, prev = s.state, s.card
        turn = st.meta.turn + 1
        self._close_card(s)
        s.transcript.append({"role": "user", "text": text, "turn": turn, "kind": "text"})
        pre = prepass(text, self.today())
        emit("preview", {"fields": [{"target": p.field, "value": values.jsonable(p.value), "quote": p.quote}
                                    for p in pre.proposals]})
        answered = (prev.qid,) if prev and prev.qid not in st.meta.asked else ()
        st = with_meta(st, turn=turn, asked=st.meta.asked + answered, unsure_streak=0,
                       adaptive_turns=st.meta.adaptive_turns + int(bool(prev) and prev.tier >= 2))
        st = self._deterministic(st, text, pre, turn)
        req = required(st, self.catalog, self.cfg)
        ranked = rank_questions(st, self.catalog, self.cfg)[:5]
        fields = prompt_fields(st, text, pre, req, ranked, self.cfg, prev.text if prev else None, self.today())
        streamed: list[str] = []

        def on_say(delta: str) -> None:
            streamed.append(delta)
            emit("say", {"delta": delta})

        heard = " ".join(t["text"] for t in s.transcript if t["role"] == "user")
        try:
            g = guard(asyncio.run(self.agent(fields, on_say)), st, text, turn, self.catalog, self.cfg, heard)
            st, q, say, log = g.state, g.question, g.say, g.log
        except AgentError as e:
            st, say, log = settle(st), FALLBACK_SAY, [f"agent_fallback: {e}"]
            q = next_question(st, self.catalog, self.cfg)
        if prev and prev.tier == 1 and prev.qid != "frame" and q.qid == prev.qid:
            say = f"{say} {NUDGE_SAY}".strip()  # typed past a card only a chip can answer
        if say != "".join(streamed):
            emit("say", {"replace": say})
        if say:
            s.transcript.append({"role": "agent", "text": say, "turn": turn, "kind": "say"})
        if log:
            s.transcript.append({"role": "system", "text": "; ".join(log), "turn": turn})
        s.state = st
        self._advance(s, emit, q)

    def _edit(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        ev = Evidence(turn=s.state.meta.turn, tool="edit")

        def user(field, value=None, op="set"):
            return Update(field=field, op=op, value=value, source="user", confidence="high", evidence=ev)

        kind, _, arg = inp.target.partition(":")
        v = inp.value
        try:
            if kind in SCALARS:
                u = user(kind, op="remove") if v is None else user(kind, values.parse(kind, v, self.catalog))
            elif kind == "companions":
                u = user(kind, [x for x in (v or "").split(",") if x])
            elif kind == "soft":
                u = user("soft", arg, "remove") if v is None else user("soft", (arg, v))
            elif kind == "hard":
                u = user("hard", arg, "remove") if v is None else user("hard_policy", (arg, v))
            elif kind in ("anchor", "unmapped"):
                u = user(kind, int(arg), "remove")
            elif kind == "signal":
                u = user("signal", arg, "remove")
            else:
                raise ValueError(f"unknown target {inp.target!r}")
            s.state = settle(apply(s.state, u))
        except (ValueError, ValidationError, IndexError):
            emit("error", {"message": BAD_VALUE})
            return
        emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
        req = required(s.state, self.catalog, self.cfg)
        stale = s.card is not None and s.card.tier == 1 and req is None
        if stale or (req and (s.card is None or s.card.qid != req.qid)):
            s.card = req or next_question(s.state, self.catalog, self.cfg)
            emit("card", card(s.card))

    def _show(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        req = required(s.state, self.catalog, self.cfg)
        if req:
            s.card = req
            emit("say", {"replace": SAFETY_SAY if req.group == "C" else MISSING_SAY})
            emit("card", card(req))
            return
        si = compile_search_input(s.state)
        self._close_card(s)
        s.card = None
        s.transcript.append({"role": "agent", "text": DONE_SAY, "turn": s.state.meta.turn, "kind": "done"})
        emit("done", {"search_input": si.model_dump(mode="json")})

    # ---------- helpers ----------

    def _deterministic(self, st: TripState, text: str, pre: Prepass, turn: int) -> TripState:
        """Links, pasted place lists, keyword matches: written before the agent so nothing depends on it."""
        lines = [x.strip() for x in text.splitlines() if x.strip()]
        names = [x for x in lines if not URL.match(x)] if len(lines) >= 2 else []
        for raw in URL.findall(text) + names:
            a = anchor_for(raw, self.catalog)
            if a.state == "missing" and not URL.match(raw):
                continue
            st = apply(st, Update(field="anchor", op="add", value=a, source="user", confidence="high",
                                  evidence=Evidence(turn=turn, quote=raw)))
        for p in pre.proposals:
            try:
                # keyword guesses: shown with ✎ until the user or the agent confirms them
                st = apply(st, Update(field=p.field, op=p.op, value=p.value, source="inferred",
                                      confidence="low" if p.inferred else "medium",
                                      evidence=Evidence(turn=turn, quote=p.quote)))
            except (ValueError, ValidationError):
                pass
        for quote, keys in pre.ambiguous:
            good = [k for k in keys if self.catalog.count(k) >= self.cfg.top_k]
            ev = Evidence(turn=turn, quote=quote)
            if len(good) >= 2:
                u = Update(field="pending", op="add", value={"phrase": quote, "keys": good}, source="user",
                           confidence="medium", evidence=ev)
            elif good:
                u = Update(field="soft", op="add", value=(good[0], "love"), source="inferred", confidence="medium",
                           evidence=ev)
            else:
                u = Update(field="unmapped", op="add", value=quote, source="user", confidence="medium", evidence=ev)
            st = apply(st, u)
        return settle(st)

    def _close_card(self, s: Session) -> None:
        if s.card:
            s.transcript.append({"role": "agent", "text": s.card.text, "turn": s.state.meta.turn, "kind": "card"})

    def _advance(self, s: Session, emit: Emit, question: Question | None = None) -> None:
        s.card = question or next_question(s.state, self.catalog, self.cfg)
        emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
        emit("card", card(s.card))
