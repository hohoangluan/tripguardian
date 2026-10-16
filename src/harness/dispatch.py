"""In-process handoffs through public module tools; no hidden LLM supervisor."""

import hashlib
import json
import sys
import time
import uuid
import threading
from datetime import datetime, timezone

from trip import SearchInput, TurnInput
from planning import TripIncomplete
from corpus.releases import Binding

from .contracts import Conflict, Emit, Journey, JourneyView, ModuleTools, Request, Stage, TripNotReady
from .router import route, route_companion
from .session import Store
from .chat_guard import admit


def _said(events: list[dict]) -> str:
    """The reply streamed so far through say events (deltas, or a replace)."""
    out = ""
    for e in events:
        if e["event"] == "say":
            out = e["data"]["replace"] if "replace" in e["data"] else out + e["data"].get("delta", "")
    return out


def _page(query: dict) -> tuple[int, int | None]:
    """(offset, limit) of a paged read (`?offset=&limit=`, both optional); limit is 1-60."""
    offset, limit = str(query.get("offset", "0")), query.get("limit")
    if not offset.isdigit() or len(offset) > 6 or (limit is not None and (not str(limit).isdigit() or not 1 <= int(limit) <= 60)):
        raise ValueError("offset must be a number, limit 1-60")
    return int(offset), int(limit) if limit is not None else None


LIVE = ("say", "preview", "progress", "state", "card", "deck_issues", "readback")


def _fingerprint(request: Request) -> str:
    raw = json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()



CHAT_TITLE_MAX = 60


def chat_title(transcript: list) -> str | None:
    """The chat's one-line title for the history list: what the user said first (its first line, cut at
    CHAT_TITLE_MAX). A list file attached to that message is part of its text, so only the first line is read.
    None while the user has said nothing yet."""
    for turn in transcript:
        if not isinstance(turn, dict) or turn.get("role") != "user":
            continue
        lines = [ln.strip() for ln in str(turn.get("text") or "").splitlines() if ln.strip()]
        if not lines:
            continue
        line = " ".join(lines[0].split())
        return line if len(line) <= CHAT_TITLE_MAX else line[:CHAT_TITLE_MAX - 1].rstrip() + "…"
    return None


class Harness:
    def __init__(self, trip_tools: ModuleTools, decision_tools: ModuleTools, planning_tools: ModuleTools, store: Store,
                 events=None, companion=None, calendar=None, notify=None, safety=None,
                 corpus_binding: Binding | None = None, tools_for_binding=None):
        """events: harness.events.EventLog (usage events in Postgres); companion: companion.Companion (Đang đi).
        None turns either off (CLI, most tests)."""
        self.tools = {"trip": trip_tools, "decision": decision_tools, "planning": planning_tools}
        self.store = store
        self.events = events
        self.companion = companion
        self.calendar = calendar
        self.notify = notify
        self.safety = safety
        self.corpus_binding = corpus_binding
        self.tools_for_binding = tools_for_binding
        self._corpus_tools = {self._binding_key(corpus_binding): self.tools}
        self._corpus_lock = threading.RLock()
        self._loaded: set[str] = set()

    @staticmethod
    def _binding_key(binding: Binding | None) -> str:
        return binding.model_dump_json() if binding is not None else "legacy"

    def _module(self, session: Journey, stage: Stage) -> ModuleTools:
        key = self._binding_key(session.corpus_binding)
        with self._corpus_lock:
            if key not in self._corpus_tools:
                if self.tools_for_binding is None:
                    raise Conflict("corpus binding unavailable; restore the pinned release before continuing")
                self._corpus_tools[key] = self.tools_for_binding(session.corpus_binding)
            return self._corpus_tools[key][stage]

    @staticmethod
    def _bound_output(session: Journey, output: dict) -> dict:
        if session.corpus_binding is None:
            return output
        existing = output.get("corpus_binding")
        binding = session.corpus_binding.model_dump(mode="json")
        if existing is not None and existing != binding:
            raise Conflict("module output uses a different corpus binding")
        return {**output, "corpus_binding": binding}

    def _event(self, name: str, owner: str | None, jid: str | None, **props) -> None:
        if self.events is not None:
            self.events.server(name, owner, jid, **props)

    def _get(self, jid: str, owner: str | None = None) -> Journey:
        """owner None is the in-process caller (CLI, tests); the HTTP server always names the signed-in account,
        and another account's journey is reported as missing."""
        session = self.store.get(jid)
        if owner is not None and session.user_id != owner:
            raise KeyError(jid)
        if jid not in self._loaded:
            for stage, snapshot in session.snapshots.items():
                self._module(session, stage).restore(snapshot)
            self._loaded.add(jid)
        return session

    def _view(self, session: Journey, result: dict | None = None, stage: Stage | None = None) -> dict:
        shown = stage or session.stage
        if shown not in session.sessions:
            raise Conflict(f"no {shown} session")
        return JourneyView(id=session.id, stage=session.stage, revision=session.revision,
                sessions=session.sessions, outputs=session.outputs,
                result=result if result is not None else self._module(session, shown).load(session.sessions[shown])).model_dump(mode="json")

    def create(self, experience=None, start_with=None, user_id=None, remember=False, owner=None, profile=None) -> dict:
        """profile: the account's usual mobility / companions, a prior for Trip (never a fact of this trip)."""
        session = self.store.new()
        session.user_id = owner
        session.corpus_binding = self.corpus_binding
        payload = {"experience": experience, "start_with": start_with, "user_id": user_id, "remember": remember}
        if profile:
            payload["profile"] = profile
        result = self._module(session, "trip").create(payload)
        session.sessions["trip"] = result["id"]
        session.snapshots["trip"] = self._module(session, "trip").snapshot(result["id"])
        self.store.save(session)
        self._loaded.add(session.id)
        self._event("journey.create", owner, session.id, start_with=start_with, experience=experience,
                    profile_prior=bool(profile))
        return self._view(session, result)

    def load(self, jid: str, stage: Stage | None = None, owner: str | None = None) -> dict:
        with self.store.lock(jid):
            return self._view(self._get(jid, owner), stage=stage)

    def read(self, jid: str, stage: Stage, operation: str, payload: dict | None = None, owner: str | None = None) -> dict:
        if stage == "decision" and operation == "lodging":
            return self.lodging(jid, owner, *_page(payload or {}))
        with self.store.lock(jid):
            session = self._get(jid, owner)
            if stage not in session.sessions:
                raise Conflict(f"no {stage} session")
            out = self._module(session, stage).read(session.sessions[stage], operation, payload or {})
            if operation in {"suggestions", "preview-act"} and stage == "planning":
                out = {**out, "revision": session.revision}
        if operation == "why-not":
            self._event("why_not", owner, jid, place_id=(payload or {}).get("place"))
        elif operation == "page":
            self._event("page_more", owner, jid, group=(payload or {}).get("group"), page=(payload or {}).get("n"))
        return out

    def preview(self, jid: str, owner: str | None = None) -> dict:
        """The schedule the current Decision selection would get, built in the background without confirming it.
        Reads Decision under the journey lock, then builds outside it; nothing in the journey changes."""
        with self.store.lock(jid):
            session = self._get(jid, owner)
            if session.stage != "decision":
                raise Conflict("preview needs the decision stage")
            draft = self._module(session, "decision").read(session.sessions["decision"], "draft", {})["output"]
            revision = session.revision
        if draft is None:
            out = {"revision": revision, "status": "blocked", "plan": None}
        elif not draft["confirmed"]:
            out = {"revision": revision, "status": "empty", "plan": None}
        else:
            plan = self._module(session, "planning").preview({"decision_output": self._bound_output(session, draft)})
            out = {"revision": revision, "status": "ready" if plan["ok"] else "failed", "plan": plan}
        self._event(f"preview.{out['status']}", owner, jid, revision=revision)
        return out

    def lodging(self, jid: str, owner: str | None = None, offset: int = 0, limit: int | None = None) -> dict:
        """Lựa chọn's lodging list, one page: every served stay, those around the places chosen so far first
        (Planning ranks them), read under the journey lock and built outside it; nothing in the journey changes. A
        selection that cannot be confirmed yet, or no place chosen at all, still gets its list: where to sleep does not
        wait for the plan to fit."""
        with self.store.lock(jid):
            session = self._get(jid, owner)
            if session.stage not in ("decision", "planning"):  # read only: Lựa chọn reopened from Lịch trình lists it too
                raise Conflict("lodging list needs the decision stage")
            draft = self._module(session, "decision").read(session.sessions["decision"], "draft", {"any": True})["output"]
        if draft is None:
            return {"status": "empty", "candidates": [], "total": 0}
        return self._module(session, "planning").lodging_options({"decision_output": self._bound_output(session, draft)}, offset, limit)

    def trips(self, owner: str) -> list[dict]:
        """One line per journey of the signed-in account, newest first. All of them: the profile counts these."""
        return self.summaries(self.store.list_for(owner, limit=1000), limit=None)

    def summaries(self, ids: list[str], limit: int | None = 20) -> list[dict]:
        """One line per asked journey (the first `limit`, all when None); unknown IDs are skipped."""
        out = []
        for jid in ids[:limit]:
            try:
                with self.store.lock(jid):
                    try:
                        session = self._get(jid)
                    except KeyError:
                        raise
                    except Exception:  # a journey an older build saved cannot be restored: it stays in the list,
                        session = self.store.get(jid)  # read from its saved copy (opening it reports its own error)
                    context = (session.outputs.get("trip") or {}).get("context") or {}
                    if "decision" in session.outputs:
                        places = [c["id"] for c in session.outputs["decision"].get("confirmed", [])]
                    elif "decision" in session.sessions:
                        try:
                            view = self._module(session, "decision").load(session.sessions["decision"]).get("view") or {}
                        except Exception:
                            view = {}
                        places = list(view.get("selected") or [])
                    else:
                        places = []
            except KeyError:
                continue
            out.append({"id": session.id, "stage": session.stage, "revision": session.revision,
                        "start_date": context.get("start_date"), "days": context.get("days"),
                        "people": context.get("people"), "places": places,
                        "confirmed": "planning" in session.outputs,
                        "title": chat_title((session.snapshots.get("trip") or {}).get("transcript") or [])})
        return out

    def discard(self, jid: str, owner: str) -> None:
        """The account removes one of its journeys: it leaves the account (and the list) at once and cannot be opened
        again; like a deleted account's trips, the usage numbers stay without a user. A schedule already on
        Đang đi goes with it."""
        with self.store.lock(jid):
            session = self._get(jid, owner)
            session.user_id = None
            self.store.save(session)
        if self.companion is not None:
            self.companion.forget(jid)
        self._event("journey.discard", owner, jid, stage=session.stage)

    def owns(self, jid: str, owner: str) -> bool:
        try:
            with self.store.lock(jid):
                self._get(jid, owner)
        except KeyError:
            return False
        return True

    def copy(self, jid: str, source_owner: str, owner: str) -> dict:
        """A new journey of `owner` with the trip, choices and schedule of another account's journey (a trip a friend
        sent). Module sessions get fresh IDs so the two never share state; the chat transcript and the source
        account's pattern link stay behind."""
        with self.store.lock(jid):
            source = self._get(jid, source_owner)
            raw = json.dumps({"sessions": source.sessions, "outputs": source.outputs, "snapshots": source.snapshots})
        for old in set(source.sessions.values()):
            raw = raw.replace(old, uuid.uuid4().hex[:12])
        data = json.loads(raw)
        trip = data["snapshots"].get("trip") or {}
        if "transcript" in trip:
            trip["transcript"] = []
        if meta := (trip.get("state") or {}).get("meta"):
            meta |= {"user_id": None, "remember": False}
        session = self.store.new()
        session.user_id, session.stage, session.revision = owner, source.stage, source.revision
        session.corpus_binding = source.corpus_binding
        session.sessions, session.outputs, session.snapshots = data["sessions"], data["outputs"], data["snapshots"]
        for stage, snapshot in session.snapshots.items():
            self._module(session, stage).restore(snapshot)
        self.store.save(session)
        self._loaded.add(session.id)
        self._event("journey.copy", owner, session.id, source=jid)
        return {"id": session.id, "stage": session.stage, "revision": session.revision}

    def feedback(self, jid: str, payload: dict, owner: str | None = None) -> dict:
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
            self._get(jid, owner)
        record = {"journey": jid, "user_id": owner, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "scores": scores,
                  "more_search": more, "note": note.strip()}
        self.store.append_feedback(record)
        self._event("feedback.submit", owner, jid, scores=",".join(f"{k}:{v}" for k, v in sorted(scores.items())),
                    more_search=more, has_note=bool(record["note"]))
        return {"stored": True}

    def report(self, payload: dict) -> dict:
        return self.tools["decision"].report(payload)

    def places(self, query: str, owner: str | None = None) -> list[dict]:
        hits = self.tools["trip"].places(query)
        if query.strip():
            self._event("places.search", owner, None, q=query.strip()[:80], hits=len(hits))
        return hits

    def geo(self, q: str) -> list[dict]:
        """Search-as-you-type for a starting point; Planning owns Live Context (docs/PLANNING.md §Live Context)."""
        return self.tools["planning"].geo(q)

    def lodging_suggest(self, q: str) -> list[dict]:
        return self.tools["planning"].lodging_suggest(q)

    def forget_profile(self, user_id: str) -> bool:
        return self.tools["trip"].forget(user_id)

    def adopt(self, from_id: str, to_id: str) -> int:
        """A guest signed in with Google: their journeys now belong to the account. Returns how many moved."""
        moved = 0
        for jid in self.store.list_for(from_id):
            with self.store.lock(jid):
                session = self.store.get(jid)
                session.user_id = to_id
                self.store.save(session)
            moved += 1
        return moved

    def request(self, jid: str, request: Request, emit: Emit | None = None, owner: str | None = None) -> dict:
        started = time.monotonic()
        trace: dict = {"t0": started}
        name = f"{request.stage}.{request.operation}"
        if request.operation == "act" and isinstance(request.payload.get("type"), str):
            name += "." + request.payload["type"][:40]
        try:
            response = self._request(jid, request, emit, owner, trace)
        except Exception as exc:
            if not isinstance(exc, KeyError):
                self._event(name, trace.get("user_id"), jid, revision=request.expected_revision, error=type(exc).__name__,
                            latency_ms=round((time.monotonic() - started) * 1000), path=trace.get("path"))
            raise
        if not trace.get("replayed") and name == "planning.confirm" and self.companion is not None:
            self._sync_trip(jid)
        if not trace.get("replayed"):
            props = self.events.act_props(request.payload) if self.events and request.operation == "act" else {}
            if request.stage == "trip" and request.operation == "turn":
                chips = request.payload.get("chips") or []
                props |= {"kind": request.payload.get("kind"), "qid": request.payload.get("qid") or None,
                          "exit": next((c for c in ("skip", "unsure") if c in chips), None)}
            if name == "planning.confirm" and self.companion is not None:
                props |= self._quality(jid)
            self._event(name, trace.get("user_id"), jid, revision=response["revision"], path=trace.get("path"),
                        latency_ms=round((time.monotonic() - started) * 1000), first_ms=trace.get("first_ms"),
                        refined=trace.get("refined"),
                        compiled=True if trace.get("compiled") else None, **props)
        return response

    # --- Đang đi (companion) ------------------------------------------------------------------------------------

    def _sync_trip(self, jid: str) -> None:
        """The confirmed plan becomes (or updates) the trip; a failure is logged and leaves the confirm committed."""
        try:
            session = self.store.get(jid)
            self.companion.sync(jid, session.user_id, session.outputs["planning"])
        except Exception as exc:
            print(f"trip not synced for {jid}: {type(exc).__name__}: {exc}", file=sys.stderr)

    def _confirmed(self, jid: str, owner: str | None, operation: str = "checkin") -> Journey:
        if self.companion is None:
            raise Conflict("companion is off")
        with self.store.lock(jid):
            session = self._get(jid, owner)
        route_companion(session.outputs, operation)
        return session

    def _quality(self, jid: str) -> dict:
        """Event props for a confirmed plan (Admin tab Chất lượng): hard filters failed / unknown on its places, and
        the plan's robustness. A failure here only loses the props."""
        try:
            session = self.store.get(jid)
            plan, si = session.outputs["planning"], session.outputs.get("trip") or {}
            return {**self.companion.quality(plan, si), "robustness": (plan.get("robustness") or {}).get("level")}
        except Exception as exc:
            print(f"plan quality not measured for {jid}: {exc}", file=sys.stderr)
            return {}

    def today(self, jid: str, owner: str | None = None, day: int | None = None) -> dict:
        session = self._confirmed(jid, owner)
        plan = session.outputs["planning"]
        try:
            return self.companion.today(jid, plan, day)
        except KeyError:  # confirmed before trips existed
            self.companion.sync(jid, session.user_id, plan)
            return self.companion.today(jid, plan, day)

    def suggest(self, jid: str, place_id: str, owner: str | None = None, similar: bool = False) -> dict:
        session = self._confirmed(jid, owner)
        dropped = ((session.snapshots.get("decision") or {}).get("state") or {}).get("dropped") or []
        disliked = {d.get("place_id") for d in dropped if d.get("reason") == "dislike"}
        out = self.companion.suggestions(jid, session.outputs.get("trip") or {}, session.outputs["planning"], place_id,
                                         disliked, similar)
        backups = {b.get("id") for b in (session.outputs.get("decision") or {}).get("backup_pool") or []}
        for item in out.get("nearby", []) + out.get("similar", []):
            item["addable"] = item["place_id"] in backups  # Planning only adds from the backup pool
        return out

    def companion_act(self, jid: str, operation: str, payload: dict, owner: str | None = None) -> dict:
        """checkin / skip / rate write the trip; add / adjust change the plan through Planning (act, then confirm)
        and only with confirmed: true, i.e. after the user saw what changes."""
        session = self._confirmed(jid, owner, operation)
        uid = session.user_id
        if operation == "checkin":
            out = self.companion.checkin(jid, payload.get("stop_id"), payload.get("place_id"))
        elif operation == "skip":
            out = self.companion.skip(jid, payload.get("stop_id"), payload.get("reason"))
        elif operation == "rate":
            out = self.companion.rate(jid, payload.get("stop_id"), payload.get("value"))
        else:
            if payload.get("confirmed") is not True:
                raise ValueError(f"{operation} changes the plan: show the change, then send confirmed: true")
            if operation == "adjust":
                action = self.companion.option(jid, session.outputs["planning"], payload.get("option_id"))
            else:
                day = payload.get("day")
                if not isinstance(day, int) or isinstance(day, bool):
                    raise ValueError("day must be the trip day (1, 2, …)")
                action = {"type": "add_from_backup", "place": payload.get("place_id"), "day": day - 1}
            self._replan(jid, action, owner)
            out = {"changed": True, "today": self.today(jid, owner)}
        self._event(f"companion.{operation}", uid, jid, **{k: payload[k] for k in ("reason", "value", "option_id", "place_id")
                                                           if k in payload and not isinstance(payload[k], (dict, list))})
        return out

    def calendar_preview(self, jid: str, owner: str) -> dict:
        self.today(jid, owner)  # makes sure the trip rows exist
        session = self._confirmed(jid, owner)
        return self.calendar.preview(jid, owner, session.outputs["planning"])

    def calendar_apply(self, jid: str, preview_hash: str, owner: str) -> dict:
        session = self._confirmed(jid, owner)
        if not isinstance(preview_hash, str):
            raise ValueError("preview_hash is required")
        out = self.calendar.apply(jid, owner, session.outputs["planning"], preview_hash)
        if not out["stale"]:
            self._event("calendar.apply", owner, jid, applied=out["applied"], failed=out["failed"] is not None)
        return out

    def calendar_disconnect(self, owner: str, delete_calendar: bool) -> dict:
        if not isinstance(delete_calendar, bool):
            raise ValueError("delete_calendar must be true or false")
        out = self.calendar.disconnect(owner, delete_calendar)
        self._event("calendar.disconnect", owner, None, deleted=delete_calendar)
        return out

    def _replan(self, jid: str, action: dict, owner: str | None) -> None:
        """Planning act + confirm as two journey requests; when the confirm fails the act is undone and confirmed
        again, so the journey keeps a confirmed plan."""
        def send(operation, payload=None):
            view = self.load(jid, None, owner)
            if view["stage"] != "planning":
                raise Conflict("the plan is being edited elsewhere")
            return self.request(jid, Request(request_id=f"companion-{uuid.uuid4().hex}", stage="planning",
                                             operation=operation, expected_revision=view["revision"],
                                             payload=payload or {}), None, owner)
        send("act", action)
        try:
            send("confirm")
        except Exception:
            send("act", {"type": "undo"})
            send("confirm")
            raise

    def _request(self, jid: str, request: Request, emit: Emit | None, owner: str | None, trace: dict) -> dict:
        with self.store.lock(jid):
            session = self._get(jid, owner)
            trace["user_id"] = session.user_id
            fingerprint = _fingerprint(request)
            receipt = session.receipts.get(request.request_id)
            if receipt:
                if receipt["fingerprint"] != fingerprint:
                    raise Conflict("request_id was already used for another request")
                if emit:
                    for event in receipt["events"]:
                        emit(event["event"], event["data"])
                trace["replayed"] = True
                return receipt["response"]
            if request.expected_revision != session.revision:
                raise Conflict(f"expected revision {session.revision}, got {request.expected_revision}")
            stage = route(session.stage, request)
            before = session.model_copy(deep=True)
            events: list[dict] = []

            had_trip = "trip" in session.outputs

            def capture(event: str, data: dict) -> None:
                if event == "trace":  # internal: how the module answered (agent, fallback, heuristic), for events
                    trace.update(data)
                    return
                if "first_ms" not in trace and event in ("say", "preview", "view"):  # time to the first SSE event
                    trace["first_ms"] = round((time.monotonic() - trace["t0"]) * 1000)
                events.append({"event": event, "data": data})
                if emit and event in LIVE:
                    emit(event, data)
                if stage == "trip" and event == "done" and "search_input" in data:
                    session.outputs["trip"] = SearchInput.model_validate(self._bound_output(session, data["search_input"])).model_dump(mode="json")

            try:
                refusal = None
                if self.safety is not None and request.operation in {"turn", "act"}:
                    current = self._module(session, stage).load(session.sessions[stage])
                    refusal = admit(self.safety, request.payload, current, stage, review_text=request.operation == "turn")
                if refusal:
                    trace["path"] = "chat_refused"
                    capture("say", {"replace": refusal})
                    capture("done", {})
                    result = self._module(session, stage).load(session.sessions[stage])
                elif request.operation == "advance":
                    result = self._advance(session)
                elif request.operation == "trip":
                    inp = TurnInput.model_validate(request.payload)
                    if inp.kind not in {"deck", "drop", "readback_ok"}:
                        raise ValueError("decision.trip accepts only deck, drop or readback_ok")
                    trip = self._module(session, "trip")
                    trip.apply(session.sessions["trip"], "turn", request.payload, capture)
                    output = trip.read(session.sessions["trip"], "search_input", {})
                    session.outputs["trip"] = SearchInput.model_validate(self._bound_output(session, output)).model_dump(mode="json")
                    rebased = self._module(session, "decision").rebase(session.sessions["decision"],
                        {"search_input": session.outputs["trip"], "trip_session": session.sessions["trip"]})
                    result = {"id": rebased["id"], "view": rebased["view"]}
                    for key in ("decision", "planning"):
                        session.outputs.pop(key, None)
                    session.sessions.pop("planning", None)
                    session.snapshots.pop("planning", None)
                elif request.operation == "back":
                    session.stage = "decision" if stage == "planning" else "trip"
                    session.outputs.pop("planning", None)
                    session.outputs.pop("decision", None)
                    session.sessions.pop("planning", None)
                    session.snapshots.pop("planning", None)
                    if session.stage == "trip":
                        session.outputs.pop("trip", None)
                    result = self._module(session, session.stage).load(session.sessions[session.stage])
                else:
                    result = self._module(session, stage).apply(session.sessions[stage], request.operation, request.payload, capture)
                    if stage == "decision" and request.operation == "turn":
                        texts = [t for e in events if e["event"] == "trip" for t in e["data"]["texts"]]
                        events[:] = [e for e in events if e["event"] != "trip"]  # internal: the web never sees it
                        if texts and "trip" in session.sessions:
                            trace["refined"] = True
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
                        result = self._bound_output(session, result)
                        session.outputs["planning"] = result
                trace["compiled"] = stage == "trip" and not had_trip and "trip" in session.outputs
                session.revision += 1
                for name, sid in session.sessions.items():
                    session.snapshots[name] = self._module(session, name).snapshot(sid)
                response = self._view(session, result)
                session.receipts[request.request_id] = {"fingerprint": fingerprint, "response": response, "events": events,
                                                        "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                self.store.save(session)
            except Exception:
                for name, snapshot in before.snapshots.items():
                    self._module(session, name).restore(snapshot)
                raise
            if emit:
                for event in events:
                    if event["event"] not in LIVE:
                        emit(event["event"], event["data"])
            return response

    def _refine(self, session: Journey, text: str, events: list[dict], capture) -> dict | None:
        """A wish typed at Chọn nơi: Trip Understanding reads it, then Decision is rebuilt on the new Search Input.
        The rebuilt view replaces the turn's own; Trip's reply and the list change follow Decision's in the same bubble."""
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

        self._module(session, "trip").apply(session.sessions["trip"], "refine", {"text": text}, on_trip)
        if not compiled:
            return None
        session.outputs["trip"] = SearchInput.model_validate(self._bound_output(session, compiled[-1])).model_dump(mode="json")
        out = self._module(session, "decision").rebase(session.sessions["decision"],
                                            {"search_input": session.outputs["trip"], "trip_session": session.sessions["trip"]})
        rebuilt = {"view": out["view"], "diff": out["diff"]}
        if note := out["diff"].get("text"):  # the reply ends with what happened to the list: "Giữ 22 nơi, thay 2 …"
            capture("say", {"replace": f"{said} {reply} {note}.".replace("  ", " ").strip()})
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
            result = self._module(session, "decision").rebase(existing, payload) if existing else self._module(session, "decision").create(payload)
            session.stage = "decision"
        else:
            output = self._module(session, "decision").apply(session.sessions["decision"], "confirm", {}, lambda *args: None)
            output = self._bound_output(session, output)
            try:
                result = self._module(session, "planning").create({"decision_output": output})
            except TripIncomplete as exc:
                readback = self._module(session, "trip").read(session.sessions["trip"], "readback", {})
                raise TripNotReady(exc.missing, readback) from exc
            session.outputs["decision"] = output
            session.stage = "planning"
        session.sessions[session.stage] = result["id"]
        return result
