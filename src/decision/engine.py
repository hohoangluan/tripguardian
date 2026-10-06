"""Place Decision sessions for the web (docs/PLACE_DECISION.md §12-15, §18): create, act (chips / buttons, no model), turn (typed text, one
agent call), compare, why-not, confirm. One lock per session; each change is one version that undo restores."""

import asyncio
import json
from datetime import datetime, timezone
from functools import cache
from typing import Awaitable, Callable

from corpus.ontology import load as load_ontology
from trip import SearchInput, squash

from . import output
from .agent import AgentError, features_text
from .compare import compare as compare_cands
from .curation import ActionError, apply
from .guard import TurnPlan, guard
from .pipeline import Data, Result, run, wanted, why_not
from .policy import DONE, NONE, policy
from .scope import STEPS, replan_scope
from .session import Pending, Session, State, Store
from .settings import Settings

Emit = Callable[[str, dict], None]
Agent = Callable[[dict, Callable[[str], None]], Awaitable[TurnPlan]]


class NoSession(Exception):
    pass


class VersionMismatch(Exception):
    pass


class NotConfirmable(Exception):
    pass


@cache
def _ontology_version() -> int:
    return load_ontology().version


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def diff(before: dict, after: dict, scope: dict | None) -> dict:
    b, a = set(before["shortlist"]), set(after["shortlist"])
    tb, ta = before["feasibility"]["totals"], after["feasibility"]["totals"]
    delta = {k: ta[k] - tb[k] for k in ("places", "visit", "travel")}

    def sign(n: int) -> str:
        return f"+{n}" if n > 0 else str(n)

    return {"added": sorted(a - b), "removed": sorted(b - a),
            "status": [before["feasibility"]["status"], after["feasibility"]["status"]], "delta": delta,
            "text": f"{sign(delta['places'])} nơi, {sign(delta['visit'])} phút tham quan, {sign(delta['travel'])} phút đi lại",
            "scope": scope}


def _earliest(actions: list[dict]) -> dict:
    scopes = [replan_scope(a) for a in actions]
    return min(scopes, key=lambda s: STEPS.index(s["from"]))


class Engine:
    def __init__(self, data: Data, cfg: Settings, store: Store, agent: Agent | None = None):
        self.data, self.cfg, self.store, self.agent = data, cfg, store, agent
        self._results: dict[str, Result] = {}
        self.name_keys = [(k, r["id"]) for r in data.records
                          if len((k := squash(r["identity"].get("name") or "")).split()) >= 3]

    # ---------- helpers ----------

    def _get(self, sid: str) -> Session:
        try:
            return self.store.get(sid)
        except KeyError:
            raise NoSession(sid) from None

    def _result(self, s: Session) -> Result:
        if s.id not in self._results:
            self._results[s.id] = run(s, self.data, self.cfg)
        return self._results[s.id]

    def _apply(self, s: Session, actions: list[dict], before: Result, strict: bool) -> tuple[State, list[dict], list[str]]:
        pend = Pending.model_validate(before.view["pending"]) if before.view["pending"] else None
        known = lambda p: p in before.cands or p in self.data.by_id  # noqa: E731
        st, done, log = s.state, [], []
        for a in actions:
            try:
                st = apply(st, a, known, before.alternatives, pend, self.cfg)
                done.append(a)
            except ActionError as e:
                if strict:
                    raise
                log.append(f"skip {a}: {e}")
        return st, done, log

    def _commit(self, s: Session, before: Result, logged: dict, scope: dict | None) -> dict:
        s.log.append({"version": len(s.history), "action": logged, "scope": scope, "at": _now()})
        self._results.pop(s.id, None)
        after = self._result(s)
        self.store.save(s)
        return {"view": after.view, "diff": diff(before.view, after.view, scope)}

    def _push(self, s: Session, new: State) -> None:
        s.history = (s.history + [s.state])[-self.cfg.history_max:]
        s.state = new

    # ---------- API ----------

    def create(self, search_input: dict, trip_session: str | None = None) -> dict:
        si = SearchInput.model_validate(search_input)
        if si.ontology_version != _ontology_version():
            raise VersionMismatch(f"Search Input ontology v{si.ontology_version}, corpus v{_ontology_version()}")
        st = State(selected=[a.place_id for a in si.anchors],
                   locked=[a.place_id for a in si.anchors if a.priority == "must"])
        s = self.store.new(si, trip_session, st)
        res = self._result(s)
        s.first_shortlist = len(res.view["shortlist"])
        self.store.save(s)
        return {"id": s.id, "view": res.view}

    def load(self, sid: str) -> dict:
        s = self._get(sid)
        with self.store.lock(sid):
            return {"id": s.id, "view": self._result(s).view}

    def report(self, place_id, text, reporter) -> dict:
        """A traveller reports something about a place in their own words. It is only stored here; it changes the
        corpus once enough different people report the same thing (corpus.observe.reports, next build)."""
        from corpus.review import reports

        if place_id not in self.data.by_id:
            raise ValueError(f"unknown place {place_id!r}")
        rec = reports.add(place_id, text, reporter)
        return {"id": rec["id"], "stored": True}

    def act(self, sid: str, action: dict) -> dict:
        s = self._get(sid)
        with self.store.lock(sid):
            before = self._result(s)
            if action.get("type") == "undo":
                if not s.history:
                    raise ActionError("nothing to undo")
                s.state = s.history.pop()
            else:
                new, _, _ = self._apply(s, [action], before, strict=True)
                self._push(s, new)
            out = self._commit(s, before, action, replan_scope(action))
            if action.get("type") == "answer" and action.get("qid") == "rethink" and action.get("chip") == "back":
                out["goto"] = "understand"
            return out

    def turn(self, sid: str, text: str, emit: Emit) -> None:
        s = self._get(sid)
        with self.store.lock(sid):
            before = self._result(s)
            aliases = self._aliases(before.view)
            fields = self._fields(before.view, aliases, text)
            streamed: list[str] = []

            def on_say(d: str) -> None:
                streamed.append(d)
                emit("say", {"delta": d})

            try:
                if self.agent is None:
                    raise AgentError("no agent configured")
                g = guard(asyncio.run(self.agent(fields, on_say)), text, aliases,
                          f"{fields['places']} {fields['feasibility']} {fields['pending']}", self.name_keys)
                actions, say, log = g.actions, g.say, g.log
            except AgentError as e:
                (actions, say), log = policy(text, aliases), [f"agent_fallback: {e}"]
            new, done, skipped = self._apply(s, actions, before, strict=False)
            say = say or (DONE if done else NONE)  # a guard-dropped say never leaves an empty bubble
            if say != "".join(streamed):
                emit("say", {"replace": say})
            logged = {"type": "turn", "text": text, "actions": done, "log": log + skipped}
            if done:
                self._push(s, new)
                out = self._commit(s, before, logged, _earliest(done))
            else:
                s.log.append({"version": len(s.history), "action": logged, "scope": None, "at": _now()})
                self.store.save(s)
                out = {"view": before.view, "diff": diff(before.view, before.view, None)}
            emit("view", out)
            emit("done", {})

    def compare(self, sid: str, a: str, b: str) -> dict:
        s = self._get(sid)
        with self.store.lock(sid):
            res = self._result(s)
            ca, cb = res.cands.get(a), res.cands.get(b)
            if ca is None or cb is None:
                raise ActionError(f"unknown place {a if ca is None else b!r}")
            out = compare_cands(ca, cb, wanted(s.search_input, s.state.profile), res.days, self.cfg)
            s.log.append({"version": len(s.history), "action": {"type": "compare", "a": a, "b": b}, "scope": None,
                          "at": _now()})
            self.store.save(s)
            return out

    def why_not(self, sid: str, pid: str) -> dict:
        s = self._get(sid)
        with self.store.lock(sid):
            return why_not(self._result(s), pid, s.search_input, self.cfg)

    def confirm(self, sid: str) -> dict:
        s = self._get(sid)
        with self.store.lock(sid):
            res = self._result(s)
            status = res.view["feasibility"]["status"]
            if status not in ("feasible", "unknown"):
                raise NotConfirmable(status)
            s.output = output.build(s, res, self.cfg)
            self.store.save(s)
            return s.output

    # ---------- agent prompt ----------

    @staticmethod
    def _aliases(view: dict) -> dict[str, dict]:
        out, seen = {}, set()
        for g in view["groups"]:
            for c in g["cards"]:
                if c["id"] in seen:
                    continue
                seen.add(c["id"])
                notes = "; ".join(t["text"] for t in (c["why"] + c["tradeoffs"])[:3])
                out[f"P{len(out) + 1}"] = {"id": c["id"], "name": c["name"], "group": g["label"],
                                           "chosen": c["chosen"], "notes": notes}
        for d in view["dropped"][-5:]:
            if d["id"] not in seen:
                seen.add(d["id"])
                out[f"P{len(out) + 1}"] = {"id": d["id"], "name": d["name"], "group": "-", "chosen": False,
                                           "notes": "đã bỏ"}
        return out

    @staticmethod
    def _fields(view: dict, aliases: dict, text: str) -> dict:
        f = view["feasibility"]
        places = "\n".join(f"{k} | {a['name']} | {a['group']} | {'chosen' if a['chosen'] else '-'} | {a['notes']}"
                           for k, a in aliases.items())
        t = f["totals"]
        return {"features": features_text(), "places": places or "none",
                "profile": json.dumps(view["profile"], ensure_ascii=False),
                "feasibility": f"{f['status']}; {t['places']} nơi; " + "; ".join(c["title"] for c in f["conflicts"][:3]),
                "pending": view["pending"]["text"] if view["pending"] else "none", "text": text}
