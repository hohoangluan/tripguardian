import pytest
from plan_fixtures import CFG, FakeLive, fake_matrix, no_geocode
from fixtures import srec

from trip import Catalog, Engine as TripEngine, SessionStore, Settings


def test_public_trip_tools_round_trip_state_and_reject_an_invalid_start():
    from trip import Tools
    engine = TripEngine(Catalog.from_records([], 1), Settings(), SessionStore(None), chat=None)
    tools = Tools(engine)
    with pytest.raises(ValueError):
        tools.create({"experience": "invented"})
    with pytest.raises(ValueError):
        tools.create({"user_id": "../escape"})
    created = tools.create({"user_id": "user-abc-123", "remember": True})
    tools.apply(created["id"], "turn", {"kind": "edit", "target": "days", "value": "2"}, lambda *a: None)
    snapshot = tools.snapshot(created["id"])
    restored = Tools(TripEngine(Catalog.from_records([], 1), Settings(), SessionStore(None), chat=None))
    restored.restore(snapshot)
    assert restored.load(created["id"]) == tools.load(created["id"])


def test_real_decision_and_planning_tools_preserve_selection_on_handoff(tmp_path):
    from decision import Data, Engine as DecisionEngine, Store as DecisionStore, Tools as DecisionTools, load_settings
    from planning import Engine as PlanningEngine, Tools as PlanningTools
    from harness import Harness, Store
    from test_dispatch import Tools as FakeTools, decision, run
    records = [srec("place-1", name="Synthetic Place")]
    decision_tools = DecisionTools(DecisionEngine(Data(records), load_settings(), DecisionStore(None)))
    planning_tools = PlanningTools(PlanningEngine(records, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode,
        matrix_fn=fake_matrix, sun_fn=lambda *a: (360, 1050), lodging_fn=lambda *a: [],
        route_fn=lambda *a: {"points": [], "source": "osrm", "fetched_at": "t"}, background=False))
    harness = Harness(FakeTools("trip"), decision_tools, planning_tools, Store(tmp_path))
    view = decision(harness)
    view = run(harness, view, "act", "select", {"type": "select", "place_id": "place-1"})
    view = run(harness, view, "advance", "to-planning")
    assert view["outputs"]["decision"]["confirmed"][0]["id"] == "place-1"
    view = run(harness, view, "back", "more-places")
    assert view["result"]["view"]["selected"] == ["place-1"]


def test_planning_tools_reject_chat_without_invoking_the_agent():
    from planning import Engine, Tools
    tools = Tools(Engine([]))
    with pytest.raises(ValueError, match="turn"):
        tools.apply("000000000001", "turn", {"text": "change everything"}, lambda *a: None)


def test_missing_module_session_is_a_public_404_error():
    from agents import ToolError
    from planning import Engine, Tools
    with pytest.raises(ToolError) as caught:
        Tools(Engine([])).load("000000000000")
    assert caught.value.status == 404


def test_harness_adapter_refuses_a_second_persistence_owner(tmp_path):
    from trip import Tools
    engine = TripEngine(Catalog.from_records([], 1), Settings(), SessionStore(tmp_path), chat=None)
    with pytest.raises(ValueError, match="memory"):
        Tools(engine)


def test_real_trip_compiles_clues_and_harness_advances_with_a_scripted_agent(tmp_path):
    import json
    from trip import Tools
    from trip.agent import Assistant, Call
    from harness import Harness, Store
    from test_dispatch import Tools as FakeTools, run

    def fact(field, value, quote):
        args = {"field": field, "op": "set", "value": value, "quote": quote, "how": "said"}
        return Call(f"c_{field}", "record_fact", json.dumps(args))
    script = [Assistant(calls=[fact("days", "3", "3 ngày"), fact("mobility", "car", "ô tô"),
                               fact("companions", "solo", "một mình"), fact("month", "12", "tháng 12")]),
              Assistant(content="Mình đã ghi lại rồi.")]  # facts only: the loop calls the model again, which answers

    async def scripted(messages, tools, on_say):
        return script.pop(0)
    trip = Tools(TripEngine(Catalog.from_records([], 1), Settings(), SessionStore(None), scripted))
    harness = Harness(trip, FakeTools("decision"), FakeTools("planning"), Store(tmp_path))
    view = harness.create("first", "nothing")
    view = run(harness, view, "turn", "opening", {"kind": "text", "text": "3 ngày đi ô tô một mình tháng 12"})
    assert view["result"]["understanding"]["ready"] is True
    view = run(harness, view, "turn", "show", {"kind": "show"})
    assert view["outputs"]["trip"]["context"]["days"] == 3
    assert view["outputs"]["trip"]["context"]["mobility"] == "car"
    advanced = run(harness, view, "advance", "to-decision")
    assert advanced["stage"] == "decision" and advanced["id"] == view["id"]


def test_decision_compare_is_read_only_for_canonical_journey_snapshot():
    from decision import Data, Engine, Store, Tools, load_settings
    from fixtures import si
    engine = Engine(Data([srec("a", name="Place A"), srec("b", name="Place B")]), load_settings(), Store(None))
    tools = Tools(engine)
    sid = tools.create({"search_input": si().model_dump(mode="json")})["id"]
    before = tools.snapshot(sid)
    assert tools.read(sid, "compare", {"a":"a", "b":"b"})["a"]["id"] == "a"
    assert tools.snapshot(sid) == before
