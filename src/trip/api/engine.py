"""One conversation turn (docs/TRIP_UNDERSTANDING.md §4).

edit / show are deterministic. Typing, and answering a card, run the agent loop (agent/loop.py): the agent records
facts, then asks a card, finishes, or just replies.
"""

import asyncio
from datetime import date
from typing import Callable, Literal

from pydantic import ValidationError, model_validator

from ..agent import AgentError, Chat, TurnTools, build_messages, run_loop
from ..domain import values
from ..domain.card import OPENING, Question, conversation_card
from ..domain.compile import UnhandledSignal, compile_search_input
from ..domain.guard import bad_say, drop_questions
from ..domain.patterns import Summary, seed, seed_profile, votes_from_state
from ..domain.prepass import Prepass, prepass
from ..domain.readiness import missing
from ..domain.resolve import URL, anchor_for, search
from ..domain.state import SCALARS, Evidence, Frozen, Meta, TripState, Update, apply, settle, with_meta
from ..domain.traits import compared_places
from ..domain.understanding import chip_effects, view as understanding
from ..infrastructure.catalog import Catalog
from ..infrastructure.clef import ClefRoute
from ..infrastructure.profile import ProfileStore
from ..infrastructure.sessions import Session, SessionStore
from ..infrastructure.settings import Settings

Emit = Callable[[str, dict], None]
Route = Callable[[str, str | None, tuple], ClefRoute]  # (message, open card's text, still-needed (key, label) pairs)

GREETING = "Chào bạn! Mình hỏi vài câu ngắn để hiểu chuyến Đà Lạt của bạn trước khi chọn chỗ."
FALLBACK_SAY = "Mình ghi lại được một phần; câu bạn gõ mình chưa hiểu hết, bạn có thể nói lại theo cách khác."
MISSING_SAY = "Mình cần biết thêm {items} trước khi tìm chỗ, bạn kể giúp mình nhé."
REJECT_SAY = "Mình chưa hỗ trợ nội dung này. Bạn vui lòng nhập câu hỏi khác về chuyến đi nhé."
NODATA_SAY = ("Mình chưa có số liệu thực tế về điều này ở bước này; thông tin thật sẽ hiện ở bước Lựa chọn. "
              "Bạn cứ kể tiếp về chuyến đi nhé.")
UNSURE_SAY = "Mình chưa chắc chắn về thông tin này nên chưa trả lời được ở bước này. Bạn cứ kể tiếp về chuyến đi nhé."
UNMAPPED_SAY = ("Mình đã ghi lại {wish}, nhưng hiện chưa dùng được điều này để lọc địa điểm. "
                "Bạn kể thêm về chuyến đi nhé.")
DONE_SAY = "Xong rồi, mình đi tìm chỗ hợp với chuyến này."
BAD_VALUE = "Giá trị này mình chưa đọc được, bạn thử lại nhé."
EXIT_TEXT = {"skip": "Bỏ qua câu này.", "unsure": "Mình chưa chắc."}


class TurnInput(Frozen):
    kind: Literal["text", "answer", "edit", "show"]
    text: str = ""
    qid: str = ""
    chips: tuple[str, ...] = ()
    value: str | None = None
    target: str = ""

    @model_validator(mode="after")
    def _one_answer(self):
        # typing is the card's "other answer" option: an answer is chips / a value, or text, never both
        if self.kind == "answer" and self.text.strip() and (self.chips or self.value):
            raise ValueError("an answer is chips or text, not both")
        return self


def card(q: Question | None, effects: dict[str, int] | None = None) -> dict | None:
    """effects: chip id -> places the "Đang hợp với bạn" count gains or loses if that chip is chosen."""
    if q is None:
        return None
    d = q.model_dump(mode="json", exclude={"exit_drafts"})
    d["chips"] = [{"id": c.id, "label": c.label, "row": c.row, "effect": (effects or {}).get(c.id)} for c in q.chips]
    return d


class Engine:
    def __init__(self, catalog: Catalog, cfg: Settings, store: SessionStore, chat: Chat,
                 today: Callable[[], date] = date.today, profiles: ProfileStore | None = None,
                 route: Route | None = None, judge=None):
        """chat: one model call with tools (agent/loop.py). profiles: stored patterns (config patterns.enabled);
        None = no long-term learning. route: Clef, asked before the Agent on a typed turn; None = never short-circuits.
        judge: Clef's yes / no checks on facts, replies and questions (infrastructure.clef.Judge); None = regex guards only."""
        self.catalog, self.cfg, self.store, self.chat, self.today = catalog, cfg, store, chat, today
        self.profiles, self.route, self.judge = profiles, route, judge

    # ---------- reads ----------

    def create(self, experience: str | None = None, start_with: str | None = None, user_id: str | None = None,
               remember: bool = False, profile: dict | None = None) -> dict:
        """user_id: whose stored patterns seed the session. remember: the user agreed this session may add to them.
        profile: the account's usual mobility / companions, seeded as priors (patterns.seed_profile)."""
        on = self.profiles is not None and user_id is not None
        state = TripState(meta=Meta(experience=experience, start_with=start_with, user_id=user_id if on else None,
                                    remember=remember and on))
        if on:
            state = seed(state, self.profiles.patterns(user_id, self.today()), self.catalog, self.cfg.patterns)
        if profile:
            state = seed_profile(state, profile)
        s = self.store.new(state)
        s.card = OPENING
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
                "card": self._card(s.state, s.card)}

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
        """A wish typed later, at Chọn nơi: read it like any text turn, without questions, then compile again. The
        Understand screen's card is left as it was; only say / state / done leave this method."""
        s = self.store.get(sid)
        with s.lock:
            try:
                card_before = s.card
                self._run(s, text, emit, may_ask=False, quiet=True)
                s.card = card_before
                try:
                    emit("done", {"search_input": compile_search_input(s.state).model_dump(mode="json")})
                except UnhandledSignal:  # an open health hint: the user answers it on the Understand screen
                    pass
            finally:
                self.store.save(s)

    def _answer(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        q = s.card
        if q is None or q.qid != inp.qid:
            emit("error", {"message": "Câu này đã qua, bạn trả lời câu mới nhất nhé."})
            emit("card", self._card(s.state, s.card))
            return
        if "show" in inp.chips:
            return self._show(s, inp, emit)
        exit_ = next((x for x in ("skip", "unsure") if x in inp.chips), None)
        chosen = [c.label for c in q.chips if c.id in inp.chips]
        text = inp.text.strip() or (EXIT_TEXT[exit_] if exit_ else ", ".join(chosen) or (inp.value or ""))
        self._text(s, TurnInput(kind="text", text=text), emit)

    def _text(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        text = inp.text.strip()
        if not text:
            emit("card", self._card(s.state, s.card))
            return
        self._run(s, text, emit)

    def _run(self, s: Session, text: str, emit: Emit, may_ask: bool = True, quiet: bool = False) -> None:
        """One agent turn: record what the user said, then let the agent loop run until it asks, finishes or replies."""
        st, prev = s.state, s.card
        turn = st.meta.turn + 1
        closed_at = len(s.transcript)
        self._close_card(s)
        closed = len(s.transcript) > closed_at
        s.transcript.append({"role": "user", "text": text, "turn": turn, "kind": "text"})
        pre = prepass(text, self.today())
        emit("preview", {"fields": [{"target": p.field, "value": values.jsonable(p.value), "quote": p.quote}
                                    for p in pre.proposals]})
        st = self._deterministic(with_meta(st, turn=turn), text, pre, turn)
        compared = compared_places(text, self.catalog)
        heard = " ".join(t["text"] for t in s.transcript if t["role"] == "user")
        tools = TurnTools(st, text, turn, self.catalog, self.today(), compared, may_ask, self.judge)
        hints = [{"field": p.field, "value": values.jsonable(p.value), "quote": p.quote} for p in pre.proposals]
        hints += [{"ambiguous": q, "may_mean": list(k)} for q, k in pre.ambiguous]
        log = tools.log
        needed = missing(st, self.cfg.required)
        fixed, read = self._fixed_reply(text, prev, pre, log, tuple(needed)) if may_ask else (None, ClefRoute())
        # a message with only trip facts needs no FEATURES list; a keyword taste or an ambiguity means it might
        lean = read.plain and not compared and not pre.ambiguous and not any(p.field in ("soft", "hard") for p in pre.proposals)
        if lean:
            log.append("clef_lean")
        messages = build_messages(st, text, s.transcript[:-1], prev.text if prev else None, self.today(), hints, compared,
                                  may_ask, dict(needed), lean, read.next_field)
        said: list[str] = []

        def on_say(delta: str) -> None:
            said.append(delta)
            emit("say", {"delta": delta})

        try:
            if fixed is None:
                asyncio.run(run_loop(self.chat, messages, tools, on_say, self.cfg.tool_steps))
        except AgentError as exc:
            log.append(f"agent_error: {exc}")
            if not said:
                said.append(FALLBACK_SAY)
                emit("say", {"replace": FALLBACK_SAY})
        say = "".join(said).strip()
        if fixed:  # Clef answered for the Agent: nothing learned, nothing spent, the open question stays
            say = fixed
            emit("say", {"replace": say})
        if not may_ask:
            plain = drop_questions(say)  # no card follows here, so a question would go unanswered
            if plain != say:
                say = plain
                emit("say", {"replace": say})
        if tools.lead and not tools.unmapped:  # a comment written in front of a card's question belongs in the chat
            say = f"{say} {tools.lead}".strip()
            emit("say", {"replace": say})
        if tools.unmapped:  # fixed reply: the model's own words could promise what the search cannot do
            say = UNMAPPED_SAY.format(wish=", ".join(f"“{w}”" for w in tools.unmapped))
            emit("say", {"replace": say})
        elif why := (bad_say(say, heard, tools.state, self.catalog, {c["id"] for c in compared})
                     or (self.judge.bad_reply(say) if self.judge and say and not fixed else None)):
            log.append(f"say replaced: {why}")
            say = UNSURE_SAY if say else ""  # never leave the user's question or message without a visible reply
            emit("say", {"replace": say})
        if say:
            s.transcript.append({"role": "agent", "text": say, "turn": turn, "kind": "say"})
        s.transcript.append({"role": "system", "text": "; ".join(log) or "no tools", "turn": turn})
        s.state = tools.state
        if quiet:
            return
        s.card = tools.card
        if s.card is None and prev is not None and prev.qid.startswith("ask:"):
            s.card = prev  # nothing new was asked (a reply, an unmapped wish, an error): the open question stays open
            if closed:
                del s.transcript[closed_at]
        s.card = s.card or conversation_card()
        emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
        emit("card", self._card(s.state, s.card))

    def _fixed_reply(self, text: str, prev: Question | None, pre: Prepass, log: list[str],
                     needed: tuple = ()) -> tuple[str | None, ClefRoute]:
        """Clef first, in sequence: off topic / abuse, or a question for figures this step has no data for, get a fixed
        reply and the Agent is not called. A clue the keyword rules read means the message is about the trip; they have
        already written what they read, so a date framing a figure question is kept."""
        if self.route is None:
            return None, ClefRoute()
        r = self.route(text, prev.text if prev else None, needed)
        if r.reject and not (pre.proposals or pre.ambiguous):
            log.append(f"clef_reject:{r.reject}")
            return REJECT_SAY, r
        if r.asks_data and {p.field for p in pre.proposals} <= {"month", "start_date"}:  # a date only frames the question
            log.append("clef_data")
            return NODATA_SAY, r
        return None, r

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

    def _show(self, s: Session, inp: TurnInput | None, emit: Emit) -> None:
        if miss := missing(s.state, self.cfg.required):  # Next is the user's, but not before the minimum is known
            say = MISSING_SAY.format(items=", ".join(label for _, label in miss))
            s.transcript.append({"role": "agent", "text": say, "turn": s.state.meta.turn, "kind": "say"})
            emit("say", {"replace": say})
            emit("card", self._card(s.state, s.card))
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
        return settle(st)

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

    def _card(self, state: TripState, q: Question | None) -> dict | None:
        return card(q, chip_effects(state, q, self.catalog))

    def _close_card(self, s: Session) -> None:
        if s.card:
            s.transcript.append({"role": "agent", "text": s.card.text, "turn": s.state.meta.turn, "kind": "card"})
