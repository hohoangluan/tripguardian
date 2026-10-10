"""The tools the Trip agent calls. Only record_fact writes the Trip State, and only through domain.guard."""

import json
import re
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date

from pydantic import ValidationError

from ...domain import values
from ...domain.card import Chip, Question
from ...domain.guard import record_fact, split_lead
from ...domain.state import TripState, ontology
from ...domain.text import contains, fold, squash
from ...infrastructure.catalog import Catalog
from ..prompts import summarize
from .executor import ToolExecutor
from .specs import MAX_OPTION_LEN, MAX_OPTIONS, MAX_SENT_BACK, SPECS, STOP, STOPPING


class TurnTools:
    """One turn's tools. `state` is the turn's working Trip State; `card` / `outcome` are set by the stopping tools."""

    def __init__(self, state: TripState, text: str, turn: int, catalog: Catalog, today: date,
                 compared: list[dict] | None = None, may_ask: bool = True, judge=None, interactive: bool = True):
        self.state, self.text, self.turn, self.catalog = state, text, turn, catalog
        self.compared, self.may_ask, self.judge = compared or [], may_ask, judge  # judge: infrastructure.clef.Judge or None
        self.interactive = interactive  # False on a quiet turn (refine): nothing may restart the quiz there
        self.lookup = ToolExecutor(catalog, today)
        self.card: Question | None = None
        self.lead = ""  # what the agent wrote in front of a card's question: the engine shows it as chat text
        self.unmapped: list[str] = []  # wishes stored as unmapped this turn: they end the turn with a fixed reply
        self.recorded: list[str] = []  # fields record_fact wrote this turn
        self.stopped = False
        self.opened = False  # open_quiz was called: the engine starts, resumes, or restarts the quiz after this turn
        self.refused: set[str] = set()  # fields whose last record_fact was refused and not yet corrected
        self.sent_back = 0  # questions returned to the model while a refused fact stayed unfixed
        self.log: list[str] = []
        self.pool = ThreadPoolExecutor(max_workers=8) if judge else None
        self.checks: dict[tuple, Future] = {}  # Clef's checks sent when a reply arrived, read when its tool runs
        self.replies: list[Future] = []        # Clef's check of each text the model wrote
        self.transcript = []  # the session transcript, set by engine before tool calls
    def prefetch(self, calls, content: str) -> None:
        """Send every Clef check this model reply needs at the same moment, so they cost one round trip together and
        run while the tools execute: each inferred soft / hard fact, each question asked, and the text written."""
        if not self.judge:
            return
        args = []
        for c in calls:
            try:
                a = json.loads(c.arguments or "{}")
            except ValueError:
                continue
            if isinstance(a, dict):
                args.append((c.name, a))
        recorded = [{k: a.get(k) for k in ("field", "value")} for n, a in args if n == "record_fact"]
        for name, a in args:
            try:
                if name == "record_fact" and (claim := self._claim(a)) and contains(self.text, str(a["quote"])):
                    self.checks[("v", a["field"], str(a["value"]), str(a["quote"]))] = self.pool.submit(
                        self.judge.unsupported, str(a["quote"]), claim)
                elif name in ("ask_choice", "ask_text") and str(a.get("text", "")).strip():
                    question = split_lead(str(a["text"]))[1]
                    known = summarize(self.state) + " ; this reply also records " + json.dumps(recorded, ensure_ascii=False)
                    self.checks[("r", question)] = self.pool.submit(self.judge.repeats, question, known)
            except (KeyError, TypeError):
                continue
        if content.strip():
            self.replies.append(self.pool.submit(self.judge.bad_reply, content))

    def reply_problem(self) -> str | None:
        """Why Clef thinks the model's text may not be shown, or None."""
        return next((why for f in self.replies if (why := f.result())), None)

    def close(self) -> None:
        if self.pool:
            self.pool.shutdown(wait=False, cancel_futures=True)

    def _checked(self, key: tuple, fallback) -> bool:
        f = self.checks.get(key)
        return f.result() if f else fallback()

    def specs(self) -> list[dict]:
        def show(n: str) -> bool:
            if n == "open_quiz":
                # not asking in words but a deterministic handover: only on a live turn, never on quiet refine turns
                return self.interactive and (self.may_ask or self.state.meta.phase in ("quiz", "review", "paused"))
            return self.may_ask or n not in STOPPING
        return [s for n, s in SPECS.items() if show(n)]

    def run(self, name: str, args: dict) -> dict:
        """-> the result the agent reads next. Never raises: a bad call is an error result."""
        if name not in SPECS or (name in STOPPING and not self.may_ask
                                 and not (name == "open_quiz" and self.interactive
                                           and (self.may_ask or self.state.meta.phase in ("quiz", "review", "paused")))):
            return {"error": f"unknown tool {name!r}"}
        if name in STOPPING and self.refused and self.sent_back < MAX_SENT_BACK:
            # a fact was refused and is still not fixed: a question is sent back (twice at most) so the model deals with it
            self.sent_back += 1
            self.log.append(f"{name}:refused_first")
            return {"error": f"your record_fact for {sorted(self.refused)} was refused and is not fixed. Either call record_fact "
                             "again with a valid value, or, if no valid value fits what the user said, drop it and ask the user "
                             "about exactly that (ask_choice with the valid values as options)."}
        try:
            result = getattr(self, f"_{name}")(args)
        except (ValueError, ValidationError, KeyError, TypeError) as e:
            result = {"error": str(e).splitlines()[0]}
        detail = f" {args.get('field')}={args.get('value')}" if name == "record_fact" else ""
        if name == "record_fact":
            (self.refused.add if "error" in result else self.refused.discard)(args.get("field"))
        self.log.append(name + detail + (":error" if "error" in result else ":unmapped" if args.get("field") == "unmapped" else ""))
        return result

    # ---------- writes ----------

    def _claim(self, a: dict) -> str | None:
        """What an inferred soft / hard fact says, in words Clef can compare with the quote; None for any other field."""
        if a["field"] not in ("soft", "hard") or a["op"] == "remove" or a["how"] != "inferred":  # a said fact is the user's own words
            return None
        key, weight = values.split_weight(str(a["value"]))
        f = ontology().features.get(re.split(r"[=!]", key)[0])
        if f is None:
            return None
        stance = "muốn tránh" if weight == "avoid" or "!=" in key else "muốn"
        return f"khách {stance}: {f.hint[:100]}"

    def _record_fact(self, a: dict) -> dict:
        claim = self._claim(a) if self.judge and contains(self.text, str(a["quote"])) else None
        if claim and self._checked(("v", a["field"], str(a["value"]), str(a["quote"])),
                                   lambda: self.judge.unsupported(str(a["quote"]), claim)):
            self.log.append("clef_unsupported")
            raise ValueError(f"the quote {a['quote']!r} does not say this; quote the words that do, or drop the fact")
        self.state, note = record_fact(self.state, a["field"], a["op"], str(a["value"]), a["quote"], a["how"], self.text,
                                       self.turn, self.catalog, self.compared)
        if note.startswith("refused"):
            return {"error": note}
        self.recorded.append(a["field"])
        if a["field"] == "unmapped":  # only the agent decides a wish is unmapped
            self.unmapped.append(a["quote"])
        return {"ok": True, **({"note": note} if note else {})}

    # ---------- lookups ----------

    def _resolve_relative_date(self, a: dict) -> dict:
        return self.lookup.run("resolve_relative_date", a, self.text)

    def _search_features(self, a: dict) -> dict:
        if not squash(str(a["query"])):
            raise ValueError("query is empty")
        words = [w for w in squash(str(a["query"])).split() if len(w) >= 2 and w not in STOP]
        scored = []
        for f in ontology().features.values():
            text = f" {squash(f.id.replace('_', ' '))} {squash(f.hint)} {squash(f.group)} "
            if n := sum(f" {w} " in text for w in words):
                scored.append((-n, f.id, f))
        found = [{"id": f.id, "values": list(f.values), "meaning": f.hint[:120],
                  "use": f"{f.id}={f.values[0]}:love  (or :avoid)"} for _, _, f in sorted(scored)[:5]]
        if not found and self.judge:
            ids = self.judge.features(str(a["query"]), ontology().features.values())
            found = [{"id": f.id, "values": list(f.values), "meaning": f.hint[:120], "use": f"{f.id}={f.values[0]}:love  (or :avoid)"}
                     for i in ids if (f := ontology().features.get(i))]
            if found:
                self.log.append("clef_features")
        if found:
            return {"features": found}
        return {"features": [], "note": "no keyword match: read FEATURES by meaning; if none expresses the wish it is unmapped"}

    def _search_places(self, a: dict) -> dict:
        return self.lookup.run("search_places", a, self.text)

    # ---------- stopping tools ----------

    def repeated(self, question: str) -> str | None:
        """Why this question may not be asked now, read without Clef: the user declined it, or it was just asked."""
        folded = fold(question)
        if any(folded == fold(d) for d in self.state.meta.declined):
            return "declined_repeat"
        for t in reversed(self.transcript[-6:]):  # the last ~3 agent turns
            if t["role"] == "agent" and t.get("kind") == "card" and folded in fold(t["text"]):
                return "clef_repeat:recent"
        return None

    def _already_known(self, question: str) -> None:
        if not question.strip():
            return
        if why := self.repeated(question):
            self.log.append(why)
            raise ValueError("the user skipped this question (declined_questions); ask something else, or reply in text"
                             if why == "declined_repeat" else "just asked this question; ask something else, or reply in text")
        # Also check state if Judge is available
        if self.judge and self._checked(("r", question), lambda: self.judge.repeats(question, summarize(self.state))):
            self.log.append("clef_repeat")
            raise ValueError("the Trip State already answers this question; ask about something else, or reply in text")

    def _ask_choice(self, a: dict) -> dict:
        options = [str(o).strip() for o in a["options"]]
        if not str(a["text"]).strip():
            raise ValueError("text is empty")
        if not 2 <= len(options) <= MAX_OPTIONS or not all(0 < len(o) <= MAX_OPTION_LEN for o in options):
            raise ValueError(f"give 2-{MAX_OPTIONS} options of 1-{MAX_OPTION_LEN} characters each")
        self.lead, question = split_lead(str(a["text"]))
        self._already_known(question)
        self.card = Question(qid=f"ask:{self.turn}", group="I", tier=2, custom=True, multi=bool(a.get("multi")),
                             input="text", text=question, reason=str(a.get("reason", "")).strip(),
                             placeholder=str(a.get("placeholder", "")).strip()[:120],
                             chips=tuple(Chip(id=f"c{i}", label=o) for i, o in enumerate(options)))
        self.stopped = True
        return {"ok": True}

    def _ask_text(self, a: dict) -> dict:
        if not str(a["text"]).strip():
            raise ValueError("text is empty")
        if a.get("kind") == "date":  # the start date is the quiz's `dates` card; the agent only clarifies what was said
            self.log.append("date_ask_refused")
            raise ValueError("the start date is asked later on its own card; ask only about what the user wrote, or reply in text")
        self.lead, question = split_lead(str(a["text"]))
        self._already_known(question)
        self.card = Question(qid=f"ask:{self.turn}", group="I", tier=2, custom=True, input="text",
                             text=question, placeholder=str(a.get("placeholder", "")).strip()[:120])
        self.stopped = True
        return {"ok": True}

    def _open_quiz(self, a: dict) -> dict:
        if self.state.meta.phase not in ("chat", "quiz", "review", "paused"):
            raise ValueError("the quiz cannot be opened in this phase; reply in text")
        self.opened = True
        self.stopped = True
        return {"ok": True}
