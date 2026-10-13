"""One conversation turn (docs/TRIP_UNDERSTANDING.md §4).

edit / show / theme, a skipped or unsure card and a day picked on a calendar are deterministic. Typing, and choosing an
option the agent wrote, run the agent loop (agent/loop.py): the agent records facts, then asks a card or just replies.
"""

import asyncio
import base64
import binascii
import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from datetime import date
from typing import Callable, Literal

from pydantic import ValidationError, model_validator

from ..agent import AgentError, Chat, TurnTools, build_messages, run_loop
from ..domain import values
from ..domain import vibes
from ..domain.card import OPENING, Chip, Question, conversation_card
from ..domain.compile import UnhandledSignal, compile_search_input
from ..domain.guard import bad_say, drop_questions
from ..domain.logistics import pick_transit
from ..domain.patterns import Summary, seed, seed_profile, votes_from_state
from ..domain.prepass import Prepass, prepass
from ..domain.questions import (FIELD_LABEL, OFFER_QID, OTHER_CHIP, QUIZ_FIELD, REVIEW_QID, SOFT_LABEL, TO_QUIZ,
                                apply_chip, find_quiz, is_quiz, pending_fields, strictest,
                                quiz_queue, review_card)
from ..domain.readiness import missing
from ..domain.resolve import URL, anchor_for, search
from ..domain.coverage import admissible
from ..domain.state import (SCALARS, Draft, Evidence, Frozen, Meta, SoftKey, TripState, Update, Vibe, apply, apply_drafts,
                            ontology, pending_signals, settle, with_meta)
from ..domain.text import fold
from ..domain.traits import compared_places
from ..domain.understanding import chip_effects, view as understanding
from ..infrastructure.catalog import Catalog
from ..infrastructure.clef import ClefRoute
from ..infrastructure.profile import ProfileStore
from ..infrastructure.sessions import Session, SessionStore
from ..infrastructure.settings import ROOT, Settings

Emit = Callable[[str, dict], None]
TURN_LOG = ROOT / "logs" / "run" / "trip_turns.log"  # one JSON line per turn: tools called, retry, reply, card (debugging)


def log_turn(sid: str, turn: int, text: str, log: list[str], say: str, card: str, state: dict | None = None,
             path: Path = TURN_LOG) -> None:
    """Append one turn's trace. Logging must never break a turn, so a failed write is ignored."""
    line = {"at": datetime.now().isoformat(timespec="seconds"), "session": sid, "turn": turn, "user": text,
            "tools": log, "retried": "claim_without_record" in log, "say": say, "card": card, "state": state or {}}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass
Route = Callable[[str, str | None, str], ClefRoute]

GREETING = "Chào bạn! Mình hỏi vài câu ngắn để hiểu chuyến Đà Lạt của bạn trước khi chọn chỗ."
RECORDED_SAY = "Mình đã ghi lại ({got}). Bạn kể thêm gì về chuyến đi không?"
PARTIAL_SAY = "Mình đã ghi lại một phần ({got}), phần còn lại chưa xử lý xong. Bạn kể lại giúp mình nhé."
NOT_DONE_SAY = "Mình chưa xử lý xong ý này. Bạn kể lại giúp mình một lần nữa nhé."
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
DONE_SAY = "Xong rồi, mình đi tìm chỗ hợp với chuyến này."
OTHER_TYPE_SAY = "Bạn gõ ý của bạn vào ô bên dưới giúp mình nhé."
REVIEW_SAY = "Mình đã hỏi đủ những điều cần cho chuyến này. Các nơi đang hợp ở bảng bên cạnh."
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
# looks (domain/vibes.py): fixed lines, the agent does not run on these answers
KINDS_SAY = "Mình ghi lựa chọn của bạn: {labels}. Các nơi này lên đầu danh sách."
NO_KIND_SAY = "Không sao, mình không xếp theo kiểu nào. Bạn kể thêm nơi bạn thích trông thế nào nhé."
CUES_ONLY_SAY = "Mình ưu tiên nơi có {cues}."
PHOTO_SAY = "Trong ảnh mình thấy {cues}."
PHOTO_PLACE_SAY = "Mình sẽ tìm nơi cùng phong cách với {name}."
PHOTO_NOT_SAY = "Bạn kể thêm nơi này đẹp ở điểm nào nhé."
PHOTO_BLIND_SAY = "Mình chưa đọc được ảnh này. Bạn kể bằng lời giúp mình nhé."
BAD_PHOTO = "Ảnh này mình không mở được, bạn thử ảnh JPG hoặc PNG khác nhé."
MAX_PHOTO_BYTES = 2_000_000

# Prepass proposals allowed straight into the Trip State: high-precision slots only (dates, counts,
# money, explicit body signals, effort hard filters, single-meaning soft). Everything else arrives as
# agent-only suggestions and is recorded via record_fact.
APPLIED_FIELDS = frozenset({"start_date", "month", "month_part", "days", "nights", "people", "budget_vnd",
                            "budget_scope", "signal", "hard", "soft"})


class TurnInput(Frozen):
    kind: Literal["text", "answer", "edit", "show", "more", "theme", "to_chat", "to_quiz", "image"]  # theme: value = a theme id of config/trip.yaml; more: "Hỏi tiếp"; to_chat / to_quiz: legacy mode bar; image: value = a base64 photo, text = its caption
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
        if f == "activity":
            return st.activities
        if f == "time_preference":
            return st.time_preferences
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
                 route: Route | None = None, judge=None, looks=None, web=None, see=None):
        """chat: one model call with tools (agent/loop.py). profiles: stored patterns (config patterns.enabled);
        None = no long-term learning. route: Clef, asked before the Agent on a typed turn; None = never short-circuits.
        judge: Clef's yes / no checks on facts, replies and questions (infrastructure.clef.Judge); None = regex guards only.
        looks: corpus.index for looks and photos (infrastructure.looks.Looks); None = no photo cards.
        web: infrastructure.web.Web for the agent's web_search / web_read; None = no web tools.
        see: photo bytes -> {kind, cues} (Extractor PHOTO_CUES); None = a photo is matched by its pixels only."""
        self.catalog, self.cfg, self.store, self.chat, self.today = catalog, cfg, store, chat, today
        self.profiles, self.route, self.judge = profiles, route, judge
        self.looks, self.web, self.see = looks, web, see

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
                "card": self._card(s.state, s.card),
                "phase": s.state.meta.phase}

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
                    emit("done", {"search_input": compile_search_input(s.state, self.cfg.arrival_buffer_min, self.cfg.coach_min_people).model_dump(mode="json")})
                except UnhandledSignal:  # an open health hint: the user answers it on the Understand screen
                    pass
            finally:
                self.store.save(s)

    def _answer(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        if (i := vibes.index_of(inp.qid)) is not None:
            return self._vibe_answer(s, i, inp, emit)
        q = s.card
        if (q is None or q.qid != inp.qid) and is_quiz(inp.qid) and not inp.text.strip() \
                and (old := find_quiz(inp.qid, s.state, self.catalog, self.cfg)) is not None:
            return self._answer_quiz(s, old, inp, emit)  # an earlier card in the chat, still unanswered: it still counts
        if q is not None and q.qid == inp.qid and q.qid.startswith("pick:"):
            return self._answer_pick(s, q, inp, emit)
        if q is None or q.qid != inp.qid:
            emit("error", {"message": "Câu này đã qua, bạn trả lời câu mới nhất nhé."})
            emit("card", self._card(s.state, s.card))
            return
        if "show" in inp.chips:
            return self._show(s, inp, emit)
        if q.qid == OFFER_QID:
            return self._answer_offer(s, inp, emit)
        if q.qid == REVIEW_QID:
            return self._answer_review(s, inp, emit)
        if not q.custom and is_quiz(q.qid):
            return self._answer_quiz(s, q, inp, emit)
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
        if s.state.meta.phase == "review":
            return self._review_text(s, text, emit)
        if s.state.meta.phase == "quiz":
            qq = None
            if s.state.meta.other_qid:
                qq = find_quiz(s.state.meta.other_qid, s.state, self.catalog, self.cfg)
            if qq is None and s.card is not None and is_quiz(s.card.qid):
                qq = find_quiz(s.card.qid, s.state, self.catalog, self.cfg) or s.card
            if qq is not None:
                return self._quiz_typed(s, qq, text, emit)
        self._run(s, text, emit)

    def _review_text(self, s: Session, text: str, emit: Emit) -> None:
        """A wish typed in review: a normal chat turn, then back to the review card."""
        self._run(s, text, emit)
        if s.state.meta.phase == "review" and s.card is not None:
            s.card = review_card()
            emit("card", self._card(s.state, s.card))

    # ---------- quiz phase: deterministic answers, no model ----------

    def _answer_offer(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        """The F transition card of a session saved before it was dropped (every later question is a chip card now)."""
        if inp.text.strip():
            return self._text(s, inp, emit)
        picked = [c.id for c in (s.card.chips if s.card else ()) if c.id in inp.chips]
        if TO_QUIZ in picked:
            self._open_turn(s, "Làm trắc nghiệm", "answer")
            s.state = with_meta(s.state, phase="quiz")
            return self._quiz_next(s, emit)
        self._open_turn(s, "Kể thêm bằng chat", "answer")
        s.state = with_meta(s.state, phase="chat")
        s.card = conversation_card()
        emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
        emit("card", self._card(s.state, s.card))

    def _answer_review(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        text = inp.text.strip()
        if not text:
            emit("card", self._card(s.state, s.card))
            return
        self._review_text(s, text, emit)

    def _answer_quiz(self, s: Session, q: Question, inp: TurnInput, emit: Emit) -> None:
        """A chip on a quiz card writes its drafts straight into the state. Typed
        text goes through the other-gate instead."""
        typed = inp.text.strip()
        if q.input == "date" and inp.value and not typed:
            return self._pick_date(s, inp.value, emit)
        if q.input in ("geo", "lodging", "transit") and inp.value and not typed:
            return self._pick_logistics(s, q, inp.value, emit)
        if typed:
            return self._quiz_typed(s, q, typed, emit)
        picked = [c for c in q.chips if c.id in inp.chips and c.id != OTHER_CHIP]
        if OTHER_CHIP in inp.chips and not picked:
            emit("say", {"replace": OTHER_TYPE_SAY})
            emit("card", self._card(s.state, s.card))
            return
        exit_ = next((x for x in ("skip", "unsure") if x in inp.chips), None)
        if exit_ is not None and not picked:
            turn = self._open_turn(s, EXIT_LABEL[exit_], "exit")
            s.state = with_meta(s.state, asked=s.state.meta.asked + (q.qid,),
                                declined=s.state.meta.declined + (q.text,),
                                unsure_streak=s.state.meta.unsure_streak + 1)
            s.transcript.append({"role": "agent", "text": DECLINE_SAY, "turn": turn, "kind": "say"})
            emit("say", {"replace": DECLINE_SAY})
            emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
            return self._quiz_next(s, emit)
        if not picked:
            emit("card", self._card(s.state, s.card))
            return
        turn = self._open_turn(s, ", ".join(c.label for c in picked), "answer")
        try:
            st = apply_chip(s.state, q, tuple(c.id for c in picked), turn)
        except (ValueError, ValidationError, IndexError):
            emit("error", {"message": BAD_VALUE})
            emit("card", self._card(s.state, s.card))
            return
        s.state = with_meta(st, asked=st.meta.asked + (q.qid,))
        emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
        return self._quiz_next(s, emit)

    def _pick_logistics(self, s: Session, q: Question, raw: str, emit: Emit) -> None:
        """A row picked on the origin / lodging card, or a coach / flight on the transit card (or only its time, typed
        when no trip was found). No model call; a chosen trip also sets the city's entry or exit point."""
        try:
            parsed = values.parse(q.qid, raw, self.catalog)
            if isinstance(parsed, str):  # only a time: the day starts (inbound) or ends (outbound) then
                shown, put = parsed, ("checkin_at" if q.qid == "inbound" else "checkout_at", parsed)
            elif q.qid in ("inbound", "outbound"):
                shown, put = f"{parsed.carrier} {parsed.depart_at[11:]}", None
            else:
                shown, put = parsed.text, (q.qid, parsed)
            turn = s.state.meta.turn + 1
            ev = Evidence(turn=turn, tool=f"quiz:{q.qid}")
            if put is None:
                st = pick_transit(s.state, q.qid, parsed, self.cfg, turn)
            else:
                st = settle(apply(s.state, Update(field=put[0], value=put[1], source="user", confidence="high",
                                                  evidence=ev)))
        except (ValueError, ValidationError, KeyError, TypeError):
            emit("error", {"message": BAD_VALUE})
            emit("card", self._card(s.state, s.card))
            return
        self._open_turn(s, shown, "answer")
        s.state = with_meta(st, asked=st.meta.asked + (q.qid,))
        emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
        return self._quiz_next(s, emit)

    def _quiz_typed(self, s: Session, q: Question, text: str, emit: Emit) -> None:
        """Typed text while a quick-reply card is open. Clear for the card's field (prepass, then Clef + parse) fills
        it straight away; anything else is a chat message: the agent reads it, the card stays answerable above."""
        if (filled := self._gate_fill(s, q, text)) is not None:
            turn = self._open_turn(s, text, "text")
            s.state = with_meta(filled, turn=turn, asked=filled.meta.asked + (q.qid,),
                                other_qid=None, other_text=None)
            emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
            return self._quiz_next(s, emit)
        s.state = with_meta(s.state, phase="chat", other_qid=None, other_text=None)
        self._run(s, text, emit)

    def _gate_fill(self, s: Session, q: Question, text: str) -> TripState | None:
        """Other-gate attempt without touching the transcript: deterministic reads
        first (prepass), then Clef + parse. Returns the new state, or None when the
        chat phase must resolve it."""
        field = QUIZ_FIELD.get(q.qid)
        if field is None:
            return None
        turn = s.state.meta.turn + 1
        pre = prepass(text, self.today())
        st = self._deterministic(with_meta(s.state, turn=turn), text, pre, turn)
        fields = {"times": ("checkin_at", "checkout_at"), "dates": ("start_date", "month", "month_part")}.get(q.qid, (field,))
        if any(p.field in fields for p in pre.proposals):
            return st
        if self.judge is not None and (label := FIELD_LABEL.get(field)) \
                and self.judge.clear_for_field(text, label):
            try:
                parsed = values.parse(field, text, self.catalog)
                return settle(apply(st, Update(field=field, op="set", value=parsed, source="user",
                                               confidence="high", evidence=Evidence(turn=turn, quote=text))))
            except (ValueError, ValidationError):
                pass
        return None

    def _quiz_next(self, s: Session, emit: Emit) -> None:
        """The next quiz card, or the review card when the queue is empty."""
        queue = quiz_queue(s.state, self.catalog, self.cfg)
        if not queue:
            turn = s.state.meta.turn
            s.state = with_meta(s.state, phase="review", other_qid=None, other_text=None)
            s.card = review_card()
            s.transcript.append({"role": "agent", "text": REVIEW_SAY, "turn": turn, "kind": "say"})
            emit("say", {"replace": REVIEW_SAY})
            emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
            emit("card", self._card(s.state, s.card))
            return
        s.state = with_meta(s.state, phase="quiz")
        s.card = queue[0]
        emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
        emit("card", self._card(s.state, s.card))

    def _run(self, s: Session, text: str, emit: Emit, may_ask: bool = True, quiet: bool = False,
             answer: bool = False) -> None:
        """One agent turn: record what the user said, then let the agent loop run until it asks, finishes or replies.
        answer: the text is an option the user pressed on the open card (it answers that card; Clef is not asked)."""
        before = st = s.state
        prev = s.card
        # Chat mode is plain words, never cards: the agent asks in text and the user types. Quiz and review
        # keep cards; the quiz detour (_quiz_typed) only borrows the chat to resolve a typed answer.
        chat = s.state.meta.phase == "chat"
        clarify = may_ask and (not s.state.meta.told or chat)
        stuck = s.state.meta.unsure_streak >= 2 or s.state.meta.idle_streak >= 2
        turn = st.meta.turn + 1
        self._close_card(s)
        s.transcript.append({"role": "user", "text": text, "turn": turn, "kind": "text"})
        pre = prepass(text, self.today())
        emit("preview", {"fields": [{"target": p.field, "value": values.jsonable(p.value), "quote": p.quote}
                                    for p in pre.proposals]})
        st = self._deterministic(with_meta(st, turn=turn), text, pre, turn)
        if not quiet:  # what the keyword rules read shows at once, before the agent's slower reply
            emit("state", {"understanding": understanding(st, self.catalog, self.cfg)})
        compared = compared_places(text, self.catalog)
        heard = " ".join(t["text"] for t in s.transcript if t["role"] == "user")
        tools = TurnTools(st, text, turn, self.catalog, self.today(), compared, self.judge,
                          web=self.web if may_ask and not quiet else None, cards=may_ask and not quiet,
                          on_trace=lambda t: emit("progress", t))
        hints = [{"field": p.field, "value": values.jsonable(p.value), "quote": p.quote} for p in pre.proposals]
        hints += [{"ambiguous": q, "may_mean": list(k)} for q, k in pre.ambiguous]
        hints += [{"field": p.field, "value": values.jsonable(p.value), "quote": p.quote, "suggested": True}
                  for p in pre.suggestions]
        log = tools.log
        needed = missing(st, self.cfg.required)
        messages = build_messages(st, text, s.transcript[:-1], prev.text if prev else None, self.today(), hints, compared,
                                   clarify, dict(needed), stuck)
        said: list[str] = []
        shown = False  # the Agent starts at once, next to Clef; what it says stays unseen until Clef has let the turn through

        def on_retry() -> None:
            # the model is asked again: what it streamed so far is not shown or kept
            said.clear()
            if shown:
                emit("say", {"replace": ""})

        def on_say(delta: str) -> None:
            said.append(delta)
            if shown:
                emit("say", {"delta": delta})

        clef_log: list[str] = []
        fixed: str | None = None
        last_say = next((t["text"] for t in reversed(s.transcript)
                         if t["role"] == "agent" and t.get("kind") == "say" and t.get("text")), None)
        # the previous turn just parked a wish as unmapped and asked about it: this message likely answers it
        follows_unmapped = any(u.turn == turn - 1 for u in st.unmapped) and last_say is not None and "?" in last_say
        # Clef reads the recent exchanges, not just this message: an answer to our own question is on topic
        recent = [f"{'khách' if t['role'] == 'user' else 'mình'}: {(t.get('text') or '')[:120]}"
                  for t in s.transcript if t["role"] in ("user", "agent") and t.get("text")]
        history = "\n".join(recent[-6:])

        async def go() -> None:
            nonlocal shown, fixed
            agent = asyncio.ensure_future(run_loop(self.chat, messages, tools, on_say, self.cfg.tool_steps, on_retry))
            if self.route is None or not may_ask or answer:  # a pressed option is never off topic
                shown = True
                return await agent
            fixed, _ = await asyncio.to_thread(self._fixed_reply, text, prev, pre, clef_log, follows_unmapped,
                                                 history)
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
            if not said:
                said.append((NOTED_SAY if tools.recorded else BUSY_SAY) if answer else FALLBACK_SAY)
                emit("say", {"replace": said[0]})
        finally:
            tools.close()
        if fixed:  # Clef answered for the Agent: whatever it already did is dropped, the open question stays
            tools.state, tools.unmapped = st, []
            said.clear()
            log.clear()
        log.extend(clef_log)
        say = "".join(said).strip()
        if fixed:  # Clef answered for the Agent: nothing learned, nothing spent, the open question stays
            say = fixed
            emit("say", {"replace": say})
        if not say and (tools.recorded or "step_cap" in log) and tools.asked is None:  # the agent wrote no reply: never leave the turn silent
            got = ", ".join(sorted({FIELD_LABEL.get(f, f) for f in tools.recorded}))
            say = (PARTIAL_SAY if "step_cap" in log else RECORDED_SAY).format(got=got) if got else NOT_DONE_SAY
            emit("say", {"replace": say})
        if not may_ask:  # refine (Chọn nơi) asks nothing: a question would go unanswered there
            plain = drop_questions(say)
            if plain != say:
                say = plain
                emit("say", {"replace": say})
        # An unmapped wish is the agent's to handle (see UNMAPPED in the prompt): its own text stays, checked
        # below like any reply. Only a silent turn keeps the recorded-facts fallback above.
        if why := (bad_say(say, heard, tools.state, self.catalog, {c["id"] for c in compared})
                     or (tools.reply_problem() if say and not fixed else None)):
            log.append(f"say replaced: {why}")
            # never leave a question without a visible reply; a told trip gets an honest pointer to the summary
            say = (UNSURE_SAY if "?" in text else NOTED_TEXT_SAY) if say else ""
            emit("say", {"replace": say})
        card = None  # questions are plain text: the quiz cards come from the bank, never from the agent
        if say:
            s.transcript.append({"role": "agent", "text": say, "turn": turn, "kind": "say"})
        s.transcript.append({"role": "system", "text": "; ".join(log) or "no tools", "turn": turn,
                             "tools": {"recorded": list(tools.recorded), "refused": dict(tools.refusal_notes),
                                       "unmapped": list(tools.unmapped)}})
        s.state = tools.state
        if tools.asked is not None and not fixed and may_ask:
            card = self._asked(s, tools, turn)
        if _learned(before, tools.state, tools.recorded) or tools.asked is not None:
            s.state = with_meta(s.state, unsure_streak=0, idle_streak=0)
        elif may_ask and not fixed:
            # an adaptive turn that added nothing: the user may be stuck (surfaced as `stuck` next turn)
            s.state = with_meta(s.state, idle_streak=s.state.meta.idle_streak + 1)
        if clarify and not fixed and (card is not None or s.state.model_copy(update={"meta": before.meta}) != before):
            # the trip was told (something was read or asked; a greeting or "không đi nữa" is not a telling). An agent
            # that failed still leaves the keyword reads: the quiz asks the rest when the user switches to it.
            s.state = with_meta(s.state, told=True)
        if quiet:
            return
        resumed = False
        if may_ask and s.state.meta.other_qid:
            # the chat just resolved a typed quiz answer: back to the quiz, one card further
            other = s.state.meta.other_qid
            if _learned(before, tools.state, pending_fields(other)):
                s.state = with_meta(tools.state, other_qid=None, other_text=None,
                                    asked=tools.state.meta.asked + (other,))
                resumed = True
            elif (qq := find_quiz(other, tools.state, self.catalog, self.cfg)) is not None:
                card = qq  # not resolved yet: the chat clarifies, the chips stay available
        failed = bool(fixed) or "step_cap" in log or any(x.startswith("agent_error") for x in log)
        # a fixed reply or a failed agent leaves the text box: the user says it again before anything else is asked
        s.card = card or (conversation_card() if failed else self._next(s, say))
        st = s.state
        log_turn(s.id, turn, text, log, say, s.card.qid, {
            "companions": sorted(map(str, st.companions.value or ())), "start_date": str(st.start_date.value),
            "days": st.days.value, "unmapped": [u.phrase for u in st.unmapped]})
        if not resumed:
            emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
            emit("card", self._card(s.state, s.card))
            return
        self._quiz_next(s, emit)

    def _fixed_reply(self, text: str, prev: Question | None, pre: Prepass, log: list[str],
                     follows_unmapped: bool = False, history: str = "") -> tuple[str | None, ClefRoute]:
        """Clef, next to the Agent (it runs in a thread): off topic / abuse, or a question for figures this step has no data for, get a fixed
        reply and the Agent is not called. A clue the keyword rules read means the message is about the trip; they have
        already written what they read, so a date framing a figure question is kept. An off-topic verdict is also
        dropped when the message follows a turn that just parked a wish as unmapped and asked about it: the user is
        likely answering, not wandering off (abuse is still rejected)."""
        if self.route is None:
            return None, ClefRoute()
        r = self.route(text, prev.text if prev else None, history)
        if r.reject and not (pre.proposals or pre.ambiguous or pre.suggestions):
            if r.reject == "off_topic" and follows_unmapped:
                log.append("clef_skip_answer")
                return None, r
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
        s.state = with_meta(s.state, declined=s.state.meta.declined + (q.text,),
                            unsure_streak=s.state.meta.unsure_streak + 1)
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
        if s.state.meta.phase == "quiz" and s.card is not None and s.card.qid == "dates":
            s.state = with_meta(s.state, asked=s.state.meta.asked + ("dates",))
            emit("say", {"replace": DATE_SAY.format(day=shown)})
            emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
            return self._quiz_next(s, emit)
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
        s.state = with_meta(settle(st), told=True)  # the theme is the telling; the user picks chat or quiz next
        self._close_turn(s, THEME_SAY.format(title=th["title"], what=th["say"]), turn, emit)

    def _open_turn(self, s: Session, shown: str, kind: str) -> int:
        turn = s.state.meta.turn + 1
        self._close_card(s)
        s.transcript.append({"role": "user", "text": shown, "turn": turn, "kind": kind})
        s.state = with_meta(s.state, turn=turn)
        return turn

    def _close_turn(self, s: Session, say: str, turn: int, emit: Emit) -> None:
        """Ends a turn the agent did not run. The session stays in its phase: the quiz moves to its next
        card, chat keeps the text box open."""
        if s.state.meta.phase == "quiz":
            s.transcript.append({"role": "agent", "text": say, "turn": turn, "kind": "say"})
            emit("say", {"replace": say})
            return self._quiz_next(s, emit)
        s.card = self._next(s, say)
        if s.card.qid == "conversation":
            miss = missing(s.state, self.cfg.required)
            say += NEXT_MISSING.format(items=", ".join(label for _, label in miss)) if miss else NEXT_READY
        s.transcript.append({"role": "agent", "text": say, "turn": turn, "kind": "say"})
        emit("say", {"replace": say})
        emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
        emit("card", self._card(s.state, s.card))

    def _edit(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        ev = Evidence(turn=s.state.meta.turn, tool="edit")

        def user(field, value=None, op="set"):
            return Update(field=field, op=op, value=value, source="user", confidence="high", evidence=ev)

        kind, _, arg = inp.target.partition(":")
        v = inp.value
        if kind == "vibe":  # the ticket's ✕ on a look: it ranks nothing any more
            if not arg.isdigit() or int(arg) >= len(s.state.vibes) or v is not None:
                emit("error", {"message": BAD_VALUE})
                return
            gone = list(s.state.vibes)
            del gone[int(arg)]
            s.state = s.state.model_copy(update={"vibes": tuple(gone)})
            emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
            return
        try:
            if kind in SCALARS:
                if v is None:
                    u = user(kind, op="remove")
                else:
                    parsed = values.parse(kind, v, self.catalog)
                    if isinstance(parsed, str) and kind in ("inbound", "outbound"):  # only a time was typed: no trip to store
                        u = user("checkin_at" if kind == "inbound" else "checkout_at", parsed)
                    else:
                        u = user(kind, parsed)
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

    def _more(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        """"Hỏi tiếp": kept as an alias of the mode bar's to_quiz (an unanswered open card counts as declined)."""
        return self._to_quiz(s, inp, emit)

    def _to_chat(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        """The mode bar: free chat from here on (plain words, no cards). An open card left unanswered counts
        as declined: it is never asked again in either mode."""
        if s.state.meta.phase == "chat":
            emit("card", self._card(s.state, s.card))
            return
        self._close_card(s)
        self._decline_open_card(s)
        turn = s.state.meta.turn + 1
        s.transcript.append({"role": "user", "text": "Trò chuyện tự do", "turn": turn, "kind": "answer"})
        s.state = with_meta(s.state, turn=turn, phase="chat")
        s.card = conversation_card()
        emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
        emit("card", self._card(s.state, s.card))

    def _to_quiz(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        """The mode bar: quick chip cards from here on. An open card left unanswered counts as declined:
        it is never asked again in either mode."""
        if s.state.meta.phase == "quiz":
            emit("card", self._card(s.state, s.card))
            return
        was_review = s.card is not None and s.card.qid == REVIEW_QID
        self._close_card(s)
        self._decline_open_card(s)
        turn = s.state.meta.turn + 1
        s.transcript.append({"role": "user", "text": "Làm trắc nghiệm nhanh", "turn": turn, "kind": "answer"})
        s.state = with_meta(s.state, turn=turn, phase="quiz")
        if was_review and not quiz_queue(s.state, self.catalog, self.cfg):
            s.card = review_card()
            emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
            emit("card", self._card(s.state, s.card))
            return
        self._quiz_next(s, emit)

    def _decline_open_card(self, s: Session) -> None:
        """An open question left unanswered on a mode switch: never asked again in either mode."""
        q = s.card
        if q is None or q.qid in ("conversation", "frame"):
            return
        s.state = with_meta(s.state, asked=s.state.meta.asked + (q.qid,),
                            declined=s.state.meta.declined + (q.text,))

    def _show(self, s: Session, inp: TurnInput | None, emit: Emit) -> None:
        # Next is always open: unknown fields ride along as unknowns. An open health / body / diet hint gets the
        # strictest answer of its card (fail-closed); if one still stays open, Next waits for it.
        if pending_signals(s.state):
            s.state = apply_drafts(s.state, strictest(s.state), s.state.meta.turn, tool="next:strictest")
        if pending_signals(s.state):
            say = MISSING_SAY.format(items="điều cần lưu ý về sức khỏe")
            s.transcript.append({"role": "agent", "text": say, "turn": s.state.meta.turn, "kind": "say"})
            emit("say", {"replace": say})
            emit("card", self._card(s.state, s.card))
            return
        si = compile_search_input(s.state, self.cfg.arrival_buffer_min, self.cfg.coach_min_people)
        self._remember(s)
        self._close_card(s)
        s.card = None
        s.transcript.append({"role": "agent", "text": DONE_SAY, "turn": s.state.meta.turn, "kind": "done"})
        emit("done", {"search_input": si.model_dump(mode="json")})

    # ---------- helpers ----------

    def _deterministic(self, st: TripState, text: str, pre: Prepass, turn: int) -> TripState:
        """Links, pasted place lists, keyword matches: written before the agent so nothing depends on it.

        Only high-precision prepass proposals reach the state (dates, counts, money, explicit body
        signals, effort hard filters). Suggestions (who goes, transport, pace, novelty, kinds of place)
        are agent-only hints: the agent reads the user's words and records them via record_fact.
        """
        lines = [x.strip() for x in text.splitlines() if x.strip()]
        names = [x for x in lines if not URL.match(x)] if len(lines) >= 2 else []
        for raw in URL.findall(text) + names:
            a = anchor_for(raw, self.catalog)
            if a.state == "missing" and not URL.match(raw):
                continue
            st = apply(st, Update(field="anchor", op="add", value=a, source="user", confidence="high",
                                  evidence=Evidence(turn=turn, quote=raw)))
        for p in pre.proposals:
            if p.field not in APPLIED_FIELDS:
                continue
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

    def _next(self, s: Session, say: str) -> Question:
        """One chat flow: after a reply that asks nothing, the next bank question shows as quick replies under it;
        a reply that asks something, or a chat where the trip is not told yet, leaves the text box as the answer."""
        if "?" not in say and s.state.meta.told and s.state.meta.phase != "review":
            queue = quiz_queue(s.state, self.catalog, self.cfg)
            if queue:
                s.state = with_meta(s.state, phase="quiz")
                return queue[0]
        if s.state.meta.phase == "quiz":
            s.state = with_meta(s.state, phase="chat")
        return conversation_card()

    def _pool(self, st: TripState, scope: str = "any") -> set[str]:
        """Places past the hard limits now, of the kind a look is about: looks rank inside these, never outside."""
        groups = vibes.SCOPES.get(scope)
        return {c.id for c in self.catalog.places if admissible(c, st.hard, st.activities.get(c.id))
                and (groups is None or c.category_group in groups)}

    def _name(self, pid: str) -> str:
        c = self.catalog.by_id.get(pid)
        return c.name if c else (self.looks.name(pid) if self.looks else pid)

    def _match(self, st: TripState, cues: tuple[str, ...], step, scope: str = "any") -> tuple[list[str], list]:
        """The look's signs against the corpus photos: (places best first, their kinds)."""
        total = self.looks.total if self.looks else 0
        step("match", f"Đối chiếu {total:,} nơi".replace(",", "."), "run")
        places, vec = self.looks.by_cues(list(cues), self._pool(st, scope)) if self.looks else ([], None)
        kinds = self.looks.kinds(places[:80], vec) if places else []
        step("match", f"Đối chiếu {total:,} nơi · {len(places)} nơi gần".replace(",", "."), "ok" if self.looks and self.looks.ready() else "fail")
        return places, kinds

    def _asked(self, s: Session, tools: TurnTools, turn: int) -> Question:
        """The card the agent asked for with `ask`, built from real data (it only named the look or the readings)."""
        a = tools.asked
        if a["kind"] == "this_or_that":
            ont = ontology().features
            chips = []
            for n, o in enumerate(a["options"]):
                key, _ = values.split_weight(o)
                k = SoftKey.parse(key)
                label = SOFT_LABEL.get(key) or ont[k.feature].hint.split(",")[0].split(":")[0].strip().capitalize()
                chips.append(Chip(id=f"o{n}", label=label, drafts=(Draft(field="soft", op="add", value=(str(k), "love")),)))
            return Question(qid=f"pick:{turn}", group="G", tier=2, text=f"Ý “{a['about']}” của bạn gần với cái nào hơn?",
                            chips=tuple(chips), exits=True)
        tools.step("cues", "Tách thành dấu hiệu nhìn thấy được", "ok")
        vibe = Vibe(phrase=a["about"], turn=turn, cues=tuple(a["cues"]), scope=a.get("where", "any"),
                    sources=vibes.sources_of(tools.sources))
        places, kinds = self._match(s.state, vibe.cues, tools.step, vibe.scope)
        vibe = vibe.model_copy(update={"offered": tuple(kinds), "places": tuple(places[:vibes.VIBE_PLACES])})
        s.state, i = vibes.put(s.state, None, vibe)
        return vibes.cues_card(i, vibe, kinds, len(places), self.looks.total if self.looks else 0, self._name)

    def _answer_pick(self, s: Session, q: Question, inp: TurnInput, emit: Emit) -> None:
        """this_or_that: the chosen reading's soft value is written as it is, no model call."""
        picked = [c for c in q.chips if c.id in inp.chips]
        if not picked:
            exit_ = next((x for x in ("skip", "unsure") if x in inp.chips), None)
            return self._decline(s, q, exit_, emit) if exit_ else emit("card", self._card(s.state, s.card))
        turn = self._open_turn(s, picked[0].label, "answer")
        s.state = apply_drafts(s.state, picked[0].drafts, turn, tool=f"chip:{q.qid}")
        self._close_turn(s, f"Mình ghi “{picked[0].label}”.", turn, emit)

    def _vibe_answer(self, s: Session, i: int, inp: TurnInput, emit: Emit) -> None:
        """An answer on a look's card (signs, kinds, "is it this place?"), from any point of the chat. No model call."""
        if not 0 <= i < len(s.state.vibes):
            emit("error", {"message": "Câu này đã qua, bạn trả lời câu mới nhất nhé."})
            return
        v = s.state.vibes[i]
        exit_ = next((x for x in ("skip", "unsure") if x in inp.chips), None)
        steps: list[dict] = []

        def step(sid, label, status):
            steps[:] = [x for x in steps if x["id"] != sid] + [{"id": sid, "label": label, "status": status}]
            emit("progress", {"steps": list(steps), "sources": []})

        say, card = "", None
        if exit_:
            turn = self._open_turn(s, EXIT_LABEL[exit_], "exit")
            v = v.model_copy(update={"status": "none", "places": ()})
            say = DECLINE_SAY
        elif inp.value is not None:  # the signs card: kept / removed signs
            try:
                kept, removed = vibes.read_cues(inp.value)
            except ValueError:
                emit("error", {"message": BAD_VALUE})
                return
            turn = self._open_turn(s, "Đúng rồi, xem ảnh các kiểu", "answer")
            places, kinds = self._match(s.state, kept, step, v.scope)
            v = v.model_copy(update={"cues": kept, "removed": removed, "offered": tuple(kinds),
                                     "places": tuple(places[:vibes.VIBE_PLACES]), "chosen": ()})
            if len(kinds) >= 2:
                v = v.model_copy(update={"status": "kinds"})
                card = vibes.kinds_card(i, v, self._name)
            else:
                v = v.model_copy(update={"status": "done" if places else "none"})
                say = CUES_ONLY_SAY.format(cues=", ".join(kept))
        elif v.status == "cues" and v.picked is None and inp.chips and set(inp.chips) <= {"yes", "no"}:
            turn = self._open_turn(s, "Đúng nơi này" if "yes" in inp.chips else "Không phải", "answer")
            pid = (v.places or (None,))[0]
            if "yes" in inp.chips and pid:
                v = v.model_copy(update={"picked": pid, "status": "done",
                                         "places": (pid, *self.looks.similar(pid, self._pool(s.state)))[:vibes.VIBE_PLACES]
                                         if self.looks else (pid,)})
                say = PHOTO_PLACE_SAY.format(name=self._name(pid))
            elif len(v.offered) >= 2:
                v = v.model_copy(update={"status": "kinds", "places": ()})
                card = vibes.kinds_card(i, v, self._name)
            else:
                v = v.model_copy(update={"status": "none", "places": ()})
                say = PHOTO_NOT_SAY
        else:  # the kinds card
            ids = [c for c in inp.chips if c != "none"]
            v = vibes.choose(v, ids)
            labels = [k.label for k in v.offered if k.id in v.chosen]
            turn = self._open_turn(s, ", ".join(labels) or "Không kiểu nào giống", "answer")
            say = KINDS_SAY.format(labels=", ".join(labels)) if labels else NO_KIND_SAY
        s.state, _ = vibes.put(s.state, i, v)
        s.state = with_meta(s.state, told=True)
        if card is not None:
            s.card = card
            emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
            emit("card", self._card(s.state, s.card))
            return
        self._close_turn(s, say, turn, emit)

    def _image(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        """A photo the user sent: matched against the corpus photos (looks) and read for visible signs (see), in
        parallel. One clear match -> "is it X?"; else the kinds of the nearest places, or the signs to confirm. The
        photo is never stored: only the corpus places and the signs stay."""
        try:
            raw = (inp.value or "").split(",", 1)[-1]
            data = base64.b64decode(raw, validate=True)
            if not 0 < len(data) <= MAX_PHOTO_BYTES:
                raise ValueError("size")
            from PIL import Image
            Image.open(io.BytesIO(data)).verify()
        except (ValueError, binascii.Error, OSError):
            emit("error", {"message": BAD_PHOTO})
            return
        caption = inp.text.strip()[:200]
        turn = self._open_turn(s, caption or "Ảnh bạn gửi", "image")
        steps: list[dict] = []

        def step(sid, label, status):
            steps[:] = [x for x in steps if x["id"] != sid] + [{"id": sid, "label": label, "status": status}]
            emit("progress", {"steps": list(steps), "sources": []})

        step("read", "Đọc ảnh", "run")
        pool = self._pool(s.state)
        with ThreadPoolExecutor(2) as ex:
            seen = ex.submit(self.see, data) if self.see else None
            matched = ex.submit(self.looks.by_photo, data, pool) if self.looks else None
            try:
                read = seen.result() if seen else {}
            except Exception:  # the reader is down: the pixels still match
                read = {}
            vec, places, shows = matched.result() if matched else (None, [], None)
        try:
            cues = vibes.clean_cues(read.get("cues"), {fold(c.name) for c in self.catalog.places})
        except ValueError:
            cues = ()
        step("read", "Đọc ảnh" + (f" · {read['kind']}" if read.get("kind") else ""), "ok" if cues or places else "fail")
        total = self.looks.total if self.looks else 0
        step("match", f"Đối chiếu {total:,} nơi · {len(places)} nơi gần".replace(",", "."), "ok" if places else "fail")
        ids = [p.place_id for p in places]
        kinds = self.looks.kinds(ids[:80], vec) if self.looks and ids else []
        v = Vibe(phrase=caption or "ảnh bạn gửi", turn=turn, cues=cues, image=True, offered=tuple(kinds),
                 places=tuple(ids[:vibes.VIBE_PLACES]))
        if shows:
            step("name", "Kiểm tra tên và địa chỉ", "ok")
            v = v.model_copy(update={"places": (shows, *[p for p in ids if p != shows])[:vibes.VIBE_PLACES]})
            s.state, i = vibes.put(s.state, None, v)
            s.card = vibes.pick_card(i, v, shows, self.looks.best_photo(shows), self._name)
            say = ""
        elif len(kinds) >= 2:
            v = v.model_copy(update={"status": "kinds"})
            s.state, i = vibes.put(s.state, None, v)
            s.card = vibes.kinds_card(i, v, self._name)
            say = PHOTO_SAY.format(cues=", ".join(cues)) if cues else ""
        elif cues:
            s.state, i = vibes.put(s.state, None, v)
            s.card = vibes.cues_card(i, v, kinds, len(ids), total, self._name)
            say = PHOTO_SAY.format(cues=", ".join(cues))
        else:
            return self._close_turn(s, PHOTO_BLIND_SAY, turn, emit)
        s.state = with_meta(s.state, told=True)
        if say:
            s.transcript.append({"role": "agent", "text": say, "turn": turn, "kind": "say"})
            emit("say", {"replace": say})
        emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
        emit("card", self._card(s.state, s.card))

    def _card(self, state: TripState, q: Question | None) -> dict | None:
        return card(q, chip_effects(state, q, self.catalog))

    def _close_card(self, s: Session) -> None:
        if s.card and s.card.text.strip():  # an empty text box closing leaves no trace
            s.transcript.append({"role": "agent", "text": s.card.text, "turn": s.state.meta.turn, "kind": "card"})
