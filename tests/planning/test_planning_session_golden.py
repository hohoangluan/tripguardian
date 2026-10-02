"""End to end: create -> background lodging -> pick a variant -> edit -> undo -> confirm. If this breaks, something
in the P6 chain broke even though every task's own tests still pass in isolation."""

from plan_fixtures import CFG, FakeLive, fake_lodging, fake_matrix, no_geocode, sample_trip

from planning.engine import Engine
from planning.session import Store


def fake_route(points, mode, live_cfg):
    return {"points": [list(p) for p in points], "source": "osrm", "fetched_at": "t"}


def test_a_full_session_from_create_to_confirm():
    d, recs = sample_trip(days=2)
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, route_fn=fake_route, background=False)

    created = e.create(d, None)
    sid = created["id"]
    assert created["view"]["ok"] and created["view"]["lodging"]["status"] == "ready"

    variant_id = e.variants(sid)[0]["id"]
    e.act(sid, {"type": "pick_variant", "id": variant_id})

    first_day_before = e.load(sid)["view"]  # just confirms load() works post pick_variant; no field asserted here

    e.act(sid, {"type": "pick_lodging", "id": "h1"})
    e.act(sid, {"type": "lock_slot", "place": "c1"})

    out = e.act(sid, {"type": "drop_place", "place": "s1", "reason": "far"})
    assert any(d["place_id"] == "s1" for d in out["view"]["state"]["dropped"])

    e.act(sid, {"type": "undo"})
    assert not e.load(sid)["view"]["state"]["dropped"]

    plan = e.confirm(sid)
    assert plan["chosen"] == variant_id
    assert plan["lodging"]["chosen"]["id"] == "h1"
    assert len(plan["itinerary"]) == 2
    assert len(plan["route"]) == 2
