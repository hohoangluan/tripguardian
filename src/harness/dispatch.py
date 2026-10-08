"""In-process handoffs through public module tools; no hidden LLM supervisor."""

import hashlib
import json

from trip import SearchInput

from .contracts import Emit, Journey, JourneyView, ModuleTools, Request, Stage
from .router import route
from .session import Store


class Conflict(ValueError):
    pass


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
