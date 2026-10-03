import dataclasses

from plan_fixtures import CFG, FakeLive, fake_lodging, fake_matrix, no_geocode, small_trip

from planning.engine import Engine
from planning.guard import PlanUpdate, TurnPlan
from planning.session import Store


def fake_agent(plan: TurnPlan):
    async def run(fields, on_say):
        on_say(plan.say)
        return plan
    return run


def fake_route(points, mode, live_cfg):
    return {"points": [list(p) for p in points], "source": "osrm", "fetched_at": "t"}


def engine(agent=None):
    d, recs = small_trip()
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, route_fn=fake_route,
              background=False, agent=agent)
    sid = e.create(d, None)["id"]
    e.act(sid, {"type": "pick_variant", "id": e.variants(sid)[0]["id"]})
    return e, sid


def events(e, sid, text):
    out = []
    e.turn(sid, text, lambda ev, data: out.append((ev, data)))
    return out


def alias(e, sid, pid: str) -> str:
    """The P# the screen shows for place `pid` -- the order a session lays its days out in is not the fixture's
    insertion order, so tests look the alias up rather than assume it."""
    base = e._ensure_base(sid)
    return next(k for k, v in e._turn_aliases(e._get(sid), base).items() if v.get("id") == pid)


def said(ev) -> str:
    """The text the user finally sees: the streamed deltas, unless a replace event overrode them."""
    text = "".join(d["delta"] for k, d in ev if k == "say" and "delta" in d)
    replaced = [d["replace"] for k, d in ev if k == "say" and "replace" in d]
    return replaced[-1] if replaced else text


def test_a_drop_update_runs_through_the_same_act_as_a_chip():
    e, sid = engine()
    plan = TurnPlan(say="Mình đã bỏ nơi đó.",
                    updates=(PlanUpdate(op="drop", ref=alias(e, sid, "b"), value="dislike", quote="b không thích"),))
    e.agent = fake_agent(plan)
    ev = events(e, sid, "b không thích")
    assert [k for k, _ in ev] == ["say", "view", "done"]
    # the reason only the agent's plan carries: proves the agent path ran, not the keyword policy
    assert e.load(sid)["view"]["state"]["dropped"] == [{"place_id": "b", "reason": "dislike"}]


def test_an_action_a_later_action_in_the_same_turn_invalidates_is_skipped_not_fatal():
    e, sid = engine()
    b = alias(e, sid, "b")
    plan = TurnPlan(say="Mình đã cập nhật.",
                    updates=(PlanUpdate(op="drop", ref=b, value="", quote="bỏ b"),
                            PlanUpdate(op="reorder_edge", ref=b, value="first", quote="bỏ b")))  # built from pre-turn order
    e.agent = fake_agent(plan)
    ev = events(e, sid, "bỏ b")
    assert [k for k, _ in ev] == ["say", "view", "done"]       # no exception escapes the turn
    assert e.load(sid)["view"]["state"]["dropped"][0]["place_id"] == "b"  # the first action still applied


def test_crossing_rethink_drops_in_a_turn_suggests_going_back_instead_of_dropping_again():
    e, sid = engine(agent=None)
    e.cfg = dataclasses.replace(e.cfg, rethink_drops=1)   # small_trip has 3 places; lower the threshold instead
    e.act(sid, {"type": "drop_place", "place": "a"})
    plan = TurnPlan(say="Mình đã bỏ nơi đó.",
                    updates=(PlanUpdate(op="drop", ref=alias(e, sid, "c"), value="", quote="bỏ c luôn"),))
    e.agent = fake_agent(plan)
    ev = events(e, sid, "bỏ c luôn")
    assert "Place Decision" in said(ev) or "chọn lại" in said(ev)
    assert e.load(sid)["view"]["state"]["dropped"] == [{"place_id": "a", "reason": None}]  # c was NOT dropped


def test_turn_falls_back_to_policy_when_the_agent_is_unavailable():
    e, sid = engine(agent=None)
    ev = events(e, sid, "b xa quá")
    assert [k for k, _ in ev] == ["say", "view", "done"]
    assert e.load(sid)["view"]["state"]["dropped"][0]["place_id"] == "b"


def test_turn_falls_back_to_policy_when_the_agent_raises():
    async def boom(fields, on_say):
        raise RuntimeError("agent host down")
    e, sid = engine(agent=boom)
    ev = events(e, sid, "b xa quá")
    assert [k for k, _ in ev] == ["say", "view", "done"]
    assert e.load(sid)["view"]["state"]["dropped"][0]["place_id"] == "b"


def test_a_full_turn_session_create_pick_turn_confirm():
    """One pass through everything P7 built: create, pick a variant, two turns (one agent op, one policy fallback),
    confirm -- the same path the web Itinerary screen (P8) will drive."""
    e, sid = engine()
    a = alias(e, sid, "a")
    plan = TurnPlan(say="Mình đã đưa nơi đó lên đầu buổi sáng.",
                    updates=(PlanUpdate(op="reorder_edge", ref=a, value="first", quote="a đi trước nhé"),))
    e.agent = fake_agent(plan)
    events(e, sid, "a đi trước nhé")
    e.agent = None  # second turn: agent "goes down", policy takes over
    events(e, sid, "b xa quá")
    out = e.confirm(sid)
    assert out["itinerary"] and "b" not in {i.get("place_id") for day in out["itinerary"] for i in day["items"]}
