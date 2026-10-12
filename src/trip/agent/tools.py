"""The tools the Trip agent calls. Only record_fact writes the Trip State, and only through domain.guard."""

import json
import re
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date
from typing import get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..domain import values
from ..domain.dates import relative_dates, weekday_vi
from ..domain.guard import FieldName, record_fact
from ..domain.resolve import search
from ..domain.state import TripState, ontology
from ..domain.text import contains, fold, squash
from ..infrastructure.catalog import Catalog

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
    "drop_refusal": _fn(
        "drop_refusal", "Drop a refused fact when the latest user message does not support any valid value. This writes nothing and lets you reply or ask about something else.",
        {"field": {"type": "string", "enum": list(get_args(FieldName))}}, ["field"]),
}

SPECS["record_fact"]["function"]["parameters"]["properties"]["requirement"] = {
    "type": "object", "description": "Intent metadata for hard/soft: meaning, scope, subject, subject_count, ambiguity.",
    "properties": {"meaning": {"type": "string"},
                   "scope": {"type": "string", "enum": ["all", "eating", "drinking", "sightseeing", "accommodation", "travel"]},
                   "subject": {"type": "string", "enum": ["traveler", "group", "member", "unspecified"]},
                   "subject_count": {"type": "integer", "minimum": 1, "maximum": 20},
                   "ambiguity": {"type": "string"}},
    "required": ["meaning", "scope", "subject"], "additionalProperties": False}


class TurnTools:
    """One turn's tools. `state` is the turn's working Trip State. Questions are never tools: the agent asks in text."""

    def __init__(self, state: TripState, text: str, turn: int, catalog: Catalog, today: date,
                 compared: list[dict] | None = None, judge=None):
        self.state, self.text, self.turn, self.catalog = state, text, turn, catalog
        self.compared, self.judge = compared or [], judge  # judge: infrastructure.clef.Judge or None
        self.lookup = ToolExecutor(catalog, today)
        self.unmapped: list[str] = []  # wishes stored as unmapped this turn: they end the turn with a fixed reply
        self.group_other = False  # the unmapped wish is a group the companions field does not hold
        self.recorded: list[str] = []  # fields record_fact wrote this turn
        self.written: set[tuple] = set()  # (field, op, value) written this turn: a repeat is not written twice
        self.refused: set[str] = set()  # fields whose last record_fact was refused and not yet corrected
        self.log: list[str] = []
        self.pool = ThreadPoolExecutor(max_workers=8) if judge else None
        self.checks: dict[tuple, Future] = {}  # Clef's checks sent when a reply arrived, read when its tool runs
        self.replies: list[Future] = []        # Clef's check of each text the model wrote

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
        for name, a in args:
            try:
                if name == "record_fact" and (claim := self._claim(a)) and contains(self.text, str(a["quote"])):
                    self.checks[("v", a["field"], str(a["value"]), str(a["quote"]))] = self.pool.submit(
                        self.judge.unsupported, str(a["quote"]), claim)
            except (KeyError, TypeError):
                continue
        if content.strip():
            self.replies.append(self.pool.submit(self.judge.bad_reply, content))

    def reply_problem(self) -> str | None:
        """Why Clef thinks the model's text may not be shown, or None."""
        return next((why for f in self.replies if (why := f.result())), None)

    def forget_replies(self) -> None:
        """The text just sent back is no longer the reply: only the next one is checked."""
        self.replies = []

    def close(self) -> None:
        if self.pool:
            self.pool.shutdown(wait=False, cancel_futures=True)

    def _checked(self, key: tuple, fallback) -> bool:
        f = self.checks.get(key)
        return f.result() if f else fallback()

    def specs(self) -> list[dict]:
        return list(SPECS.values())

    def run(self, name: str, args: dict) -> dict:
        """-> the result the agent reads next. Never raises: a bad call is an error result."""
        if name not in SPECS:
            return {"error": f"unknown tool {name!r}"}
        try:
            result = getattr(self, f"_{name}")(args)
        except (ValueError, ValidationError, KeyError, TypeError) as e:
            result = {"error": str(e).splitlines()[0]}
        detail = f" {args.get('field')}={args.get('value')}" if name == "record_fact" else ""
        if name == "record_fact":
            (self.refused.add if "error" in result else self.refused.discard)(args.get("field"))
        status = ":error" if "error" in result else ":unmapped" if args.get("field") == "unmapped" else ""
        why = f" [{str(result['error'])[:160]}]" if "error" in result else ""  # the reason, for the turn log
        self.log.append(name + detail + status + why)
        return result

    # ---------- writes ----------

    def _claim(self, a: dict) -> str | None:
        """What an inferred soft / hard fact says, in words Clef can compare with the quote; None for any other field."""
        if a["field"] == "time_preference" and a["op"] != "remove":
            return f"khách ưu tiên khung giờ và hoạt động: {a['value']}"
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
        key = (a["field"], a["op"], str(a["value"]))
        self.state, note = record_fact(self.state, a["field"], a["op"], str(a["value"]), a["quote"], a["how"], self.text,
                                       self.turn, self.catalog, self.compared, a.get("requirement"))
        if note.startswith("refused"):
            return {"error": note}
        if key in self.written:  # the same fact again in this turn: already in the state, so answer instead
            return {"ok": True, "note": "already recorded this turn: reply to the user now, in plain text, with no tool call"}
        self.recorded.append(a["field"])
        self.written.add(key)
        if a["field"] == "companions" and a["op"] != "remove":  # the group is now recorded: its stale "other" entries go
            self.state = self.state.model_copy(update={"unmapped": tuple(u for u in self.state.unmapped if not u.group)})
        if a["field"] == "unmapped":  # only the agent decides a wish is unmapped
            self.unmapped.append(a["quote"])
            self.group_other = "companions" in self.refused  # the refused companions fact is what this wish replaces
            if self.group_other and self.state.unmapped:
                *rest, last = self.state.unmapped
                self.state = self.state.model_copy(update={"unmapped": (*rest, last.model_copy(update={"group": True}))})
        return {"ok": True, **({"note": note} if note else {})}

    def _drop_refusal(self, a: dict) -> dict:
        field = str(a["field"])
        if field not in self.refused:
            raise ValueError(f"no refused record_fact for {field}")
        self.refused.discard(field)
        self.log.append(f"drop_refusal {field}")
        return {"ok": True}

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
