"""In-process handoffs through public module tools; no hidden LLM supervisor."""

import hashlib
import json
from datetime import datetime, timezone

from trip import SearchInput

from .contracts import Emit, Journey, JourneyView, ModuleTools, Request, Stage
from .router import route
from .session import Store


class Conflict(ValueError):
    pass


def _said(events: list[dict]) -> str:
    """The reply streamed so far through say events (deltas, or a replace)."""
    out = ""
    for e in events:
        if e["event"] == "say":
            out = e["data"]["replace"] if "replace" in e["data"] else out + e["data"].get("delta", "")
    return out


def _fingerprint(request: Request) -> str:
    raw = json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class Harness:
    def __init__(self, trip_tools: ModuleTools, decision_tools: ModuleTools, planning_tools: ModuleTools, store: Store):
        self.tools = {"trip": trip_tools, "decision": decision_tools, "planning": planning_tools}
        self.store = store
        self._loaded: set[str] = set()

    def _get(self, jid: str) -> Journey:
        session = self.store.get(jid)
        if jid not in self._loaded:
            for stage, snapshot in session.snapshots.items():
                self.tools[stage].restore(snapshot)
            self._loaded.add(jid)
        return session

    def _view(self, session: Journey, result: dict | None = None, stage: Stage | None = None) -> dict:
        shown = stage or session.stage
        if shown not in session.sessions:
            raise Conflict(f"no {shown} session")
        return JourneyView(id=session.id, stage=session.stage, revision=session.revision,
                sessions=session.sessions, outputs=session.outputs,
                result=result if result is not None else self.tools[shown].load(session.sessions[shown])).model_dump(mode="json")

    def create(self, experience=None, start_with=None, user_id=None, remember=False) -> dict:
        session = self.store.new()
        result = self.tools["trip"].create({"experience": experience, "start_with": start_with,
                                            "user_id": user_id, "remember": remember})
        session.sessions["trip"] = result["id"]
        session.snapshots["trip"] = self.tools["trip"].snapshot(result["id"])
        self.store.save(session)
        self._loaded.add(session.id)
        return self._view(session, result)

    def load(self, jid: str, stage: Stage | None = None) -> dict:
        with self.store.lock(jid):
            return self._view(self._get(jid), stage=stage)

    def read(self, jid: str, stage: Stage, operation: str, payload: dict | None = None) -> dict:
        with self.store.lock(jid):
            session = self._get(jid)
            if stage not in session.sessions:
                raise Conflict(f"no {stage} session")
            return self.tools[stage].read(session.sessions[stage], operation, payload or {})

    def preview(self, jid: str) -> dict:
        """The schedule the current Decision selection would get, built in the background without confirming it.
        Reads Decision under the journey lock, then builds outside it; nothing in the journey changes."""
        with self.store.lock(jid):
            session = self._get(jid)
            if session.stage != "decision":
                raise Conflict("preview needs the decision stage")
            draft = self.tools["decision"].read(session.sessions["decision"], "draft", {})["output"]
            revision = session.revision
        if draft is None:
            return {"revision": revision, "status": "blocked", "plan": None}
        if not draft["confirmed"]:
            return {"revision": revision, "status": "empty", "plan": None}
        plan = self.tools["planning"].preview({"decision_output": draft})
        return {"revision": revision, "status": "ready" if plan["ok"] else "failed", "plan": plan}

    def summaries(self, ids: list[str]) -> list[dict]:
        """One line per journey the browser remembers (no listing of other people's journeys); unknown IDs are skipped."""
        out = []
        for jid in ids[:20]:
            try:
                with self.store.lock(jid):
                    session = self._get(jid)
                    context = (session.outputs.get("trip") or {}).get("context") or {}
                    if "decision" in session.outputs:
                        places = [c["id"] for c in session.outputs["decision"].get("confirmed", [])]
                    elif "decision" in session.sessions:
                        view = self.tools["decision"].load(session.sessions["decision"]).get("view") or {}
                        places = list(view.get("selected") or [])
                    else:
                        places = []
            except KeyError:
                continue
            out.append({"id": session.id, "stage": session.stage, "revision": session.revision,
                        "start_date": context.get("start_date"), "days": context.get("days"),
                        "people": context.get("people"), "places": places,
                        "confirmed": "planning" in session.outputs})
        return out

    def feedback(self, jid: str, payload: dict) -> dict:
        """After-trip answers (1-5 scales, yes/no, a short note), one JSON line per submission next to the sessions."""
        if set(payload) - {"scores", "more_search", "note"}:
            raise ValueError("unknown feedback field")
        scores, more, note = payload.get("scores") or {}, payload.get("more_search"), payload.get("note") or ""
        if not isinstance(scores, dict) or len(scores) > 10 or any(
                not isinstance(k, str) or len(k) > 40 or not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 5
                for k, v in scores.items()):
            raise ValueError("scores must map up to 10 names to 1-5")
        if more is not None and not isinstance(more, bool):
            raise ValueError("more_search must be true, false or null")
        if not isinstance(note, str) or len(note) > 1000:
            raise ValueError("note must be at most 1000 characters")
        with self.store.lock(jid):
            self._get(jid)
        record = {"journey": jid, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "scores": scores,
                  "more_search": more, "note": note.strip()}
        self.store.append_feedback(record)
        return {"stored": True}

    def report(self, payload: dict) -> dict:
        return self.tools["decision"].report(payload)

    def places(self, query: str) -> list[dict]:
        return self.tools["trip"].places(query)

    def forget_profile(self, user_id: str) -> bool:
        return self.tools["trip"].forget(user_id)

    def request(self, jid: str, request: Request, emit: Emit | None = None) -> dict:
        with self.store.lock(jid):
            session = self._get(jid)
            fingerprint = _fingerprint(request)
            receipt = session.receipts.get(request.request_id)
            if receipt:
                if receipt["fingerprint"] != fingerprint:
                    raise Conflict("request_id was already used for another request")
                if emit:
                    for event in receipt["events"]:
                        emit(event["event"], event["data"])
                return receipt["response"]
            if request.expected_revision != session.revision:
                raise Conflict(f"expected revision {session.revision}, got {request.expected_revision}")
            stage = route(session.stage, request)
            before = session.model_copy(deep=True)
            events: list[dict] = []

            def capture(event: str, data: dict) -> None:
                events.append({"event": event, "data": data})
                if emit and event in ("say", "preview"):
                    emit(event, data)
                if stage == "trip" and event == "done" and "search_input" in data:
                    session.outputs["trip"] = SearchInput.model_validate(data["search_input"]).model_dump(mode="json")

            try:
                if request.operation == "advance":
                    result = self._advance(session)
                elif request.operation == "back":
                    session.stage = "decision" if stage == "planning" else "trip"
                    session.outputs.pop("planning", None)
                    session.outputs.pop("decision", None)
                    session.sessions.pop("planning", None)
                    session.snapshots.pop("planning", None)
                    if session.stage == "trip":
                        session.outputs.pop("trip", None)
                    result = self.tools[session.stage].load(session.sessions[session.stage])
                else:
                    result = self.tools[stage].apply(session.sessions[stage], request.operation, request.payload, capture)
                    if stage == "decision" and request.operation == "turn":
                        texts = [t for e in events if e["event"] == "trip" for t in e["data"]["texts"]]
                        events[:] = [e for e in events if e["event"] != "trip"]  # internal: the web never sees it
                        if texts and "trip" in session.sessions:
                            result = self._refine(session, " ".join(texts), events, capture) or result
                    if stage == "trip" and request.operation == "turn" and not any(e["event"] == "done" for e in events):
                        session.outputs.pop("trip", None)
                    if request.operation in ("act", "turn", "recommend") and stage != "trip":
                        session.outputs.pop("planning", None)
                        if stage == "decision":
                            session.outputs.pop("decision", None)
                            session.sessions.pop("planning", None)
                            session.snapshots.pop("planning", None)
                    if request.operation == "confirm":
                        session.outputs["planning"] = result
                session.revision += 1
                for name, sid in session.sessions.items():
                    session.snapshots[name] = self.tools[name].snapshot(sid)
                response = self._view(session, result)
                session.receipts[request.request_id] = {"fingerprint": fingerprint, "response": response, "events": events}
                self.store.save(session)
            except Exception:
                for name, snapshot in before.snapshots.items():
                    self.tools[name].restore(snapshot)
                raise
            if emit:
                for event in events:
                    if event["event"] not in ("say", "preview"):
                        emit(event["event"], event["data"])
            return response

    def _refine(self, session: Journey, text: str, events: list[dict], capture) -> dict | None:
        """A wish typed at Chọn nơi: Trip Understanding reads it, then Decision is rebuilt on the new Search Input.
        The rebuilt view replaces the turn's own, and Trip's reply follows Decision's in the same bubble."""
        said = _said(events)
        compiled: list[dict] = []
        reply = ""

        def on_trip(event: str, data: dict) -> None:
            nonlocal reply
            if event == "say":
                reply = data["replace"] if "replace" in data else reply + data.get("delta", "")
                capture("say", {"replace": f"{said} {reply}".strip()})
            elif event == "done":
                compiled.append(data["search_input"])

        self.tools["trip"].apply(session.sessions["trip"], "refine", {"text": text}, on_trip)
        if not compiled:
            return None
        session.outputs["trip"] = SearchInput.model_validate(compiled[-1]).model_dump(mode="json")
        out = self.tools["decision"].rebase(session.sessions["decision"],
                                            {"search_input": session.outputs["trip"], "trip_session": session.sessions["trip"]})
        rebuilt = {"view": out["view"], "diff": out["diff"]}
        views = [e for e in events if e["event"] == "view"]
        for e in views:
            e["data"] = rebuilt
        if not views:
            capture("view", rebuilt)
        return {"id": out["id"], "view": out["view"]}

    def _advance(self, session: Journey) -> dict:
        if session.stage == "trip":
            if "trip" not in session.outputs:
                raise Conflict("Trip Understanding has not compiled Search Input")
            payload = {"search_input": session.outputs["trip"], "trip_session": session.sessions["trip"]}
            existing = session.sessions.get("decision")
            result = self.tools["decision"].rebase(existing, payload) if existing else self.tools["decision"].create(payload)
            session.stage = "decision"
        else:
            output = self.tools["decision"].apply(session.sessions["decision"], "confirm", {}, lambda *args: None)
            session.outputs["decision"] = output
            result = self.tools["planning"].create({"decision_output": output})
            session.stage = "planning"
        session.sessions[session.stage] = result["id"]
        return result
