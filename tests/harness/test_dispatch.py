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

    def apply(self, sid, operation, payload, emit):
        self.calls += 1
        if operation == "turn":
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
        elif operation == "confirm":
            return {"confirmed": [{"id": "place-1"}], "value": self.states[sid]["value"]}
        else:
            self.states[sid]["value"] += 1
        return self.load(sid)

    def snapshot(self, sid):
        return copy.deepcopy(self.states[sid])

    def restore(self, snapshot):
        self.states[snapshot["id"]] = copy.deepcopy(snapshot)

    def forget(self, user_id):
        return user_id == "user-abc-123"


def make(root=None):
    from harness import Harness, Store
    tools = {s: Tools(s) for s in ("trip", "decision", "planning")}
    return Harness(tools["trip"], tools["decision"], tools["planning"], Store(root)), tools


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
