"""Trip redesign part 5 at the harness: "Lập lịch" with an incomplete trip is a 409 the web can answer in place.

Architecture doc §1 A5, §5.7. Ids H1-H4. Before this, planning.TripIncomplete escaped the harness as a 500 and no
real journey could reach Lịch trình.
"""

import pytest
from test_dispatch import decision, make, run

READBACK = {"lines": [{"kind": "said", "text": "T6 20/11 → CN 22/11", "tab": "trip", "undo": None}],
            "digest": "d1", "ok": False, "missing": [], "deck": None}


def gated(tools, missing):
    """Planning refuses until the trip read-back is confirmed; the trip module answers reads and turns."""
    from planning import TripIncomplete
    state = {"ok": False, "turns": []}

    create_plan = tools["planning"].create

    def create(payload):
        if not state["ok"]:
            raise TripIncomplete(list(missing))
        return create_plan(payload)

    def read(sid, operation, payload):
        assert operation in ("readback", "search_input")
        if operation == "readback":
            return dict(READBACK, ok=state["ok"], missing=[m for m in missing if m != "readback"])
        out = []
        tools["trip"]._compiled(sid, lambda event, data: out.append(data["search_input"]))
        return out[-1] | {"readiness": {"missing": [], "readback_ok": state["ok"]}}

    apply_trip = tools["trip"].apply

    def apply(sid, operation, payload, emit):
        if operation == "turn" and payload.get("kind") in ("readback_ok", "deck", "drop"):
            state["turns"].append(payload)
            state["ok"] = payload.get("kind") == "readback_ok" and payload.get("value") == "d1"
            return tools["trip"].load(sid)
        return apply_trip(sid, operation, payload, emit)

    tools["planning"].create = create
    tools["trip"].read = read
    tools["trip"].apply = apply
    return state


def test_h1_an_unconfirmed_trip_is_a_typed_conflict_with_the_readback_not_a_crash():
    from harness import Conflict, TripNotReady
    h, tools = make()
    v = decision(h)
    gated(tools, ["readback"])
    with pytest.raises(TripNotReady) as caught:
        run(h, v, "advance", "to-planning")
    assert isinstance(caught.value, Conflict)
    assert caught.value.missing == ["readback"] and caught.value.readback["digest"] == "d1"
    after = h.load(v["id"])
    assert after["stage"] == "decision" and "planning" not in after["sessions"] and after["revision"] == v["revision"]


def test_h2_the_readback_is_confirmed_from_the_decision_stage_and_planning_opens():
    h, tools = make()
    v = decision(h)
    state = gated(tools, ["readback"])
    v = run(h, v, "trip", "confirm", {"kind": "readback_ok", "value": "d1"})
    assert v["stage"] == "decision" and state["turns"] == [{"kind": "readback_ok", "value": "d1"}]
    assert v["outputs"]["trip"]["readiness"]["readback_ok"] is True
    assert "rebased" in tools["decision"].states[v["sessions"]["decision"]]  # Lựa chọn sees the same trip
    v = run(h, v, "advance", "to-planning")
    assert v["stage"] == "planning"


def test_h3_a_stale_confirmation_keeps_the_gate_closed():
    from harness import TripNotReady
    h, tools = make()
    v = decision(h)
    gated(tools, ["readback"])
    v = run(h, v, "trip", "stale", {"kind": "readback_ok", "value": "old"})
    with pytest.raises(TripNotReady):
        run(h, v, "advance", "to-planning")


def test_h4_only_read_back_answers_reach_the_trip_from_the_decision_stage():
    from harness import RouteError
    h, tools = make()
    v = decision(h)
    gated(tools, ["pace", "readback"])
    for payload in ({"kind": "text", "text": "đổi sang 5 ngày"}, {"kind": "show"}, {"kind": "answer", "qid": "x"}):
        with pytest.raises((RouteError, ValueError)):
            run(h, v, "trip", f"bad-{payload['kind']}", payload)
    v = run(h, v, "trip", "tap", {"kind": "deck", "answers": {"pace": ["slow"]}})
    assert v["stage"] == "decision"
