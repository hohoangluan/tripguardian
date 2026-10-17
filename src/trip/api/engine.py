"""One conversation turn (docs/TRIP_UNDERSTANDING.md §4).

edit / show / theme, a skipped or unsure card and a day picked on a calendar are deterministic. Typing, and choosing an
option the agent wrote, run the agent loop (agent/loop.py): the agent records facts, then asks a card or just replies.
"""

import asyncio
import binascii
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from datetime import date
from typing import Callable, Literal

from PIL import Image
from pydantic import ValidationError, model_validator

from ..agent import AgentError, Chat, TurnTools, build_messages, lookups, run_loop
from ..domain import ask, deck, drill, values
from ..domain.derive import derive
from ..domain.deck import Deck
from ..domain import vibes
from ..domain.card import OPENING, Chip, Question, conversation_card
from ..domain.compile import UnhandledSignal, compile_search_input
from ..domain.frame import FrameDefaults
from ..domain.readback import build as build_readback, party_conflict, plan_digest
from ..domain.guard import asks_settled_care, same_question, prune_say, bad_say, drop_questions, trim_say
from ..domain.logistics import pick_transit
from ..domain.patterns import Summary, seed, seed_profile, votes_from_state
from ..domain.prepass import Prepass, prepass
from ..domain.questions import (FIELD_LABEL, OFFER_QID, OTHER_CHIP, QUIZ_FIELD, REVIEW_QID, SOFT_LABEL, TO_QUIZ,
                                apply_chip, care_q, c_effort, companions_q, find_quiz, is_quiz, pending_fields, strictest,
                                quiz_queue, review_card)
from ..domain.readiness import missing
from ..domain.resolve import URL, anchor_for, search
from ..domain.coverage import admissible
from ..domain.state import (MAX_TRIP_DAYS, SCALARS, Draft, Evidence, Frozen, Meta, SoftKey, TripState, Update, Vibe, apply, apply_drafts,
                            ontology, pending_signals, settle, with_meta)
from ..domain.text import fold, language
from ..domain.traits import compared_places
from ..domain.understanding import chip_effects, view as understanding
from ..infrastructure.catalog import Catalog
from ..infrastructure.images import sanitize_photo
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

GREETING = "Chào bạn! Mình hỏi vài câu ngắn để hiểu chuyến Đà Lạt của bạn trước khi chọn chỗ."
RECORDED_SAY = "Mình đã ghi lại ({got})."  # asks nothing: the next question card shows under it
MOVE_ON_SAY = "Mình hỏi tiếp phần này nhé."  # the agent asked the same question again, so only its question is dropped
INVENTED = ("numbers", "names place")  # bad_say reasons a reply loses only the sentences that hold them
VAGUE = re.compile(r"\b(tuy|chua biet|khong biet|sao cung duoc|gi cung duoc|cung duoc|la duoc|ok|oke|duoc roi|chua chot|"
                   r"chua chac|bo qua|de trong|de sau)\b")
ASKING = re.compile(r"\b(goi y|de xuat|tu van|nen di|nen an|co nen|the nao|sao a|nhu nao)\b")  # the user asks, not tells
PARTIAL_SAY = "Mình đã ghi lại một phần ({got}), phần còn lại chưa xử lý xong. Bạn kể lại giúp mình nhé."
NOT_DONE_SAY = "Mình chưa xử lý xong ý này. Bạn kể lại giúp mình một lần nữa nhé."
FALLBACK_SAY = ("Mình đã ghi lại những gì đọc được, nhưng trợ lý đang bận nên chưa hiểu hết câu này. "
                "Bạn gửi lại giúp mình nhé.")
BUSY_SAY = "Trợ lý đang bận nên chưa ghi được lựa chọn này. Bạn bấm lại giúp mình nhé."  # a button answer the agent missed
DRILL_WAIT_S = 0.3  # how long a turn waits, after the agent, for its photo card (not ready: it shows on a later turn;
# waiting 3 s added 3 s to every long first message, 2026-10-16)
NOTED_SAY = "Mình đã ghi lựa chọn của bạn."  # a button answer recorded with no agent reply (closed card, or agent failed)
MISSING_SAY = "Mình cần biết thêm {items} trước khi tìm chỗ, bạn kể giúp mình nhé."
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
NOT_PLACE_SAY = ("Ảnh này không giống ảnh một nơi hay khung cảnh nào ở Đà Lạt nên mình không đối chiếu được. "
                 "Bạn gửi ảnh một quán, một góc đồi hay một homestay bạn thích, hoặc kể bằng lời nhé.")
BAD_PHOTO = "Ảnh này mình không mở được, bạn thử ảnh JPG hoặc PNG khác nhé."

# Prepass proposals allowed straight into the Trip State: high-precision slots only (dates, counts,
# money, explicit body signals, effort hard filters, single-meaning soft). Everything else arrives as
# agent-only suggestions and is recorded via record_fact.
FOLLOWUP_LIMIT = 3  # the agent's own questions in a row after which the app asks a required topic itself
APPLIED_FIELDS = frozenset({"start_date", "month", "month_part", "days", "nights", "people", "budget_vnd",
                            "budget_scope", "signal", "hard", "soft", "arrival_mode", "mobility", "driver", "unmapped"})
# Of those, the ones written as the user's own words (source user): the agent is told not to record or compute them again
EXACT_FIELDS = frozenset({"start_date", "month", "month_part", "days", "nights", "people", "budget_vnd", "budget_scope", "signal", "arrival_mode", "unmapped"})


class TurnInput(Frozen):
    kind: Literal["text", "answer", "edit", "show", "more", "theme", "to_chat", "to_quiz", "image", "deck", "drop", "readback_ok"]
    answers: dict[str, list[str] | str] = {}
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
        if f == "like" or f.startswith("wishes."):
            return st.wishes
        if f.startswith("frame.") or f == "drive_day_min":
            return getattr(st.frame, f.removeprefix("frame.")).value
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


def asks_in_text(say: str) -> bool:
    """The reply ends on a question to the user: the talk stays in plain words, no card opens under it."""
    lines = [x for x in say.strip().splitlines() if x.strip()]
    return bool(lines) and "?" in lines[-1]


def picked_text(d: Deck, answers: dict) -> str:
    """What the user chose on the card, as their line in the talk ("Đi với: Người yêu · 2 người")."""
    tabs = {t.qid: t for t in d.tabs}
    lines: dict[str, list[str]] = {}
    for key, raw in answers.items():
        owner, _, part = key.partition(".")
        tab = tabs.get(key) or tabs.get(owner)
        labels = {o.id: o.label for o in tab.options} if tab else {}
        for v in (raw if isinstance(raw, list) else [raw]):
            v = str(v)
            if v == "skip":
                shown = "Bỏ qua"
            elif key == "trip.dates" and ".." in v:
                a, b = v.split("..")
                shown = f"{a[8:10]}/{a[5:7]} – {b[8:10]}/{b[5:7]}"
            elif key in ("trip.start", "trip.end"):
                shown = f"{'bắt đầu' if part == 'start' else 'xong lúc'} {v}"
            elif key == "companions.people":
                shown = f"{v} người"
            elif key == "budget.amount" and v.isdigit():
                shown = f"{int(v) / 1_000_000:g} triệu".replace(".", ",")
            elif key == "budget.unlimited":
                shown = "không giới hạn"
            elif key == "lodging" and v.startswith("{"):
                try:
                    shown = str(json.loads(v).get("text") or "chỗ ở đã chọn")
                except ValueError:
                    shown = "chỗ ở đã chọn"
            else:
                shown = labels.get(v, v)
            lines.setdefault(tab.header if tab else "Lựa chọn", []).append(shown)
    return "\n".join(f"{h}: {' · '.join(dict.fromkeys(v))}" for h, v in lines.items()) or "Lựa chọn cho chuyến đi"


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
                 judge=None, looks=None, web=None, see=None):
        """chat: one model call with tools (agent/loop.py). profiles: stored patterns (config patterns.enabled);
        None = no long-term learning. judge: Clef's yes / no checks on facts, replies and questions (infrastructure.clef.Judge); None = regex guards only.
        looks: corpus.index for looks and photos (infrastructure.looks.Looks); None = no photo cards.
        web: infrastructure.web.Web for the agent's web_search / web_read; None = no web tools.
        see: photo bytes -> {kind, cues} (Extractor PHOTO_CUES); None = a photo is matched by its pixels only."""
        self.catalog, self.cfg, self.store, self.chat, self.today = catalog, cfg, store, chat, today
        self.profiles, self.judge = profiles, judge
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

    def _compile(self, state: TripState):
        return compile_search_input(state, self.cfg.arrival_buffer_min, self.cfg.coach_min_people,
                                    entry_min=self.cfg.entry_min, defaults=FrameDefaults(**self.cfg.frame))

    def _deck(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        legacy = not isinstance(s.card, Deck)
        current = (deck.build(s.state, self.catalog, self.cfg, agent=s.card.agent, at=s.card.at, ask=s.card.ask,
                              question=s.card.ask_question) if not legacy else
                   deck.build(s.state, self.catalog, self.cfg, at="gate" if s.card is None else "understand"))
        available = {t.qid: t for t in current.tabs}
        before = s.state
        turn = self._open_turn(s, picked_text(current, inp.answers), "answer")
        issues, flat, other = [], {}, False
        for key, raw in inp.answers.items():
            vals = raw if isinstance(raw, list) else [raw]
            tab = available.get(key)
            if tab is None:
                if key in ("trip.dates", "trip.start", "trip.end", "companions.who", "companions.people",
                           "budget.amount", "budget.scope", "budget.unlimited", "lodging") or key in ("mobility", "care", "pace"):
                    owner, _, input_key = key.partition(".")
                    target = available.get(owner)
                    if legacy or (target is not None and (not input_key or input_key in target.inputs or input_key == "unlimited")):
                        flat[key] = raw
                    else:
                        issues.append({"key": key, "code": "invalid"})
                else:
                    issues.append({"key": key, "code": "invalid"})
                continue
            if vals == ["skip"]:
                if tab.kind == "drill":
                    s.state = drill.skip(s.state, key.removeprefix("drill."))
                s.state = with_meta(s.state, declined=tuple(dict.fromkeys((*s.state.meta.declined, key))),
                                    soft_skips=s.state.meta.soft_skips + (tab.kind != "required"))
                continue
            if vals == ["other"]:
                if inp.text.strip():
                    other = True
                else:
                    issues.append({"key": key, "code": "invalid"})
                continue
            if tab.kind == "required" and key in ("mobility", "care", "pace", "lodging") and vals != ["lodging.prefilled"]:
                flat[key] = raw
                continue
            if key == "companions":
                if not vals or not set(vals) <= {o.id for o in tab.options if o.id not in ("other", "skip")}:
                    issues.append({"key": key, "code": "invalid"})
                    continue
                who = [v for v in vals if v != "people.prefilled"]
                if who:
                    flat["companions.who"] = who
                if "people.prefilled" in vals:
                    flat["companions.people"] = str(s.state.people.value)
                continue
            opts = {o.id: o for o in tab.options if o.id not in ("skip", "other")}
            if not vals or not set(vals) <= opts.keys() or (len(vals) > 1 and not tab.multi):
                issues.append({"key": key, "code": "invalid"})
                continue
            try:
                drafts = [d.model_copy(update={"inferred": False}) for v in vals for d in opts[v].writes]
                quote = next((d.quote for d in s.state.drills if key == f"drill.{d.topic}"), None) if tab.kind == "drill" else None
                st = apply_drafts(s.state, drafts, turn, tool=f"deck:{key}", quote=quote)
                if tab.kind == "drill":
                    topic = key.removeprefix("drill.")
                    st = drill.finish(st, topic, "done")
                    selected = [opts[v] for v in vals]
                    from ..domain.state import Vibe
                    from itertools import zip_longest
                    places = tuple(dict.fromkeys(p for row in zip_longest(*(o.places for o in selected))
                                                  for p in row if p))[:60]
                    if places:
                        st, _ = vibes.put(st, None, Vibe(phrase=topic, turn=turn, status="done", places=places,
                                                        cues=tuple(dict.fromkeys(c for o in selected for c in o.cues))))
                s.state = with_meta(st, asked=tuple(dict.fromkeys((*st.meta.asked, key))))
            except (ValueError, TypeError, ValidationError):
                issues.append({"key": key, "code": "invalid"})
        for key, raw in flat.items():
            vals = raw if isinstance(raw, list) else [raw]
            if not vals or (key not in ("companions.who", "care") and len(vals) != 1):
                issues.append({"key": key, "code": "invalid"})
                continue
            value = vals[0]
            ev = Evidence(turn=turn, tool=f"deck:{key}")

            def put(state, field, parsed):
                return apply(state, Update(field=field, value=parsed, source="user", confidence="high", evidence=ev))

            st = s.state
            try:
                if key == "trip.dates":
                    start_raw, end_raw = value.split("..")
                    start, end = date.fromisoformat(start_raw), date.fromisoformat(end_raw)
                    if start < self.today():
                        issues.append({"key": key, "code": "past_date"})
                        continue
                    if end < start:
                        issues.append({"key": key, "code": "end_before_start"})
                        continue
                    if (end - start).days + 1 > MAX_TRIP_DAYS:
                        issues.append({"key": key, "code": "too_long"})
                        continue
                    st = put(st, "days", (end - start).days + 1)
                    st = put(st, "start_date", start)
                elif key in ("trip.start", "trip.end"):
                    st = put(st, "checkin_at" if key == "trip.start" else "checkout_at", values.clock(value))
                elif key == "companions.who":
                    if not set(vals) <= set(values.ENUM_VALUES["companions"]):
                        raise ValueError("invalid companions")
                    from ..domain.questions import WHO
                    st = put(st, "companions", vals)
                    implied = [d for v in vals for d in WHO[v][1] if d.field != "companions"]
                    st = apply_drafts(st, implied, turn, tool=ev.tool)
                elif key == "companions.people":
                    who = set(vals_who) if (vals_who := flat.get("companions.who")) else set(st.companions.value or ())
                    # alone is one person whatever the count box says (a guest sent "0 người" four times, 2026-10-16)
                    st = put(st, "people", 1 if who == {"solo"} else int(value))
                elif key == "mobility":
                    if value not in ("motorbike", "car_self", "car_hired", "walk"):
                        raise ValueError("invalid mobility")
                    st = put(st, "mobility", "car" if value.startswith("car_") else value)
                    st = put(st, "driver", value[4:] if value.startswith("car_") else None)
                elif key == "care":
                    if "none" in vals:
                        if len(vals) != 1:
                            raise ValueError("conflicting care choices")
                        inferred = [sig.kind for sig in pending_signals(st)
                                    if sig.from_companion is not None or sig.source == "inferred"]
                        st = put(st, "signal_handled", inferred)
                        if pending_signals(st):
                            issues.append({"key": key, "code": "contradicts_said"})
                        st = put(st, "care", "none")
                    else:
                        chips = {c.id: c.drafts for c in care_q().chips}
                        aliases = {"vegetarian": "veg", "motion_sick": "motion"}
                        for choice in vals:
                            chip = aliases.get(choice, choice)
                            if choice == "other":
                                if not inp.text.strip():
                                    raise ValueError("other care needs the user's words")
                                st = put(st, "unmapped", inp.text.strip())
                                continue
                            if choice not in ("steps", "wheelchair", "pregnant", "motion_sick", "height", "vegetarian", "vegan"):
                                raise ValueError("invalid care")
                            if choice != "steps":
                                st = apply_drafts(st, chips[chip], turn, tool=ev.tool)
                            if choice in ("steps", "wheelchair"):
                                drafts = next(c.drafts for c in c_effort(st).chips if c.id == "both")
                                st = apply_drafts(st, drafts, turn, tool=ev.tool)
                        st = put(st, "care", "listed")
                elif key == "pace":
                    st = put(st, "pace", values.parse("pace", value, self.catalog))
                    st = with_meta(st, conflicts=tuple(k for k in st.meta.conflicts if k != "pace"))
                elif key in ("budget.amount", "budget.scope", "budget.unlimited"):
                    field = {"budget.amount": "budget_vnd", "budget.scope": "budget_scope",
                             "budget.unlimited": "budget_unlimited"}[key]
                    st = put(st, field, values.parse(field, value, self.catalog))
                elif key == "lodging":
                    if value in self.catalog.by_id:
                        place = self.catalog.by_id[value]
                        parsed = {"place_id": value, "text": place.name}
                    else:
                        parsed = values.parse("lodging", value, self.catalog)
                    st = put(st, "lodging", parsed)
                else:
                    raise ValueError("unknown deck key")
                s.state = settle(st)
            except (ValueError, TypeError, ValidationError):
                issues.append({"key": key, "code": "invalid"})
        s.state = derive(s.state, self.catalog, turn)  # "Một mình" is one person, "gần trung tâm" a stay point, ...
        st = s.state
        if st.days.value == 1 and st.checkin_at.known and st.checkout_at.known and st.checkout_at.value < st.checkin_at.value:
            clock_keys = {"trip.start", "trip.end"} & flat.keys()
            key = "trip.end" if "trip.end" in clock_keys else "trip.start" if clock_keys else "trip.dates"
            issues.append({"key": key, "code": "end_before_start"})
            restored = st.model_copy(update={"checkin_at": before.checkin_at, "checkout_at": before.checkout_at})
            if not clock_keys or (before.checkin_at.known and before.checkout_at.known
                                  and before.checkout_at.value < before.checkin_at.value):
                restored = restored.model_copy(update={"days": before.days, "nights": before.nights, "start_date": before.start_date})
                if clock_keys and "trip.dates" in flat:
                    issues.append({"key": "trip.dates", "code": "end_before_start"})
            s.state = restored
        if {"companions.who", "companions.people"} & flat.keys() and st.people.known and st.companions.known:
            if st.people.value < 1 + len(set(st.companions.value) - {"solo"}):
                issues.append({"key": "companions.people", "code": "people_below_groups"})
        if issues:
            emit("deck_issues", {"issues": issues})
        s.card = deck.build(s.state, self.catalog, self.cfg, agent=current.agent, at=current.at, ask=current.ask,
                            question=current.ask_question)
        if other:
            return self._run(s, inp.text.strip(), emit)
        if current.at == "understand" and not issues and inp.answers:
            # whatever the user pressed (an option the agent wrote, a required topic, a photo variant, Bỏ qua) is
            # already written: the agent reads it like a reply in the talk, reacts and chooses the next question in
            # words that fit the talk. The app opens no required topic by itself.
            if self._tap_only(s, available, inp):
                return self._tap_next(s, turn, emit)
            return self._run(s, s.transcript[-1]["text"], emit, answer=True, picked=True)
        emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
        emit("card", self._card(s.state, s.card))

    def _tap_only(self, s: Session, available: dict, inp: TurnInput) -> bool:
        """True when the user only tapped options on required-topic cards, no words, and a required topic is still
        missing: the app records and opens the next one itself, without a model call."""
        if inp.text.strip() or self._user_asks(s):
            return False
        owners = {key.partition(".")[0] for key in inp.answers}
        if not owners or any((tab := available.get(o)) is None or tab.kind != "required" for o in owners):
            return False
        return self._next_required(s) is not None

    def _next_required(self, s: Session) -> str | None:
        m = s.state.meta
        return next((k for k, _ in missing(s.state, self.cfg.required)
                     if k not in m.declined and m.nudged.count(k) < 2), None)

    def _tap_next(self, s: Session, turn: int, emit: Emit) -> None:
        """A plain card tap: the answer is already written; open the next missing required topic in its default words."""
        started = time.monotonic()
        due = self._next_required(s)
        s.state = with_meta(derive(s.state, self.catalog, turn), unsure_streak=0, idle_streak=0, told=True,
                            nudged=(*s.state.meta.nudged, due), followups=0)
        s.card = deck.build(s.state, self.catalog, self.cfg, ask=due)
        s.transcript.append({"role": "system", "text": f"tap_next {due}", "turn": turn, "tools": {}})
        s.transcript.append({"role": "agent", "text": NOTED_SAY, "turn": turn, "kind": "say"})
        emit("say", {"replace": NOTED_SAY})
        emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
        emit("card", self._card(s.state, s.card))
        log_turn(s.id, turn, "(tap)", [f"tap_next {due}", f"t_turn {time.monotonic() - started:.2f}"], NOTED_SAY, s.card.qid, {})

    def _readback_ok(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        digest = plan_digest(self._compile(s.state)) if not pending_signals(s.state) else None
        if inp.value and inp.value != digest:
            emit("readback", self._readback(s.state))
            return
        if party_conflict(s.state.companions.value, s.state.people.value):
            emit("readback", self._readback(s.state))  # the clash is asked, not planned over
            return
        if not missing(s.state, self.cfg.required):
            s.state = with_meta(s.state, readback_digest=digest)
        emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})

    def _readback(self, state: TripState) -> dict:
        needed = [key for key, _ in missing(state, self.cfg.required)]
        try:
            rb = build_readback(self._compile(state))
            clash = party_conflict(state.companions.value, state.people.value)
            data = {**rb.model_dump(mode="json"), "conflicts": [clash] if clash else [],
                    "ok": not needed and not clash and state.meta.readback_digest == rb.digest}
        except UnhandledSignal:
            data = {"lines": [], "digest": None, "ok": False}
        gate = deck.build(state, self.catalog, self.cfg, at="gate") if needed else None
        return {**data, "missing": needed, "deck": self._card(state, gate)}

    def _drop(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        target = inp.target
        if target.startswith("soft:"):
            key = target.removeprefix("soft:")
            field = s.state.soft.get(key)
            if field is not None and field.source != "user":
                s.state = s.state.model_copy(update={"soft": {k: v for k, v in s.state.soft.items() if k != key}})
        elif target.startswith("frame.days."):
            _, _, index, key = target.split(".", 3) if target.count(".") == 3 else (None, None, None, None)
            if index is not None and index.isdecimal() and key in {"start", "end", "intensity"}:
                days = tuple(day.model_copy(update={key: None})
                             if day.index == int(index) and day.source != "user" else day for day in s.state.frame.days)
                s.state = s.state.model_copy(update={"frame": s.state.frame.model_copy(update={"days": days})})
        elif target.startswith("frame.busy."):
            label = target.removeprefix("frame.busy.")
            busy = tuple(b for b in s.state.frame.busy if b.label != label or b.source == "user")
            s.state = s.state.model_copy(update={"frame": s.state.frame.model_copy(update={"busy": busy})})
        else:
            owner = s.state.frame if target.startswith("frame.") else s.state
            key = target.removeprefix("frame.")
            field = getattr(owner, key, None) if key in type(owner).model_fields else None
            if target in {"frame.arrive", "frame.leave"} and not field.known:
                key = "inbound" if target == "frame.arrive" else "outbound"
                owner, field = s.state, getattr(s.state, key)
            if hasattr(field, "source") and hasattr(field, "known") and field.source != "user":
                updated = owner.model_copy(update={key: type(field)()})
                s.state = s.state.model_copy(update={"frame": updated}) if owner is s.state.frame else updated
                if target == "budget_scope":
                    s.state = with_meta(s.state, declined=tuple(dict.fromkeys((*s.state.meta.declined, target))))
        s.card = deck.build(s.state, self.catalog, self.cfg,
                            agent=s.card.agent if isinstance(s.card, Deck) else (),
                            at=s.card.at if isinstance(s.card, Deck) else "gate" if s.card is None else "understand",
                            ask=s.card.ask if isinstance(s.card, Deck) else None,
                            question=s.card.ask_question if isinstance(s.card, Deck) else None)
        emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
        emit("card", self._card(s.state, s.card))

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
                    emit("done", {"search_input": self._compile(s.state).model_dump(mode="json")})
                except UnhandledSignal:  # an open health hint: the user answers it on the Understand screen
                    pass
            finally:
                self.store.save(s)

    def _answer(self, s: Session, inp: TurnInput, emit: Emit) -> None:
        if (i := vibes.index_of(inp.qid)) is not None:
            return self._vibe_answer(s, i, inp, emit)
        q = s.card
        if isinstance(q, Deck):
            if inp.text.strip():
                return self._run(s, inp.text.strip(), emit)
            chips = [c.removeprefix("who:") if inp.qid == "companions" else c for c in inp.chips]
            return self._deck(s, TurnInput(kind="deck", answers={inp.qid: chips if chips else inp.value or ""}), emit)
        if (q is None or q.qid != inp.qid) and is_quiz(inp.qid) and not inp.text.strip() \
                and (old := find_quiz(inp.qid, s.state, self.catalog, self.cfg)) is not None:
            return self._answer_quiz(s, old, inp, emit)  # an earlier card in the chat, still unanswered: it still counts
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
        if isinstance(s.card, Deck):
            return self._run(s, text, emit)
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
             answer: bool = False, picked: bool = False) -> None:
        """An agent turn whose reply is sent once, when it is final: every check (Clef, guard, trim, a retry) has
        already run, so the user never sees words that are then replaced. Progress, state and cards pass at once."""
        held: list[str] = []
        sent = False

        def flush() -> None:
            nonlocal sent
            if not sent and held:
                # the checked reply streams word by word (say_stream_s in all), so it reads like typing but is
                # already final: nothing shown is ever taken back
                text = "".join(held)
                words = re.findall(r"\S+\s*", text) if self.cfg.say_stream_s > 0 else []
                words = words or [text]
                pause = self.cfg.say_stream_s / max(1, len(words) - 1)
                emit("say", {"replace": words[0]})
                for w in words[1:]:
                    time.sleep(pause)
                    emit("say", {"delta": w})
            sent = True

        def hold(ev: str, data: dict) -> None:
            if ev == "say" and not sent:
                held[:] = [data["replace"]] if "replace" in data else [*held, data.get("delta") or ""]
                return
            if ev in ("card", "done"):  # the reply goes out just before what ends the turn
                flush()
            emit(ev, data)

        try:
            self._agent_turn(s, text, hold, may_ask, quiet, answer, picked)
        finally:
            flush()

    def _agent_turn(self, s: Session, text: str, emit: Emit, may_ask: bool = True, quiet: bool = False,
                    answer: bool = False, picked: bool = False) -> None:
        """One agent turn: record what the user said, then let the agent loop run until it asks, finishes or replies.
        answer: the text is an option the user pressed on the open card (it answers that card; Clef is not asked).
        picked: the deck already wrote that answer and opened the turn (`text` is its summary): the agent only reacts
        and chooses the next question."""
        if not picked and isinstance(s.card, Deck):
            for tab in s.card.tabs:
                if tab.kind == "drill":  # its photos were shown and the user typed instead: answered in words, not shown again
                    s.state = drill.skip(s.state, tab.qid.removeprefix("drill."))
        started_at = time.monotonic()
        before = st = s.state
        prev = s.card
        # Chat mode is plain words, never cards: the agent asks in text and the user types. Quiz and review
        # keep cards; the quiz detour (_quiz_typed) only borrows the chat to resolve a typed answer.
        chat = s.state.meta.phase == "chat"
        clarify = may_ask and (not s.state.meta.told or chat)
        stuck = s.state.meta.unsure_streak >= 2 or s.state.meta.idle_streak >= 2
        turn = st.meta.turn + (0 if picked else 1)
        if not picked:
            self._close_card(s)
            s.transcript.append({"role": "user", "text": text, "turn": turn, "kind": "text"})
        pre = prepass("" if picked else text, self.today())
        emit("preview", {"fields": [{"target": p.field, "value": values.jsonable(p.value), "quote": p.quote}
                                    for p in pre.proposals]})
        st = with_meta(st, turn=turn) if picked else self._deterministic(with_meta(st, turn=turn), text, pre, turn)
        st = derive(st, self.catalog, turn)  # what the words already answer is written before the agent reads the state
        if not quiet:  # what the keyword rules read shows at once, before the agent's slower reply
            emit("state", {"understanding": understanding(st, self.catalog, self.cfg)})
        photos = None  # a drill just heard gets its photo card while the agent runs (no model call)
        if may_ask and not quiet and any(d.status == "pending" and d.tab is None for d in st.drills):
            pool = ThreadPoolExecutor(1)
            photos = pool.submit(drill.build, st, self.catalog, self.looks, self.cfg)
            pool.shutdown(wait=False)
        compared = compared_places(text, self.catalog)
        heard = " ".join(t["text"] for t in s.transcript if t["role"] == "user")
        tools = TurnTools(st, text, turn, self.catalog, self.today(), compared, self.judge,
                          web=self.web if may_ask and not quiet else None, cards=may_ask and not quiet,
                          history=tuple((t["turn"], t["text"]) for t in s.transcript if t["role"] == "user"),
                          gaps=Path(self.cfg.gaps_path),
                          on_trace=lambda t: emit("progress", t),
                          # each fact reaches the summary as soon as the model has written it, not when the turn ends
                          on_state=None if quiet else lambda st: emit(
                              "state", {"understanding": understanding(st, self.catalog, self.cfg)}))
        hints = [{"field": p.field, "value": values.jsonable(p.value), "quote": p.quote,
                  **({"written": True} if p.field in EXACT_FIELDS and not p.inferred else {})} for p in pre.proposals]
        hints += [{"ambiguous": q, "may_mean": list(k)} for q, k in pre.ambiguous]
        hints += [{"field": p.field, "value": values.jsonable(p.value), "quote": p.quote, "suggested": True}
                  for p in pre.suggestions]
        log = tools.log
        needed = missing(st, self.cfg.required)
        found = {} if picked else lookups(text, self.catalog)  # corpus lookups ready before the model reads the message
        messages = build_messages(st, text, s.transcript[:-1], prev.text if prev else None, self.today(), hints, compared,
                                   clarify, dict(needed), stuck, picked=picked, lookups=found)
        tools.step("read", "Đọc lựa chọn của bạn" if picked else "Đọc tin nhắn của bạn", "ok")
        said: list[str] = []

        def on_retry() -> None:
            # the model is asked again: what it streamed so far is not shown or kept
            said.clear()
            emit("say", {"replace": ""})

        def on_say(delta: str) -> None:
            said.append(delta)
            emit("say", {"delta": delta})

        try:
            asyncio.run(run_loop(self.chat, messages, tools, on_say, self.cfg.tool_steps, on_retry))
            tools.timings.append(f"t_agent {time.monotonic() - started_at:.1f}")
        except AgentError as exc:
            log.append(f"agent_error: {exc}")
            if not said:
                said.append((NOTED_SAY if tools.recorded else BUSY_SAY) if answer else FALLBACK_SAY)
                emit("say", {"replace": said[0]})
        finally:
            tools.close()
        if photos is not None:
            try:
                tools.state = drill.adopt(tools.state, photos.result(timeout=DRILL_WAIT_S))
            except Exception as exc:  # a photo card is optional: the turn goes on without it (a slow one is built
                log.append(f"drill_build_failed {type(exc).__name__}")  # again on a later turn)
        say = "".join(said).strip()
        if not say and (tools.recorded or "step_cap" in log) and tools.asked is None:  # the agent wrote no reply: never leave the turn silent
            got = ", ".join(sorted({FIELD_LABEL.get(f, "thông tin chuyến đi") for f in tools.recorded}))
            say = (PARTIAL_SAY if "step_cap" in log else RECORDED_SAY).format(got=got) if got else NOT_DONE_SAY
            emit("say", {"replace": say})
        if not may_ask:  # refine (Chọn nơi) asks nothing: a question would go unanswered there
            plain = drop_questions(say)
            if plain != say:
                say = plain
                emit("say", {"replace": say})
        # An unmapped wish is the agent's to handle (see UNMAPPED in the prompt): its own text stays, checked
        # below like any reply. Only a silent turn keeps the recorded-facts fallback above.
        told = " ".join(tools.refusal_notes.values())
        check = lambda x: bad_say(x, heard, tools.state, self.catalog, {c["id"] for c in compared},  # noqa: E731
                                  reply_language=language(text), told=told)
        invented = lambda x: w if (w := check(x)) and w.startswith(INVENTED) else None  # noqa: E731
        if (why := check(say)) and why.startswith(INVENTED) and (kept := prune_say(say, invented)) and check(kept) is None:
            # only the sentences with a figure or a place nobody said go; the rest of the reply stays
            log.append(f"say pruned: {why}")
            say, why = kept, None
            emit("say", {"replace": say})
        if why := (why or (tools.reply_problem() if say else None)):
            log.append(f"say replaced: {why}")
            # never leave a question without a visible reply; a told trip gets an honest pointer to the summary
            say = (UNSURE_SAY if "?" in text else NOTED_TEXT_SAY) if say else ""
            emit("say", {"replace": say})
        if language(text) == "en" and say and language(say) != "en":
            say = "I could not finish understanding that. Please tell me again."
            emit("say", {"replace": say})
        short = trim_say(say)
        if short != say:
            say = short
            emit("say", {"replace": say})
        last_ask = next((t["text"] for t in reversed(s.transcript[:-1]) if t["role"] == "agent" and t.get("kind") == "say"), "")
        if may_ask and same_question(say, last_ask):
            # the user went on without answering the question: it is not asked again (testers, 2026-10-16)
            log.append("same_question")
            say = drop_questions(say) or MOVE_ON_SAY
            emit("say", {"replace": say})
        if may_ask and asks_settled_care(say) and "care" not in dict(missing(tools.state, self.cfg.required)):
            # Lưu ý is answered with a safe limit already: how strict it is is not asked again (testers, 2026-10-16)
            log.append("care_asked_again")
            say = drop_questions(say)
            emit("say", {"replace": say})
        card = None
        if may_ask and tools.asked is not None and asks_in_text(say):
            # a card is this turn's one question: the reply keeps its reaction, never a second question beside it
            log.append("card_is_the_question")
            say = drop_questions(say)
            emit("say", {"replace": say})
        if (may_ask and tools.asked is None and asks_in_text(say)
                and any(d.turn == turn and d.status == "pending" and d.tab is not None for d in tools.state.drills)):
            # the taste the user just named has its photo card: the photos are this turn's one question, so the
            # agent's own question in words gives way to them
            log.append("drill_first")
            say = drop_questions(say)
            emit("say", {"replace": say})
        s.transcript.append({"role": "system", "text": "; ".join(log) or "no tools", "turn": turn,
                             "tools": {"recorded": list(tools.recorded), "refused": dict(tools.refusal_notes),
                                       "unmapped": list(tools.unmapped)}})
        if say:
            s.transcript.append({"role": "agent", "text": say, "turn": turn, "kind": "say"})
        kept = tools.settle_refusals(dict(s.state.meta.refusal_turns))
        tools.state = derive(tools.state, self.catalog, turn)
        s.state = with_meta(tools.state, refusal_turns=tuple(sorted(kept.items())))
        if may_ask and isinstance(prev, Deck) and VAGUE.search(fold(text)):
            # an open required card answered in words like "chưa chốt" / "bỏ qua" and still not filled: the same as its
            # Bỏ qua (asked again at the read-back before planning), so the talk moves on instead of showing it again
            still = {k for k, _ in missing(s.state, self.cfg.required)}
            put_off = [t.qid for t in prev.tabs if t.kind == "required" and t.qid in still]
            if put_off:
                log.append(f"put_off {put_off}")
                s.state = with_meta(s.state, declined=tuple(dict.fromkeys((*s.state.meta.declined, *put_off))))
        if tools.asked is not None and may_ask:
            card = self._asked(s, tools, turn)
            if tools.asked["kind"] == "agent" and not (isinstance(card, Deck) and any(t.kind in ("agent", "drill") for t in card.tabs)):
                # the post-check kept no question (code drops what it cannot offer): the agent's own words carry it
                # on, because the turn ended at ask_user and wrote no reply
                log.append("ask_dropped")
                if not say and (own := next((str(q.get("question") or "").strip() for q in tools.asked["questions"]), "")):
                    say = own
                    s.transcript.append({"role": "agent", "text": say, "turn": turn, "kind": "say"})
                    emit("say", {"replace": say})
        if _learned(before, tools.state, tools.recorded) or tools.asked is not None:
            s.state = with_meta(s.state, unsure_streak=0, idle_streak=0)
        elif may_ask:
            # an adaptive turn that added nothing: the user may be stuck (surfaced as `stuck` next turn)
            s.state = with_meta(s.state, idle_streak=s.state.meta.idle_streak + 1)
        if clarify and (card is not None or s.state.model_copy(update={"meta": before.meta}) != before):
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
        failed = "step_cap" in log or any(x.startswith("agent_error") for x in log)
        if card is None and not failed and may_ask and (due := self._due_required(s, say)):
            # the agent asked no required topic and the talk drifts (statement, or its own questions in a row): the
            # app asks the next one in the topic's default words, so the seven answers are never left to chance
            log.append(f"required_fallback {due}")
            if asks_in_text(say):
                say = drop_questions(say)
                emit("say", {"replace": say})
                if s.transcript and s.transcript[-1].get("kind") == "say":
                    s.transcript[-1]["text"] = say
            s.state = with_meta(s.state, nudged=(*s.state.meta.nudged, due))
            card = deck.build(s.state, self.catalog, self.cfg, ask=due)
        # a failed agent leaves the text box: the user says it again before anything else is asked
        s.card = card or (conversation_card() if failed else self._next(s, say))
        if may_ask:
            own = (s.card.qid == "conversation" and asks_in_text(say)) or (
                isinstance(s.card, Deck) and any(t.kind in ("agent", "drill") for t in s.card.tabs))
            s.state = with_meta(s.state, followups=s.state.meta.followups + 1 if own else 0)
        st = s.state
        log_turn(s.id, turn, text, log + tools.timings + [f"t_turn {time.monotonic() - started_at:.1f}"], say, s.card.qid, {
            "companions": sorted(map(str, st.companions.value or ())), "start_date": str(st.start_date.value),
            "days": st.days.value, "unmapped": [u.phrase for u in st.unmapped]})
        if not resumed:
            emit("state", {"understanding": understanding(s.state, self.catalog, self.cfg)})
            emit("card", self._card(s.state, s.card))
            return
        self._quiz_next(s, emit)

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
        if s.card.qid == "conversation" and not missing(s.state, self.cfg.required):
            say += NEXT_READY
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
        si = self._compile(s.state)
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
                exact = p.field in EXACT_FIELDS and not p.inferred
                st = apply(st, Update(field=p.field, op=p.op, value=p.value,
                                      source="user" if exact else "inferred",
                                      confidence="high" if exact else "low" if p.inferred else "medium",
                                      evidence=Evidence(turn=turn, quote=p.quote)))
            except (ValueError, ValidationError):
                pass
        if allergy := next((p for p in pre.proposals if p.field == "unmapped"), None):
            if not (st.care.known and st.care.source == "user"):  # the care question is answered by what they told
                st = apply(st, Update(field="care", value="listed", source="user", confidence="high",
                                      evidence=Evidence(turn=turn, quote=allergy.quote, tool="derived:allergy")))
        hints = tuple((p.value, p.quote) for p in pre.suggestions if p.field == "companions")
        rushed = bool(re.search(r"\b(goi y luon|tim luon|khoi hoi|nhanh len)\b", fold(text)))
        st = with_meta(st, companion_hints=tuple(dict.fromkeys((*st.meta.companion_hints, *hints))),
                       rushed=st.meta.rushed or rushed)
        return drill.note(settle(st), text, turn)

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

    def _next(self, s: Session, say: str) -> Question | Deck:
        """The open question after a turn in which the agent showed no card. A reply that ends on a question keeps the
        talk in plain text: the user answers in words. Otherwise the deck shows one question: a pending follow-up or a
        confirmation. A required topic is never opened here: only the agent asks it (ask_required), in its own words;
        with nothing to show the text box stays open."""
        s.state = drill.refresh(s.state, self.catalog, self.cfg)
        if asks_in_text(say):
            return conversation_card()
        built = deck.build(s.state, self.catalog, self.cfg,
                           agent=s.card.agent if isinstance(s.card, Deck) else ())
        return self._open(s, built)

    def _due_required(self, s: Session, say: str) -> str | None:
        """The required topic the app opens itself after a turn, or None. Only when the agent opened none and either
        its reply asks nothing (no deck tab waits either) or it has asked its own questions FOLLOWUP_LIMIT times in a
        row. Never while the user is asking, for a topic they skipped, nor more than twice for one topic."""
        m = s.state.meta
        asking = asks_in_text(say)
        last = fold(next((t["text"] for t in reversed(s.transcript) if t["role"] == "user"), ""))
        if self._user_asks(s) or (asking and m.followups < FOLLOWUP_LIMIT) or re.search(
                r"\b(khong muon (?:di|tiep)|khong di nua|thoi khong|huy)\b", last):
            return None
        if not asking and (built := deck.build(s.state, self.catalog, self.cfg, agent=s.card.agent if isinstance(s.card, Deck) else ())).tabs:
            return None
        return next((k for k, _ in missing(s.state, self.cfg.required)
                     if k not in m.declined and m.nudged.count(k) < 2), None)

    def _open(self, s: Session, built: Deck) -> Question | Deck:
        """The deck the app built, or the text box: no tab, or only the app's own confirmation while the user asks."""
        if built.tabs and built.tabs[0].kind == "confirm" and self._user_asks(s):
            return conversation_card()  # the user is asking: the app's confirmation waits for a calmer turn
        return built if built.tabs else conversation_card()

    @staticmethod
    def _user_asks(s: Session) -> bool:
        last = next((t["text"] for t in reversed(s.transcript) if t["role"] == "user"), "")
        return "?" in last or bool(ASKING.search(fold(last))) or fold(last).rstrip(" .!").endswith(" khong")

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

    def _asked(self, s: Session, tools: TurnTools, turn: int) -> Question | Deck:
        """The card the agent asked for with `ask`, built from real data (it only named the look or the readings)."""
        a = tools.asked
        if a["kind"] == "required":
            return deck.build(s.state, self.catalog, self.cfg, ask=a["topic"], question=a.get("question"))
        if a["kind"] == "agent":
            heard = " ".join(re.findall(r"\d+", " ".join(t["text"] for t in s.transcript if t["role"] == "user")))
            # a figure the user never said (an hour, a count) is the agent's invention: that question is dropped
            fresh = [q for q in a["questions"] if all(n in heard.split() for n in re.findall(
                r"\d+", " ".join([str(q.get("question") or "")] + [str(o.get("label") or "") for o in q.get("options") or ()])))]
            tabs = ask.check(fresh, s.state, self.catalog, self.cfg, self.looks)
            built = {t.qid.removeprefix("drill."): t for t in tabs if t.kind == "drill"}
            attempted = {ask.visual_topic(q, s.state) for q in a["questions"] if q.get("visual")}
            s.state = s.state.model_copy(update={"drills": tuple(
                d.model_copy(update={"tab": built[d.topic]}) if d.topic in built else
                d.model_copy(update={"status": "none"}) if d.topic in attempted and d.tab is None and d.status == "pending" else d
                for d in s.state.drills)})
            return self._open(s, deck.build(s.state, self.catalog, self.cfg, agent=tuple(t for t in tabs if t.kind != "drill")))
        tools.step("cues", "Tách thành dấu hiệu nhìn thấy được", "ok")
        vibe = Vibe(phrase=a["about"], turn=turn, cues=tuple(a["cues"]), scope=a.get("where", "any"),
                    sources=vibes.sources_of(tools.sources))
        places, kinds = self._match(s.state, vibe.cues, tools.step, vibe.scope)
        vibe = vibe.model_copy(update={"offered": tuple(kinds), "places": tuple(places[:vibes.VIBE_PLACES])})
        s.state, i = vibes.put(s.state, None, vibe)
        return vibes.cues_card(i, vibe, kinds, len(places), self.looks.total if self.looks else 0, self._name)

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
            data = sanitize_photo(inp.value or "")
        except (ValueError, binascii.Error, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
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
            read_ok = False
            try:
                read = seen.result() if seen else {}
                read_ok = "kind" in read and "cues" in read  # a real reading, even an empty one
            except Exception:  # the reader is down: the pixels still match
                read = {}
            vec, places, shows = matched.result() if matched else (None, [], None)
        try:
            cues = vibes.clean_cues(read.get("cues"), {fold(c.name) for c in self.catalog.places})
        except ValueError:
            cues = ()
        if read_ok and not cues and not read.get("kind") and not shows:
            # the reader saw no place or scene and no corpus photo is a clear match (a chart, a screenshot, a document):
            # the pixels still land near some corpus photos, but nothing here is a taste the user showed
            step("read", "Đọc ảnh · không phải ảnh nơi chốn", "fail")
            return self._close_turn(s, NOT_PLACE_SAY, turn, emit)
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

    def _card(self, state: TripState, q: Question | Deck | None) -> dict | None:
        if isinstance(q, Deck):
            q = deck.build(state, self.catalog, self.cfg, agent=q.agent, at=q.at, ask=q.ask, question=q.ask_question)
            q = q.model_copy(update={"tabs": tuple(ask.with_photos(t, state, self.catalog, self.looks) for t in q.tabs)})
            out = q.model_dump(mode="json", exclude={"agent": True, "at": True, "ask": True, "tabs": {"__all__": {"options": {"__all__": {"writes"}}}}})
            for tab in out["tabs"]:
                for option in tab["options"]:
                    if option["photo"]:
                        pid, file = option["photo"]
                        option["photo"] = {"place_id": pid, "name": self._name(pid), "url": vibes.media_url(file)}
            return out
        return card(q, chip_effects(state, q, self.catalog))

    def _close_card(self, s: Session) -> None:
        if s.card and s.card.text.strip():  # an empty text box closing leaves no trace
            s.transcript.append({"role": "agent", "text": s.card.text, "turn": s.state.meta.turn, "kind": "card"})
