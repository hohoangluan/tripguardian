import pytest
from plan_fixtures import CFG, FakeLive, fake_matrix, no_geocode, rec
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
        matrix_fn=fake_matrix, sun_fn=lambda *a: (360, 1050), route_fn=lambda *a: {"points": [], "source": "osrm", "fetched_at": "t"}, background=False))
    harness = Harness(FakeTools("trip"), decision_tools, planning_tools, Store(tmp_path))
    view = decision(harness)
    view = run(harness, view, "act", "select", {"type": "select", "place_id": "place-1"})
    view = run(harness, view, "advance", "to-planning")
    assert view["outputs"]["decision"]["confirmed"][0]["id"] == "place-1"
    assert view["outputs"]["decision"]["trip_context"]["activities"]["place-1"] == "coffee"
    view = run(harness, view, "back", "more-places")
    assert view["result"]["view"]["selected"] == ["place-1"]


def test_real_overload_handoff_offers_profiles_and_confirms_only_valid_drafts(tmp_path):
    from decision import Data, Engine as DecisionEngine, Store as DecisionStore, Tools as DecisionTools, load_settings
    from planning import Engine as PlanningEngine, Tools as PlanningTools
    from harness import Harness, Store
    from test_dispatch import Tools as FakeTools, decision, run
    from plan_fixtures import CENTRE, spot
    records = [spot(f'p{i}', CENTRE, i % 3, price={'typical_vnd': 10000}) for i in range(16)]
    for record in records:
        record['provenance'] = {'voices': 1}
    dt = DecisionTools(DecisionEngine(Data(records), load_settings(), DecisionStore(None)))
    pt = PlanningTools(PlanningEngine(records, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode,
        matrix_fn=fake_matrix, sun_fn=lambda *a: (360, 1050), route_fn=lambda *a: {'points': [], 'source': 'fixture', 'fetched_at': 't'}, background=False))
    h = Harness(FakeTools('trip'), dt, pt, Store(tmp_path))
    v = decision(h)
    for i in range(16):
        v = run(h, v, 'act', f'select-{i}', {'type': 'select', 'place_id': f'p{i}'})
    original = list(v['result']['view']['selected'])
    assert len(original) == 16
    before = v['revision']
    preview = h.preview(v['id'])
    assert preview['status'] == 'ready'
    assert h.load(v['id'])['revision'] == before
    v = run(h, v, 'advance', 'to-overloaded-planning')
    assert {p['id'] for p in v['outputs']['decision']['confirmed']} == set(original)
    pv = v['result']['view']
    assert {p['preset'] for p in pv['variants']} == {'low_cost', 'diverse', 'least_travel'}
    v = run(h, v, 'recommend', 'automatic-proposal')
    assert v['result']['view']['state']['chosen_variant'] is None
    assert not pv['needs_hotel']  # a plan without a lodging is offered, never refused
    v = run(h, v, 'act', 'choose-hotel', {'type': 'set_lodging', 'text': 'Chosen hotel', 'lat': 11.94, 'lng': 108.45})
    pv = v['result']['view']
    available = next(p for p in pv['variants'] if p['confirmable'])
    v = run(h, v, 'act', 'pick-valid-profile', {'type': 'pick_variant', 'id': available['id']})
    assert not v['result']['view']['violations']
    v = run(h, v, 'confirm', 'confirm-valid-profile')
    assert v['outputs']['planning']['chosen'] == available['id']
    assert {p['id'] for p in v['outputs']['decision']['confirmed']} == set(original)


def test_planning_tools_reject_chat_without_invoking_the_agent():
    from planning import Engine, Tools
    tools = Tools(Engine([]))
    with pytest.raises(ValueError, match="turn"):
        tools.apply("000000000001", "turn", {"text": "change everything"}, lambda *a: None)


def test_real_planning_suggestion_read_preserves_snapshot_and_tags_journey_revision(tmp_path):
    from decision import Data, Engine as DecisionEngine, Store as DecisionStore, Tools as DecisionTools, load_settings
    from planning import Engine as PlanningEngine, Tools as PlanningTools
    from harness import Harness, Store
    from test_dispatch import Tools as FakeTools, decision, run
    records = [srec("place-1", name="Synthetic Place")]
    decision_tools = DecisionTools(DecisionEngine(Data(records), load_settings(), DecisionStore(None)))
    planning_tools = PlanningTools(PlanningEngine(records, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode,
        matrix_fn=fake_matrix, sun_fn=lambda *a: None, background=False))
    harness = Harness(FakeTools("trip"), decision_tools, planning_tools, Store(tmp_path))
    view = decision(harness)
    view = run(harness, view, "act", "select", {"type": "select", "place_id": "place-1"})
    view = run(harness, view, "advance", "to-planning")
    view = run(harness, view, "act", "choose-hotel", {"type": "set_lodging", "text": "Chosen hotel", "lat": 11.94, "lng": 108.45})
    variant = view["result"]["view"]["variants"][0]["id"]
    view = run(harness, view, "act", "pick", {"type": "pick_variant", "id": variant})
    sid = view["sessions"]["planning"]
    before = planning_tools.snapshot(sid)
    result = harness.read(view["id"], "planning", "suggestions")
    assert result["revision"] == view["revision"] and result["session_id"] == sid
    assert result["token"] == view["result"]["view"]["suggestions"]["token"]
    assert result["status"] == "ready"
    assert planning_tools.snapshot(sid) == before


def test_real_planning_preview_act_is_read_only_and_returns_a_bound_token(tmp_path):
    import json
    from decision import Data, Engine as DecisionEngine, Store as DecisionStore, Tools as DecisionTools, load_settings
    from planning import Engine as PlanningEngine, Tools as PlanningTools
    from harness import Harness, Store
    from test_dispatch import Tools as FakeTools, decision, run

    records = [srec("place-1", name="Synthetic Place")]
    decision_tools = DecisionTools(DecisionEngine(Data(records), load_settings(), DecisionStore(None)))
    planning_tools = PlanningTools(PlanningEngine(records, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode,
        matrix_fn=fake_matrix, sun_fn=lambda *a: None, background=False))
    harness = Harness(FakeTools("trip"), decision_tools, planning_tools, Store(tmp_path))
    view = decision(harness)
    view = run(harness, view, "act", "select", {"type": "select", "place_id": "place-1"})
    view = run(harness, view, "advance", "to-planning")
    view = run(harness, view, "act", "choose-hotel", {"type": "set_lodging", "text": "Chosen hotel", "lat": 11.94, "lng": 108.45})
    variant = view["result"]["view"]["variants"][0]["id"]
    view = run(harness, view, "act", "pick", {"type": "pick_variant", "id": variant})
    sid = view["sessions"]["planning"]
    before = planning_tools.snapshot(sid)
    pid = next(item["place_id"] for item in view["result"]["view"]["itinerary"][0]["items"]
               if item["kind"] == "visit")

    preview = harness.read(view["id"], "planning", "preview-act",
                           {"action": json.dumps({"type": "drop_place", "place": pid})})

    assert preview["token"] and preview["action"]["type"] == "drop_place"
    assert preview["view"]["state"]["dropped"][0]["place_id"] == pid
    assert planning_tools.snapshot(sid) == before


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
    from langchain_core.messages import AIMessageChunk
    from harness import Harness, Store
    from test_dispatch import Tools as FakeTools, run

    def fact(field, value, quote):
        args = {"field": field, "op": "set", "value": value, "quote": quote, "how": "said"}
        return {"id": f"c_{field}", "name": "record_fact", "args": json.dumps(args)}
    calls = [fact("days", "3", "3 ngày"), fact("mobility", "car", "ô tô"),
             fact("companions", "solo", "một mình"), fact("month", "12", "tháng 12")]
    script = [AIMessageChunk(content="", tool_call_chunks=[dict(c, index=i) for i, c in enumerate(calls)]),
              AIMessageChunk(content="Mình đã ghi lại rồi.")]

    async def scripted(messages, tools, on_say):
        chunk = script.pop(0)
        if chunk.text:
            on_say(chunk.text)
        return chunk
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


def test_a_trip_saved_by_an_older_build_still_opens():
    from trip import Tools
    engine = TripEngine(Catalog.from_records([], 1), Settings(), SessionStore(None), chat=None)
    tools = Tools(engine)
    created = tools.create({"user_id": "user-abc-123", "remember": True})
    snapshot = tools.snapshot(created["id"])
    # fields later builds dropped, as old saved journeys still carry them (50 of 556 on 2026-10-16)
    snapshot["state"]["other_facts"] = []
    snapshot["state"]["meta"]["requiz"] = False
    snapshot["state"]["meta"]["phase"] = "paused"
    snapshot["state"]["unmapped"] = [{"phrase": "đi chơi", "turn": 1, "group": "x"}]
    restored = Tools(TripEngine(Catalog.from_records([], 1), Settings(), SessionStore(None), chat=None))
    restored.restore(snapshot)
    assert restored.load(created["id"])["id"] == created["id"]
