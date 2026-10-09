"""The tools the Trip agent calls. Only record_fact writes the Trip State, and only through domain.guard."""

import re
from datetime import date
from typing import get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..domain import values
from ..domain.card import Chip, Question, conversation_card
from ..domain.dates import relative_dates, weekday_vi
from ..domain.guard import FieldName, record_fact, split_lead
from ..domain.resolve import search
from ..domain.state import TripState, ontology
from ..domain.text import contains, fold, squash
from ..infrastructure.catalog import Catalog
from .prompt import summarize

STOPPING = ("ask_choice", "ask_text")
MAX_OPTIONS, MAX_OPTION_LEN = 6, 40
# folded Vietnamese words that match almost every feature hint ("chó" folds to "cho" = "for")
STOP = {"cho", "co", "la", "va", "de", "o", "voi", "cua", "nhung", "khong", "mot", "cac", "nao", "duoc", "den", "trong",
        "nay", "thi", "muon", "thich", "choi", "di"}


class RelativeDateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expression: str = Field(min_length=1, max_length=80)


class PlaceLookupInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=100)


class ToolExecutor:
    """Read-only lookups."""

    def __init__(self, catalog: Catalog, today: date):
        self.catalog, self.today = catalog, today

    def run(self, name: str, arguments: dict, text: str) -> dict:
        if name == "resolve_relative_date":
            inp = RelativeDateInput.model_validate(arguments)
            if not contains(text, inp.expression):
                raise ValueError("expression must appear in the user message")
            matches = relative_dates(fold(inp.expression), inp.expression.lower(), self.today)
            if not matches or matches[0].field != "start_date":
                return {"status": "unknown"}
            resolved = matches[0].value
            return {"status": "ok", "start_date": resolved.isoformat(), "weekday": weekday_vi(resolved)}
        if name == "search_places":
            inp = PlaceLookupInput.model_validate(arguments)
            if not contains(text, inp.query):
                raise ValueError("query must appear in the user message")
            return {"places": [{"id": p.id, "name": p.name, "category": p.category}
                                for p in search(inp.query, self.catalog)[:5]]}
        raise ValueError("unknown tool")


def _fn(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": required, "additionalProperties": False}}}


SPECS = {
    "record_fact": _fn(
        "record_fact", "Write ONE fact about this trip that the user's latest message states or clearly implies. "
        "Call it once per fact. A refusal comes back as an error: fix the call or drop the fact.",
        {"field": {"type": "string", "enum": list(get_args(FieldName))},
         "op": {"type": "string", "enum": ["set", "add", "remove"]},
         "value": {"type": "string", "description": "In the format the instructions give for this field."},
         "quote": {"type": "string", "description": "The user's own words that support it, copied from the latest message."},
         "how": {"type": "string", "enum": ["said", "inferred"]}},
        ["field", "op", "value", "quote", "how"]),
    "resolve_relative_date": _fn(
        "resolve_relative_date", "Turn a relative date the user said (\"thứ 4 tuần sau\") into an ISO date.",
        {"expression": {"type": "string", "description": "The exact relative-date words from the user."}}, ["expression"]),
    "search_places": _fn(
        "search_places", "Look a place name the user typed up in the catalog. Never invent a place.",
        {"query": {"type": "string", "description": "The exact place words from the user."}}, ["query"]),
    "search_features": _fn(
        "search_features", "Look up which search features express a wish (\"chó\" -> animals). Use it BEFORE record_fact "
        "when no feature in FEATURES obviously fits; a wish no feature expresses cannot change the search.",
        {"query": {"type": "string", "description": "Vietnamese or English words for the wish; try synonyms."}}, ["query"]),
    "ask_choice": _fn(
        "ask_choice", f"Ask the user ONE multiple-choice question and wait. 2-{MAX_OPTIONS} short options in Vietnamese, "
        "each at most 40 characters. Ends your turn.",
        {"text": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}},
         "multi": {"type": "boolean", "description": "true when several options may be picked."},
         "reason": {"type": "string", "description": "Why this matters, one short Vietnamese clause."},
         "placeholder": {"type": "string", "description": "Example of what the user could type in the \"other answer\" box, "
                         "for THIS question, in their voice (\"cuối tháng 12\"). Empty if none."}},
        ["text", "options", "multi", "reason", "placeholder"]),
    "ask_text": _fn(
        "ask_text", "Ask the user ONE open question and wait for typed text. Ends your turn.",
        {"text": {"type": "string", "description": "ONLY the question, one short Vietnamese sentence: no greeting, no praise."},
         "placeholder": {"type": "string", "description": "Example answer the user could type, for THIS question, in their voice "
                         "(\"cuối tháng 12, hoặc 20/12\")."}},
        ["text", "placeholder"]),
}


class TurnTools:
    """One turn's tools. `state` is the turn's working Trip State; `card` / `outcome` are set by the stopping tools."""

    def __init__(self, state: TripState, text: str, turn: int, catalog: Catalog, today: date,
                 compared: list[dict] | None = None, may_ask: bool = True, judge=None):
        self.state, self.text, self.turn, self.catalog = state, text, turn, catalog
        self.compared, self.may_ask, self.judge = compared or [], may_ask, judge  # judge: infrastructure.clef.Judge or None
        self.lookup = ToolExecutor(catalog, today)
        self.card: Question | None = None
        self.lead = ""  # what the agent wrote in front of a card's question: the engine shows it as chat text
        self.unmapped: list[str] = []  # wishes stored as unmapped this turn: they end the turn with a fixed reply
        self.stopped = False
        self.log: list[str] = []

    def specs(self) -> list[dict]:
        return [s for n, s in SPECS.items() if self.may_ask or n not in STOPPING]

    def run(self, name: str, args: dict) -> dict:
        """-> the result the agent reads next. Never raises: a bad call is an error result."""
        if name not in SPECS or (name in STOPPING and not self.may_ask):
            return {"error": f"unknown tool {name!r}"}
        try:
            result = getattr(self, f"_{name}")(args)
        except (ValueError, ValidationError, KeyError, TypeError) as e:
            result = {"error": str(e).splitlines()[0]}
        detail = f" {args.get('field')}={args.get('value')}" if name == "record_fact" else ""
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
        if claim and self.judge.unsupported(str(a["quote"]), claim):
            self.log.append("clef_unsupported")
            raise ValueError(f"the quote {a['quote']!r} does not say this; quote the words that do, or drop the fact")
        self.state, note = record_fact(self.state, a["field"], a["op"], str(a["value"]), a["quote"], a["how"], self.text,
                                       self.turn, self.catalog, self.compared)
        if note.startswith("refused"):
            return {"error": note}
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

    def _already_known(self, question: str) -> None:
        if self.judge and question.strip() and self.judge.repeats(question, summarize(self.state)):
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
        self.lead, question = split_lead(str(a["text"]))
        self._already_known(question)
        self.card = Question(qid=f"ask:{self.turn}", group="I", tier=2, custom=True, input="text", text=question,
                             placeholder=str(a.get("placeholder", "")).strip()[:120])
        self.stopped = True
        return {"ok": True}
