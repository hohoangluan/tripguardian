"""One conversation turn (docs/TRIP_UNDERSTANDING.md §4).

answer / edit / show are deterministic. text runs through the agent graph
(prepare -> reason with streamed say -> guard -> finalize).
"""

from datetime import date
from typing import Awaitable, Callable, Literal

from pydantic import ValidationError

from ..agent import TextFlow
from ..domain import values
from ..domain.compile import compile_search_input
from ..domain.guard import TurnPlan, drop_questions
from ..domain.heuristics import chip_echo
from ..domain.patterns import Summary, seed, votes_from_state
from ..domain.policy import next_question
from ..domain.prepass import Prepass, prepass
from ..domain.questions import READY, Question, required
from ..domain.resolve import URL, anchor_for, search
from ..domain.state import SCALARS, Evidence, Frozen, Meta, TripState, Update, apply, apply_drafts, settle, with_meta
from ..domain.understanding import view as understanding
from ..infrastructure.catalog import Catalog
from ..infrastructure.profile import ProfileStore
from ..infrastructure.sessions import Session, SessionStore
from ..infrastructure.settings import Settings

Emit = Callable[[str, dict], None]
Agent = Callable[[dict, Callable[[str], None]], Awaitable[TurnPlan]]

GREETING = "Chào bạn! Mình hỏi vài câu ngắn để hiểu chuyến Đà Lạt của bạn trước khi chọn chỗ."
FALLBACK_SAY = "Mình ghi lại được một phần; câu bạn gõ mình chưa hiểu hết, bạn có thể nói lại theo cách khác."
SAFETY_SAY = "Còn một câu để tránh xếp nhầm chỗ không hợp, bạn trả lời giúp mình nhé."
MISSING_SAY = "Mình cần biết thêm điều này trước khi tìm chỗ."
NUDGE_SAY = "Câu này bạn chọn một ý bên dưới giúp mình nhé (hoặc Bỏ qua)."
DONE_SAY = "Xong rồi, mình đi tìm chỗ hợp với chuyến này."
BAD_VALUE = "Giá trị này mình chưa đọc được, bạn thử lại nhé."
TYPED_WINS = "Mình ghi theo câu bạn gõ: {}."
# a chip draft's field -> the Trip State fields it writes; a date card is answered by a month too
WRITES = {"signal": ("signals",), "signal_handled": ("signals",), "anchor": ("anchors",),
          "anchor_priority": ("anchors",), "hard_policy": ("hard",), "start_date": ("start_date", "month")}


class TurnInput(Frozen):
    kind: Literal["text", "answer", "edit", "show"]
    text: str = ""
    qid: str = ""
    chips: tuple[str, ...] = ()
    value: str | None = None
    target: str = ""


def gained(before: TripState, after: TripState) -> bool:
    """Did a turn change what the Trip State knows? Counters and the question log do not count."""
    def core(st: TripState) -> TripState:
        return st.model_copy(update={"meta": Meta(pending=st.meta.pending)})
    return core(before) != core(after)


def touched(q: Question, before: TripState, after: TripState) -> bool:
    """Did a turn write one of the fields this card asks about? An agent-written card has no drafts: any gain counts."""
    if q.custom or not (q.chips or q.input_field):  # an open card is answered by anything the turn added
        return gained(before, after)
    fields = {x.field for c in q.chips for x in c.drafts} | ({q.input_field} if q.input_field else set())
    attrs = {a for f in fields for a in WRITES.get(f, (f,)) if a in TripState.model_fields}
    return any(getattr(before, a) != getattr(after, a) for a in attrs)


def mark(st: TripState, q: Question) -> TripState:
    """The card counts as asked: logged once, and an adaptive card spends one question of the budget."""
    asked = st.meta.asked + (() if q.qid in st.meta.asked else (q.qid,))
    return with_meta(st, asked=asked, adaptive_turns=st.meta.adaptive_turns + int(q.tier >= 2), held=None)


def card(q: Question | None) -> dict | None:
    if q is None:
        return None
    d = q.model_dump(mode="json", exclude={"exit_drafts"})
    d["chips"] = [{"id": c.id, "label": c.label, "row": c.row} for c in q.chips]
    return d


class Engine:
    def __init__(self, catalog: Catalog, cfg: Settings, store: SessionStore, agent: Agent,
                 today: Callable[[], date] = date.today, profiles: ProfileStore | None = None):
        """profiles: stored patterns (config patterns.enabled); None = no long-term learning."""
        self.catalog, self.cfg, self.store, self.agent, self.today = catalog, cfg, store, agent, today
        self.profiles = profiles
        self._text_flow = TextFlow(self)

    # ---------- reads ----------

    def create(self, experience: str | None = None, start_with: str | None = None, user_id: str | None = None,
               remember: bool = False) -> dict:
        """user_id: whose stored patterns seed the session. remember: the user agreed this session may add to them."""
        on = self.profiles is not None and user_id is not None
        state = TripState(meta=Meta(experience=experience, start_with=start_with, user_id=user_id if on else None,
                                    remember=remember and on))
        if on:
            state = seed(state, self.profiles.patterns(user_id, self.today()), self.catalog, self.cfg.patterns)
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

    def forget(self, user_id: str) -> bool:
        """Delete everything stored about a user. False when nothing was stored (or learning is off)."""
        return self.profiles.forget(user_id) if self.profiles else False

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

    def refine(self, sid: str, text: str, emit: Emit) -> None:
        """A wish typed later, at Chọn nơi: read it like any text turn, then compile again. The Understand screen's
        card is left as it was; only say / state / done leave this method."""
        s = self.store.get(sid)
        said = ""

        def quiet(ev: str, d: dict) -> None:
            nonlocal said
            if ev == "card":
                return
            if ev == "say":
                said = d["replace"] if "replace" in d else said + d.get("delta", "")
            emit(ev, d)

        with s.lock:
            try:
                card_before = s.card
                self._text_flow.invoke(s, TurnInput(kind="text", text=text), quiet, None)
                s.card = card_before
                plain = drop_questions(said)  # no card follows here, so a question would go unanswered
                if plain != said:
                    emit("say", {"replace": plain})
                    for t in reversed(s.transcript):
                        if t["role"] == "agent":
                            t["text"] = plain
                            break
                if required(s.state, self.catalog, self.cfg) is None:
                    si = compile_search_input(s.state)
                    emit("done", {"search_input": si.model_dump(mode="json")})
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
        if not (exit_ or chosen or inp.value) and inp.text.strip():  # only the "other answer" box: a text turn
            return self._text(s, TurnInput(kind="text", text=inp.text), emit)
        if q.custom and not exit_:
            text = ", ".join([c.label for c in chosen] + ([inp.text.strip()] if inp.text.strip() else []))
            return self._text(s, TurnInput(kind="text", text=text), emit)
        turn = s.state.meta.turn + 1
        st = s.state
        # text sent with the chips is the more specific answer: a value it states replaces the chip's for that field
        typed = {p.field: p.value for p in prepass(inp.text, self.today()).proposals
                 if p.field in SCALARS and p.op == "set" and not p.inferred} if inp.text.strip() else {}
        chip_set = {x.field: x.value for c in chosen for x in c.drafts if x.field in SCALARS and x.op == "set"}
        try:
            if exit_:
                st = apply_drafts(st, q.exit_drafts, turn, tool=f"chip:{q.qid}:{exit_}")
                st = with_meta(st, skipped=st.meta.skipped | {q.qid}, unsure_streak=st.meta.unsure_streak + 1)
            else:
                for c in chosen:
                    drafts = tuple(x for x in c.drafts if not (x.field in typed and x.value != typed[x.field]))
                    st = apply_drafts(st, drafts, turn, tool=f"chip:{q.qid}:{c.id}", quote=c.label)
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
        st = settle(st)
        idle = (0 if gained(s.state, st) else st.meta.idle_streak + 1) if q.tier >= 2 else st.meta.idle_streak
        st = with_meta(st, turn=turn, asked=st.meta.asked + (q.qid,), idle_streak=idle,
                       adaptive_turns=st.meta.adaptive_turns + int(q.tier >= 2), held=None)
        s.state, s.card = st, None
        if inp.text.strip():
            return self._text(s, TurnInput(kind="text", text=inp.text), emit, chip_set)
        self._advance(s, emit)

    def _text(self, s: Session, inp: TurnInput, emit: Emit, chips: dict | None = None) -> None:
        """chips: scalar values chips set earlier in this same turn; a typed value that replaced one is said aloud."""
        text = inp.text.strip()
        if not text:
            emit("card", card(s.card))
            return
        if not chips and (chip := chip_echo(text, s.card)):  # typed a chip's label: the same as tapping it
            qid = s.card.qid
            self._answer(s, TurnInput(kind="answer", qid=qid, chips=(chip,)), emit)
            s.transcript.append({"role": "system", "text": f"heuristic:chip_echo {qid}:{chip}", "turn": s.state.meta.turn})
            return
        self._text_flow.invoke(s, inp, emit, chips)

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
        stale = s.card is not None and (s.card.qid == "prior" or (s.card.tier == 1 and req is None))
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
        self._remember(s)
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

    def _idle(self, before: TripState, st: TripState, prev: Question | None, q: Question | None, say: str):
        """An adaptive question that added nothing counts as idle; idle_limit of them in a row end the questioning.
        There is no cap on turns that keep adding something."""
        if prev is None or prev.tier < 2:
            return st, q, say
        st = with_meta(st, idle_streak=0 if gained(before, st) else st.meta.idle_streak + 1)
        if st.meta.idle_streak >= self.cfg.idle_limit and q is not None and q.tier >= 2:
            return st, READY, drop_questions(say)
        return st, q, say

    def _remember(self, s: Session) -> None:
        """The user is done with this session: add its explicit choices to their stored history, if they agreed."""
        m = s.state.meta
        if not (self.profiles and m.remember and m.user_id):
            return
        votes = votes_from_state(s.state)
        if not votes:
            return
        try:
            self.profiles.record(m.user_id, Summary(sid=s.id, day=self.today(), votes=votes))
        except OSError as e:
            s.transcript.append({"role": "system", "text": f"profile not saved: {e}", "turn": m.turn})

    def _close_card(self, s: Session) -> None:
        if s.card:
            s.transcript.append({"role": "agent", "text": s.card.text, "turn": s.state.meta.turn, "kind": "card"})

    def _advance(self, s: Session, emit: Emit, question: Question | None = None) -> None:
        s.card = question or next_question(s.state, self.catalog, self.cfg)
        emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
        emit("card", card(s.card))
