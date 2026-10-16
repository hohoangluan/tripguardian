from plan_fixtures import CFG, FakeLive, LODGING, fake_matrix, no_geocode, small_trip

from planning.engine import Engine
from planning.session import Store


def engine(route_fn):
    d, recs = small_trip()
    e = Engine(recs + LODGING, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), route_fn=route_fn, background=False)
    sid = e.create(d, None)["id"]
    e.act(sid, {"type": "pick_variant", "id": e.variants(sid)[0]["id"]})
    return e, sid


def test_routes_draw_each_day_through_its_stops_and_stay_out_of_the_view():
    seen = []

    def route(points, mode, cfg):
        seen.append(list(points))
        return {"coords": [list(p) for p in points], "minutes": 10, "source": "osrm", "fetched_at": "t"}

    e, sid = engine(route)
    assert "routes" not in e.load(sid)["view"] and not seen
    out = e.routes(sid)["days"]
    assert [d["day"] for d in out] == list(range(1, len(out) + 1)) and seen
    assert all(set(d["start"]) == {"id", "name", "home"} for d in out)
    assert all(d["route"]["source"] == "osrm" and len(d["route"]["coords"]) >= 2 for d in out if d["route"])


def test_routes_are_none_when_the_routing_source_is_down():
    from live import Unavailable

    def down(points, mode, cfg):
        raise Unavailable("osrm down")

    e, sid = engine(down)
    assert all(d["route"] is None for d in e.routes(sid)["days"])
