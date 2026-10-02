import threading

import pytest
from fixtures import hard, love, si, srec

from decision.agent import AgentError
from decision.curation import ActionError
from decision.engine import Engine, NoSession, NotConfirmable, VersionMismatch
from decision.guard import PlanUpdate, TurnPlan
from decision.pipeline import Data
from decision.session import Store
from decision.settings import default

CFG = default()


def data():
    recs = [srec(f"C{i}", name=f"Quán Cà Phê Số {i}", features={"scenic_view": "present", "steep_or_stairs": "absent"},
                 lng=108.44 + i / 1000) for i in range(6)]
    return Data(recs + [srec("M", name="Quán Ăn Bình Dân", usable=("meal",))])


def trip(**over):
    return si(hard_filters=[hard("steep_or_stairs", "present")], soft_weights=[love("scenic_view")], **over).model_dump(mode="json")


class FakeAgent:
    def __init__(self, plan=None, error=None):
        self.plan, self.error, self.calls = plan, error, []

    async def __call__(self, fields, on_say):
        self.calls.append(fields)
        if self.error:
            raise self.error
        on_say(self.plan.say)
        return self.plan


def engine(agent=None):
    return Engine(data(), CFG, Store(None), agent)


def test_create_selects_anchors_and_counts_first_shortlist():
    e = engine()
    out = e.create(trip(anchors=[{"place_id": "C0", "priority": "must"}]))
    s = e.store.get(out["id"])
    assert s.state.selected == ["C0"] and s.state.locked == ["C0"] and s.first_shortlist == len(out["view"]["shortlist"])
    with pytest.raises(VersionMismatch):
        e.create({**trip(), "ontology_version": 1})


def test_act_versions_diff_and_undo():
    e = engine()
    sid = e.create(trip())["id"]
    r = e.act(sid, {"type": "select", "place_id": "C1"})
    assert r["view"]["selected"] == ["C1"] and r["diff"]["delta"]["places"] == 1 and r["diff"]["scope"]["from"] == "diversify"
    assert r["diff"]["text"].startswith("+1 nơi")
    r = e.act(sid, {"type": "undo"})
    assert r["view"]["selected"] == [] and len(e.store.get(sid).log) == 2
    with pytest.raises(ActionError):
        e.act(sid, {"type": "undo"})
    with pytest.raises(ActionError):
        e.act(sid, {"type": "select", "place_id": "NOPE"})
    assert e.store.get(sid).history == []
    with pytest.raises(NoSession):
        e.act("0123456789ab", {"type": "undo"})


def test_parallel_acts_keep_every_step():
    e = engine()
    sid = e.create(trip())["id"]
    ts = [threading.Thread(target=e.act, args=(sid, {"type": "select", "place_id": f"C{i}"})) for i in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    s = e.store.get(sid)
    assert sorted(s.state.selected) == ["C0", "C1", "C2", "C3"] and len(s.history) == 4


def test_turn_with_agent_applies_guarded_actions():
    plan = TurnPlan(say="Mình đã bỏ quán đó.", updates=(PlanUpdate(op="drop", place="P1", value="far", quote="xa quá"),))
    agent = FakeAgent(plan)
    e = engine(agent)
    sid = e.create(trip())["id"]
    first = e.load(sid)["view"]["shortlist"][0]
    events = []
    e.turn(sid, "quán đầu xa quá", lambda ev, d: events.append((ev, d)))
    assert [ev for ev, _ in events] == ["say", "view", "done"]
    view = events[1][1]["view"]
    assert view["dropped"] == [{"id": first, "name": view["dropped"][0]["name"], "reason": "far"}]
    assert "P1 |" in agent.calls[0]["places"] and e.store.get(sid).state.profile.travel_mult == CFG.far_step


def test_turn_falls_back_to_policy():
    e = engine(FakeAgent(error=AgentError("down")))
    sid = e.create(trip())["id"]
    events = []
    e.turn(sid, "Quán Cà Phê Số 2 xa quá", lambda ev, d: events.append((ev, d)))
    assert events[0] == ("say", {"replace": "Mình đã ghi nhận, danh sách đã cập nhật."})
    assert e.store.get(sid).state.dropped[0].place_id == "C2"


def test_compare_why_not_confirm():
    e = engine()
    sid = e.create(trip(context={"days": 1}))["id"]
    assert e.compare(sid, "C0", "C1")["a"]["id"] == "C0"
    with pytest.raises(ActionError):
        e.compare(sid, "C0", "NOPE")
    assert e.why_not(sid, "NOPE")["known"] is False
    e.act(sid, {"type": "select", "place_id": "C0"})
    out = e.confirm(sid)
    assert out["confirmed"][0]["id"] == "C0" and e.store.get(sid).output == out
    for i in range(1, 6):
        e.act(sid, {"type": "select", "place_id": f"C{i}"})
    with pytest.raises(NotConfirmable):
        e.confirm(sid)


def test_rethink_back_sends_the_user_to_understanding():
    e = engine()
    sid = e.create(trip())["id"]
    s = e.store.get(sid)
    s.first_shortlist = 2
    for i in range(6):
        e.act(sid, {"type": "drop", "place_id": f"C{i}"})
    view = e.load(sid)["view"]
    assert view["pending"]["qid"] == "rethink"
    assert e.act(sid, {"type": "answer", "qid": "rethink", "chip": "back"})["goto"] == "understand"
