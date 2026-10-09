import pytest

from harness import Conflict, RouteError
from test_dispatch import decision, make, run


class FakeCompanion:
    def __init__(self):
        self.synced, self.calls = [], []

    def sync(self, jid, user_id, plan):
        self.synced.append((jid, plan["value"]))

    def today(self, jid, plan, day=None):
        return {"plan_value": plan["value"], "day": day}

    def checkin(self, jid, stop_id, place_id):
        self.calls.append(("checkin", stop_id, place_id))
        return {"ok": True}

    def option(self, jid, plan, option_id):
        if option_id != "drop:b":
            raise ValueError("that option is not offered")
        return {"type": "drop_place", "place": "b"}

    def suggestions(self, jid, si, plan, place_id, disliked, similar):
        return {"place_id": place_id, "disliked": sorted(disliked)}


def confirmed():
    h, tools = make()
    h.companion = FakeCompanion()
    v = run(h, decision(h), "advance", "to-planning")
    v = run(h, v, "confirm", "confirm-1")
    return h, v


def test_confirm_makes_the_trip_and_today_reads_it():
    h, v = confirmed()
    assert h.companion.synced == [(v["id"], v["outputs"]["planning"]["value"])]
    assert h.today(v["id"], day=2) == {"plan_value": v["outputs"]["planning"]["value"], "day": 2}


def test_companion_needs_a_confirmed_plan_and_known_operations():
    h, _ = make()
    h.companion = FakeCompanion()
    v = decision(h)
    with pytest.raises(RouteError):
        h.companion_act(v["id"], "checkin", {"stop_id": "x"})
    h2, v2 = confirmed()
    with pytest.raises(RouteError):
        h2.companion_act(v2["id"], "teleport", {})
    assert h2.companion_act(v2["id"], "checkin", {"place_id": "p"}) == {"ok": True}


def test_add_and_adjust_change_the_plan_only_when_confirmed_and_valid():
    h, v = confirmed()
    with pytest.raises(ValueError):
        h.companion_act(v["id"], "add", {"place_id": "x", "day": 1})  # no confirmed: true
    before = h.load(v["id"])
    with pytest.raises(ValueError):
        h.companion_act(v["id"], "add", {"place_id": "not-in-backups", "day": 1, "confirmed": True})
    after = h.load(v["id"])
    assert "planning" in after["outputs"] and after["revision"] == before["revision"]  # refused by Planning: no change
    with pytest.raises(ValueError):
        h.companion_act(v["id"], "adjust", {"option_id": "drop:zzz", "confirmed": True})
    out = h.companion_act(v["id"], "adjust", {"option_id": "drop:b", "confirmed": True})
    assert out["changed"] and h.load(v["id"])["revision"] == before["revision"] + 2  # act + confirm
    assert len(h.companion.synced) == 2


def test_another_owner_cannot_reach_the_companion():
    h, v = confirmed()
    with pytest.raises(KeyError):
        h.today(v["id"], owner="b" * 32)


def test_companion_off_is_a_conflict():
    h, v = confirmed()
    h.companion = None
    with pytest.raises(Conflict):
        h.today(v["id"])
