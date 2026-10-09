"""One conversation turn (docs/TRIP_UNDERSTANDING.md §4).

edit / show / theme, a skipped or unsure card and a day picked on a calendar are deterministic. Typing, and choosing an
option the agent wrote, run the agent loop (agent/loop.py): the agent records facts, then asks a card or just replies.
"""

import asyncio
import re
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
from ..domain.state import SCALARS, Evidence, Frozen, Meta, SoftKey, TripState, Update, apply, settle, with_meta
from ..domain.traits import compared_places
from ..domain.understanding import chip_effects, view as understanding
from ..infrastructure.catalog import Catalog
from ..infrastructure.clef import ClefRoute
from ..infrastructure.profile import ProfileStore
from ..infrastructure.sessions import Session, SessionStore
from ..infrastructure.settings import Settings

Emit = Callable[[str, dict], None]
Route = Callable[[str, str | None], ClefRoute]

GREETING = "Chào bạn! Mình hỏi vài câu ngắn để hiểu chuyến Đà Lạt của bạn trước khi chọn chỗ."
FALLBACK_SAY = ("Mình đã ghi lại những gì đọc được, nhưng trợ lý đang bận nên chưa hiểu hết câu này. "
                "Bạn gửi lại giúp mình nhé.")
BUSY_SAY = "Trợ lý đang bận nên chưa ghi được lựa chọn này. Bạn bấm lại giúp mình nhé."  # a button answer the agent missed
NOTED_SAY = "Mình đã ghi lựa chọn của bạn."  # a button answer recorded, then the agent failed before asking more
MISSING_SAY = "Mình cần biết thêm {items} trước khi tìm chỗ, bạn kể giúp mình nhé."
REJECT_SAY = "Mình chưa hỗ trợ nội dung này. Bạn vui lòng nhập câu hỏi khác về chuyến đi nhé."
NODATA_SAY = ("Mình chưa có số liệu thực tế về điều này ở bước này; thông tin thật sẽ hiện ở bước Lựa chọn. "
              "Bạn cứ kể tiếp về chuyến đi nhé.")
NOTED_TEXT_SAY = "Mình ghi lại như dưới đây, bạn xem có đúng không nhé."  # the agent's own words were held back
UNSURE_SAY = "Mình chưa chắc chắn về thông tin này nên chưa trả lời được ở bước này. Bạn cứ kể tiếp về chuyến đi nhé."
UNMAPPED_SAY = ("Mình đã ghi lại {wish}, nhưng hiện chưa dùng được điều này để lọc địa điểm. "
                "Bạn kể thêm về chuyến đi nhé.")
DONE_SAY = "Xong rồi, mình đi tìm chỗ hợp với chuyến này."
BAD_VALUE = "Giá trị này mình chưa đọc được, bạn thử lại nhé."
EXIT_LABEL = {"skip": "Bỏ qua", "unsure": "Chưa chắc"}  # what the user pressed, as it shows in the chat
DECLINE_SAY = "Không sao, mình để trống ý này."
DATE_SAY = "Mình ghi ngày đi {day}."
THEME_SAY = "Mình bắt đầu từ chủ đề “{title}”: {what}."
# after an answer the agent did not see: what the user can do next (no question is forced)
NEXT_MISSING = " Để tìm chỗ, mình còn cần biết {items}; bạn kể giúp mình nhé."
NEXT_READY = " Bạn kể thêm điều mình nên biết, hoặc bấm Xem gợi ý khi sẵn sàng."
THEME_UNKNOWN = "Chủ đề này không còn nữa, bạn chọn chủ đề khác nhé."
PAST_DATE = "Ngày này đã qua, bạn chọn ngày khác giúp mình nhé."


class TurnInput(Frozen):
    kind: Literal["text", "answer", "edit", "show", "theme"]  # theme: value = a theme id of config/trip.yaml
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


def _learned(before: TripState, after: TripState, fields: list[str]) -> bool:
    """Whether the agent wrote something new this turn: a field it recorded now holds another value than before the
    turn. A correction of something already known or an unmapped wish does not answer the open question."""
    def now(st: TripState, f: str):
        if f == "soft":
            return {k: x.value for k, x in st.soft.items()}
        if f in ("anchor", "signal", "hard"):
            return getattr(st, {"anchor": "anchors", "signal": "signals"}.get(f, f))
        return getattr(st, f).value

    return any(now(before, f) != now(after, f) for f in set(fields) - {"unmapped"})


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
                "transcript": [{k: t.get(k) for k in ("role", "text", "turn", "kind")} for t in s.transcript
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
        typed = inp.text.strip()
        exit_ = next((x for x in ("skip", "unsure") if x in inp.chips), None)
        if exit_ and not typed:
            return self._decline(s, q, exit_, emit)
        if q.input == "date" and inp.value and not typed:
            return self._pick_date(s, inp.value, emit)
        chosen = [c.label for c in q.chips if c.id in inp.chips]
        text = typed or ", ".join(chosen) or (inp.value or "")
        if not text:
            emit("card", self._card(s.state, s.card))
            return
        self._run(s, text, emit, answer=not typed)

    def _text(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        text = inp.text.strip()
        if not text:
            emit("card", self._card(s.state, s.card))
            return
        self._run(s, text, emit)

    def _run(self, s: Session, text: str, emit: Emit, may_ask: bool = True, quiet: bool = False,
             answer: bool = False) -> None:
        """One agent turn: record what the user said, then let the agent loop run until it asks, finishes or replies.
        answer: the text is an option the user pressed on the open card (it answers that card; Clef is not asked)."""
        before = st = s.state
        prev = s.card
        turn = st.meta.turn + 1
        closed_at = len(s.transcript)
        self._close_card(s)
        closed = len(s.transcript) > closed_at
        s.transcript.append({"role": "user", "text": text, "turn": turn, "kind": "text"})
        pre = prepass(text, self.today())
        emit("preview", {"fields": [{"target": p.field, "value": values.jsonable(p.value), "quote": p.quote}
                                    for p in pre.proposals]})
        st = self._deterministic(with_meta(st, turn=turn), text, pre, turn)
        if not quiet:  # what the keyword rules read shows at once, before the agent's slower reply
            emit("state", {"understanding": understanding(st, self.catalog, self.cfg)})
        compared = compared_places(text, self.catalog)
        heard = " ".join(t["text"] for t in s.transcript if t["role"] == "user")
        tools = TurnTools(st, text, turn, self.catalog, self.today(), compared, may_ask, self.judge)
        tools.transcript = s.transcript  # so tools can check if questions were recently asked
        hints = [{"field": p.field, "value": values.jsonable(p.value), "quote": p.quote} for p in pre.proposals]
        hints += [{"ambiguous": q, "may_mean": list(k)} for q, k in pre.ambiguous]
        log = tools.log
        needed = missing(st, self.cfg.required)
        messages = build_messages(st, text, s.transcript[:-1], prev.text if prev else None, self.today(), hints, compared,
                                  may_ask, dict(needed))
        said: list[str] = []
        failed = False
        shown = False  # the Agent starts at once, next to Clef; what it says stays unseen until Clef has let the turn through

        def on_say(delta: str) -> None:
            said.append(delta)
            if shown:
                emit("say", {"delta": delta})

        clef_log: list[str] = []
        fixed: str | None = None

        async def go() -> None:
            nonlocal shown, fixed
            agent = asyncio.ensure_future(run_loop(self.chat, messages, tools, on_say, self.cfg.tool_steps))
            if self.route is None or not may_ask or answer:  # a pressed option is never off topic
                shown = True
                return await agent
            fixed, _ = await asyncio.to_thread(self._fixed_reply, text, prev, pre, clef_log)
            if fixed:
                agent.cancel()
                try:
                    await agent
                except (asyncio.CancelledError, AgentError):
                    pass
                return
            shown = True
            if said:
                emit("say", {"delta": "".join(said)})
            await agent

        try:
            asyncio.run(go())
        except AgentError as exc:
            log.append(f"agent_error: {exc}")
            failed = True
            if not said:
                said.append((NOTED_SAY if tools.recorded else BUSY_SAY) if answer else FALLBACK_SAY)
                emit("say", {"replace": said[0]})
        finally:
            tools.close()
        if fixed:  # Clef answered for the Agent: whatever it already did is dropped, the open question stays
            tools.state, tools.card, tools.lead, tools.unmapped = st, None, "", []
            said.clear()
            log.clear()
        log.extend(clef_log)
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
                     or (tools.reply_problem() if say and not fixed else None)):
            log.append(f"say replaced: {why}")
            # never leave a question without a visible reply; a told trip gets an honest pointer to the summary
            say = (UNSURE_SAY if "?" in text else NOTED_TEXT_SAY) if say else ""
            emit("say", {"replace": say})
        card = tools.card
        if not quiet:
            if card is None and may_ask and say.endswith("?") and not (fixed or tools.unmapped or failed):
                asked = [x.strip() for x in re.split(r"(?<=[.!?…])\s+", say) if x.rstrip().endswith("?")]
                if asked and not tools.repeated(asked[-1]):
                    # asked in plain text instead of through a tool (Gemma often does): it becomes a card like ask_text's
                    card = Question(qid=f"ask:{turn}", group="I", tier=2, custom=True, input="text", text=asked[-1])
                    log.append("text_question")
            # The open question stays open when this turn did not answer it: a typed message the agent recorded
            # nothing new for (a reply, a correction, an unmapped wish, an error), or a pressed option the agent never
            # read. An answered one closes.
            answered = (answer and not failed) or _learned(before, tools.state, tools.recorded)
            if card is None and prev is not None and prev.qid.startswith("ask:") and not answered:
                card = prev
                if closed:
                    del s.transcript[closed_at]
            if card is not None and (plain := drop_questions(say)) != say:  # the card asks; the chat keeps the rest
                say = plain
                emit("say", {"replace": say})
        if say:
            s.transcript.append({"role": "agent", "text": say, "turn": turn, "kind": "say"})
        s.transcript.append({"role": "system", "text": "; ".join(log) or "no tools", "turn": turn})
        s.state = tools.state
        if quiet:
            return
        s.card = card or conversation_card()
        emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
        emit("card", self._card(s.state, s.card))

    def _fixed_reply(self, text: str, prev: Question | None, pre: Prepass, log: list[str]) -> tuple[str | None, ClefRoute]:
        """Clef, next to the Agent (it runs in a thread): off topic / abuse, or a question for figures this step has no data for, get a fixed
        reply and the Agent is not called. A clue the keyword rules read means the message is about the trip; they have
        already written what they read, so a date framing a figure question is kept."""
        if self.route is None:
            return None, ClefRoute()
        r = self.route(text, prev.text if prev else None)
        if r.reject and not (pre.proposals or pre.ambiguous):
            log.append(f"clef_reject:{r.reject}")
            return REJECT_SAY, r
        if r.asks_data and {p.field for p in pre.proposals} <= {"month", "start_date"}:  # a date only frames the question
            log.append("clef_data")
            return NODATA_SAY, r
        return None, r

    # ---------- answers the agent does not need to read ----------

    def _decline(self, s: Session, q: Question, exit_: str, emit: Emit) -> None:
        """"Bỏ qua" / "Chưa chắc": the field stays unknown and the question is never asked again. No model call."""
        turn = self._open_turn(s, EXIT_LABEL[exit_], "exit")
        s.state = with_meta(s.state, declined=s.state.meta.declined + (q.text,))
        self._close_turn(s, DECLINE_SAY, turn, emit)

    def _pick_date(self, s: Session, raw: str, emit: Emit) -> None:
        """A day picked on the calendar card is the start date the user chose. No model call."""
        try:
            day = date.fromisoformat(raw.strip()[:10])
        except ValueError:
            emit("error", {"message": BAD_VALUE})
            return
        if day < self.today():
            emit("error", {"message": PAST_DATE})
            return
        shown = f"{day.day}/{day.month}/{day.year}"
        turn = self._open_turn(s, shown, "answer")
        s.state = settle(apply(s.state, Update(field="start_date", value=day, source="user", confidence="high",
                                               evidence=Evidence(turn=turn, tool="date_picker"))))
        self._close_turn(s, DATE_SAY.format(day=shown), turn, emit)

    def _theme(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        """A theme card of Khám phá: its fixed tastes (config/trip.yaml `themes`) are written as they are; no sentence
        is read. They are the user's choice but not confirmed, so anything said later overrides them."""
        th = self.cfg.themes.get(inp.value or "")
        if th is None:
            emit("error", {"message": THEME_UNKNOWN})
            return
        turn = self._open_turn(s, th["title"], "theme")
        ev = Evidence(turn=turn, tool=f"theme:{inp.value}")
        st = s.state
        for raw in th.get("soft", ()):
            key, weight = values.split_weight(raw)
            st = apply(st, Update(field="soft", op="add", value=(str(SoftKey.parse(key)), weight), source="user",
                                  confidence="medium", evidence=ev))
        for g in th.get("groups", ()):
            st = apply(st, Update(field="liked_groups", op="add", value=g, source="user", confidence="medium",
                                  evidence=ev))
        s.state = settle(st)
        self._close_turn(s, THEME_SAY.format(title=th["title"], what=th["say"]), turn, emit)

    def _open_turn(self, s: Session, shown: str, kind: str) -> int:
        turn = s.state.meta.turn + 1
        self._close_card(s)
        s.transcript.append({"role": "user", "text": shown, "turn": turn, "kind": kind})
        s.state = with_meta(s.state, turn=turn)
        return turn

    def _close_turn(self, s: Session, say: str, turn: int, emit: Emit) -> None:
        """Ends a turn the agent did not run: the reply says what the user can do next; the chat box is open."""
        miss = missing(s.state, self.cfg.required)
        say += NEXT_MISSING.format(items=", ".join(label for _, label in miss)) if miss else NEXT_READY
        s.transcript.append({"role": "agent", "text": say, "turn": turn, "kind": "say"})
        s.card = conversation_card()
        emit("say", {"replace": say})
        emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
        emit("card", self._card(s.state, s.card))

    def _edit(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        ev = Evidence(turn=s.state.meta.turn, tool="edit")

        def user(field, value=None, op="set"):
            return Update(field=field, op=op, value=value, source="user", confidence="high", evidence=ev)

        kind, _, arg = inp.target.partition(":")
        v = inp.value
        try:
            if kind in SCALARS:
                u = user(kind, op="remove") if v is None else user(kind, values.parse(kind, v, self.catalog))
            elif kind in ("companions", "liked_groups"):
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
