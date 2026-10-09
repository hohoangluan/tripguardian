import copy

import pytest


class Tools:
    """Small stateful module adapter; no network or LLM required."""
    def __init__(self, stage):
        self.stage, self.states = stage, {}
        self.calls = 0

    def create(self, payload):
        sid = f"{len(self.states) + 1:012x}"
        self.states[sid] = {"id": sid, "value": 0, "input": copy.deepcopy(payload)}
        return self.load(sid)

    def load(self, sid):
        return {"id": sid, "view": copy.deepcopy(self.states[sid])}

    def _compiled(self, sid, emit):
        from trip import SearchInput
        from corpus.ontology import load
        search = SearchInput.model_validate({"ontology_version": load().version,
            "context": {"days": 2, "mobility": "motorbike", "start_date": None, "month": None,
                "base": None, "companions": [], "people": None, "arrive_at": None, "leave_at": None,
                "day_end": None}, "hard_filters": [], "anchors": [],
            "soft_weights": [], "pace": {"level": "normal", "max_leg_min": None, "crowd_tolerance": None},
            "novelty": {"level": None, "visited": []}, "unknowns": [], "unmapped": []})
        self.states[sid]["value"] += 1
        emit("done", {"search_input": search.model_dump(mode="json")})
        return self.load(sid)

    def apply(self, sid, operation, payload, emit):
        self.calls += 1
        if self.stage == "decision" and operation == "turn":
            emit("say", {"delta": "Mình hiểu rồi."})
            if "yên tĩnh" in payload.get("text", ""):
                emit("trip", {"texts": ["muốn yên tĩnh hơn"]})
            self.states[sid]["value"] += 1
            emit("view", {"view": self.load(sid)["view"], "diff": {"added": [], "removed": [], "text": "turn"}})
            emit("done", {})
            return self.load(sid)
        if self.stage == "trip" and operation == "refine":
            self.states[sid]["refined"] = payload["text"]
            emit("say", {"delta": "Mình ưu tiên chỗ yên tĩnh."})
            return self._compiled(sid, emit)
        if operation == "turn":
            return self._compiled(sid, emit)
        elif operation == "confirm":
            return {"confirmed": [{"id": "place-1"}], "value": self.states[sid]["value"]}
        elif operation == "act" and payload.get("place") == "not-in-backups":
            raise ValueError("'not-in-backups' is not in the backup pool")
        else:
            self.states[sid]["value"] += 1
        return self.load(sid)

    def rebase(self, sid, payload):
        self.states[sid]["rebased"] = payload["search_input"]["context"]["days"]
        return {**self.load(sid), "diff": {"added": [], "removed": [], "text": "Giữ 22 nơi, thay 2 nơi hợp hơn"}}

    def read(self, sid, operation, payload):
        return {"operation": operation, "payload": payload}

    def snapshot(self, sid):
        return copy.deepcopy(self.states[sid])

    def restore(self, snapshot):
        self.states[snapshot["id"]] = copy.deepcopy(snapshot)

    def report(self, payload):
        if not payload.get("text"):
            raise ValueError("text must be 1-1000 characters")
        return {"id": "r1", "stored": True}

    def places(self, query):
        return [{"id": "place-1", "name": query}]

    def forget(self, user_id):
        return user_id == "user-abc-123"

    def geo(self, q):
        return [{"text": q, "address": "", "province": "Hồ Chí Minh", "lat": 10.77, "lng": 106.7,
                 "source": "photon", "fetched_at": "2026-10-08T00:00:00+00:00"}]

    def lodging_suggest(self, q):
        return [{"kind": "address", "text": q, "address": "", "lat": 11.94, "lng": 108.45}]

    def transit(self, params):
        if params.get("mode") not in ("plane", "bus"):
            raise ValueError("mode must be plane or bus")
        self.calls += 1  # pending on the first two polls, then the crawl "lands"
        ready = self.calls > 2
        return {"status": "ready" if ready else "pending", "book_url": "https://book",
                "trips": [{"mode": "plane", "carrier": "Vietjet"}] if ready else []}


def file_store(root):
    from harness import Store
    return Store(root)


STORE = file_store  # conftest swaps in a PgStore for the pg run of every harness test


def make(root=None):
    from harness import Harness
    tools = {s: Tools(s) for s in ("trip", "decision", "planning")}
    return Harness(tools["trip"], tools["decision"], tools["planning"], STORE(root)), tools


def run(h, view, operation, request_id="request-1", payload=None):
    from harness import Request
    return h.request(view["id"], Request(request_id=request_id, stage=view["stage"], operation=operation,
        expected_revision=view["revision"], payload=payload or {}))


def decision(h):
    v = h.create()
    v = run(h, v, "turn", "trip-turn", {"kind": "show"})
    return run(h, v, "advance", "to-decision")


def test_handoffs_preserve_the_same_journey_and_decision_state():
    h, _ = make()
    v = decision(h)
    jid, did = v["id"], v["sessions"]["decision"]
    v = run(h, v, "act", "select")
    v = run(h, v, "advance", "to-planning")
    assert v["stage"] == "planning" and v["id"] == jid
    assert v["outputs"]["decision"]["value"] == 1
    v = run(h, v, "back", "more-places")
    assert v["stage"] == "decision" and v["sessions"]["decision"] == did
    assert v["result"]["view"]["value"] == 1
    assert "planning" not in v["outputs"]


def test_request_retry_does_not_apply_twice_and_payload_reuse_is_refused():
    from harness import Conflict, Request
    h, tools = make()
    v = decision(h)
    req = Request(request_id="select", stage="decision", operation="act", expected_revision=v["revision"],
        payload={"type": "select", "place": "place-1"})
    out = h.request(v["id"], req)
    assert h.request(v["id"], req) == out
    assert tools["decision"].calls == 1
    with pytest.raises(Conflict):
        h.request(v["id"], req.model_copy(update={"payload": {"type": "drop"}}))


def test_stale_revision_does_not_change_state():
    from harness import Conflict
    h, tools = make()
    v = decision(h)
    run(h, v, "act", "select")
    with pytest.raises(Conflict):
        run(h, v, "act", "stale")
    assert tools["decision"].calls == 1


def test_restart_restores_modules_and_receipts_from_one_committed_snapshot(tmp_path):
    h, _ = make(tmp_path)
    v = decision(h)
    old = copy.deepcopy(v)
    out = run(h, v, "act", "select")
    restored, tools = make(tmp_path)
    assert restored.load(out["id"])["result"]["view"]["value"] == 1
    assert run(restored, old, "act", "select") == out
    assert tools["decision"].calls == 0


def test_failed_harness_save_rolls_back_module_mutation(tmp_path, monkeypatch):
    h, tools = make(tmp_path)
    v = decision(h)
    def fail_save(session):
        raise OSError("disk full")
    with monkeypatch.context() as m:
        m.setattr(h.store, "save", fail_save)
        with pytest.raises(OSError):
            run(h, v, "act", "select")
    assert h.load(v["id"])["revision"] == v["revision"]
    assert tools["decision"].load(v["sessions"]["decision"])["view"]["value"] == 0
    assert run(h, v, "act", "select")["result"]["view"]["value"] == 1


def test_advance_requires_a_compiled_search_input():
    from harness import Conflict
    h, _ = make()
    with pytest.raises(Conflict):
        run(h, h.create(), "advance")


def test_planning_edits_keep_the_confirmed_decision_input():
    h, _ = make()
    view = run(h, decision(h), "advance", "to-planning")
    output = copy.deepcopy(view["outputs"]["decision"])
    view = run(h, view, "recommend", "suggest-layout")
    assert view["outputs"]["decision"] == output


def preview_tools(tools, draft):
    tools["decision"].read = lambda sid, op, payload: {"output": draft}
    tools["planning"].preview = lambda payload: {"ok": True, "days": 2, "variants": [],
                                                 "input": payload["decision_output"]}


def test_preview_builds_a_plan_for_the_current_selection_without_changing_the_journey():
    h, tools = make()
    v = decision(h)
    preview_tools(tools, {"confirmed": [{"id": "place-1"}]})
    out = h.preview(v["id"])
    assert out["status"] == "ready" and out["revision"] == v["revision"]
    assert out["plan"]["input"] == {"confirmed": [{"id": "place-1"}]}
    after = h.load(v["id"])
    assert (after["revision"], after["outputs"], after["sessions"]) == (v["revision"], v["outputs"], v["sessions"])
    assert tools["decision"].calls == 0


def test_preview_says_blocked_or_empty_and_needs_the_decision_stage():
    from harness import Conflict
    h, tools = make()
    with pytest.raises(Conflict):
        h.preview(h.create()["id"])
    v = decision(h)
    preview_tools(tools, None)
    assert h.preview(v["id"]) == {"revision": v["revision"], "status": "blocked", "plan": None}
    preview_tools(tools, {"confirmed": []})
    assert h.preview(v["id"])["status"] == "empty"


def test_summaries_list_only_the_asked_journeys_with_their_places():
    h, _ = make()
    v = run(h, decision(h), "advance", "to-planning")
    other = h.create()
    out = h.summaries([v["id"], "000000000000", "../bad", other["id"]])
    assert [s["id"] for s in out] == [v["id"], other["id"]]
    assert out[0]["stage"] == "planning" and out[0]["days"] == 2 and out[0]["places"] == ["place-1"]
    assert out[1]["places"] == [] and out[1]["days"] is None and not out[1]["confirmed"]


def test_feedback_is_validated_and_appended_beside_the_sessions(tmp_path, store_kind):
    if store_kind == "pg":
        pytest.skip("file layout only; tests/harness/test_pgstore.py covers the feedback table")
    import json
    h, _ = make(tmp_path / "sessions")
    v = h.create()
    assert h.feedback(v["id"], {"scores": {"fit": 4}, "more_search": False, "note": " ok "}) == {"stored": True}
    lines = (tmp_path / "feedback.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["scores"] == {"fit": 4} and json.loads(lines[0])["note"] == "ok"
    for bad in ({"scores": {"fit": 6}}, {"scores": {"fit": True}}, {"other": 1}, {"note": "x" * 1001}):
        with pytest.raises(ValueError):
            h.feedback(v["id"], bad)
    with pytest.raises(KeyError):
        h.feedback("000000000000", {})


def test_decision_turn_with_a_trip_wish_refines_trip_then_rebases_decision():
    h, tools = make()
    v = decision(h)
    out = run(h, v, "turn", "chat-1", {"text": "muốn yên tĩnh hơn"})
    j = h.load(out["id"])
    trip_sid, dec_sid = h._get(out["id"]).sessions["trip"], h._get(out["id"]).sessions["decision"]
    assert tools["trip"].states[trip_sid]["refined"] == "muốn yên tĩnh hơn"
    assert tools["decision"].states[dec_sid]["rebased"] == 2
    assert out["stage"] == "decision" and j["revision"] == out["revision"]


def test_decision_turn_without_a_trip_wish_never_touches_trip():
    h, tools = make()
    v = decision(h)
    before = tools["trip"].calls
    run(h, v, "turn", "chat-2", {"text": "bỏ quán số 2"})
    assert tools["trip"].calls == before


def test_a_refined_turn_streams_one_rebuilt_view_and_one_reply():
    from harness import Request
    h, _ = make()
    v = decision(h)
    events = []
    h.request(v["id"], Request(request_id="chat-3", stage="decision", operation="turn",
                               expected_revision=v["revision"], payload={"text": "muốn yên tĩnh hơn"}),
              lambda e, d: events.append((e, d)))
    names = [e for e, _ in events]
    assert "trip" not in names and names.count("view") == 1 and names[-1] == "done"
    assert dict(events)["view"]["diff"]["text"] == "Giữ 22 nơi, thay 2 nơi hợp hơn"
    assert [d for e, d in events if e == "say"][-1] == {
        "replace": "Mình hiểu rồi. Mình ưu tiên chỗ yên tĩnh. Giữ 22 nơi, thay 2 nơi hợp hơn."}


def test_a_trip_wish_without_a_trip_session_still_finishes_the_turn():
    h, tools = make()
    v = decision(h)
    j = h._get(v["id"])
    j.sessions.pop("trip")
    j.snapshots.pop("trip")
    h.store.save(j)
    out = run(h, v, "turn", "chat-4", {"text": "muốn yên tĩnh hơn"})
    assert out["stage"] == "decision" and "rebased" not in tools["decision"].states[j.sessions["decision"]]
