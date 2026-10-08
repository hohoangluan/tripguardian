import http.client
import json
import threading

import pytest
from plan_fixtures import CFG, FakeLive, fake_lodging, fake_matrix, no_geocode, sample_trip

from planning.engine import Engine
from planning.server import handler
from planning.session import Store


def fake_route(points, mode, live_cfg):
    return {"points": [list(p) for p in points], "source": "osrm", "fetched_at": "t"}


@pytest.fixture
def client():
    d, recs = sample_trip()
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, route_fn=fake_route, background=False)
    from http.server import ThreadingHTTPServer
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(e))
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    yield conn, d
    conn.close()
    server.shutdown()
    server.server_close()
    t.join()


def test_create_then_load(client):
    conn, d = client
    conn.request("POST", "/api/planning/sessions", json.dumps({"decision_output": d}), {"Content-Type": "application/json"})
    out = json.loads(conn.getresponse().read())
    sid = out["id"]
    assert out["view"]["ok"]
    conn.request("GET", f"/api/planning/sessions/{sid}")
    out2 = json.loads(conn.getresponse().read())
    assert out2["id"] == sid


def test_act_then_confirm_round_trip(client):
    conn, d = client
    conn.request("POST", "/api/planning/sessions", json.dumps({"decision_output": d}), {"Content-Type": "application/json"})
    sid = json.loads(conn.getresponse().read())["id"]
    conn.request("GET", f"/api/planning/sessions/{sid}/variants")
    vid = json.loads(conn.getresponse().read())[0]["id"]
    conn.request("POST", f"/api/planning/sessions/{sid}/act", json.dumps({"type": "pick_variant", "id": vid}),
                {"Content-Type": "application/json"})
    assert conn.getresponse().status == 200
    conn.request("POST", f"/api/planning/sessions/{sid}/confirm")
    out = json.loads(conn.getresponse().read())
    assert out["chosen"] == vid


def test_a_bad_act_is_400_and_an_unknown_session_is_404(client):
    conn, d = client
    conn.request("POST", "/api/planning/sessions", json.dumps({"decision_output": d}), {"Content-Type": "application/json"})
    sid = json.loads(conn.getresponse().read())["id"]
    conn.request("POST", f"/api/planning/sessions/{sid}/act", json.dumps({"type": "pick_variant", "id": "nope"}),
                {"Content-Type": "application/json"})
    assert conn.getresponse().status == 400
    conn.request("GET", f"/api/planning/sessions/{'0' * 12}")
    assert conn.getresponse().status == 404


def test_lodging_events_streams_progress_then_done(client):
    conn, d = client
    conn.request("POST", "/api/planning/sessions", json.dumps({"decision_output": d}), {"Content-Type": "application/json"})
    sid = json.loads(conn.getresponse().read())["id"]
    conn.request("GET", f"/api/planning/sessions/{sid}/lodging/events")
    resp = conn.getresponse()
    # the "view" event alone (full session view: itinerary, state, warnings...) can exceed a small fixed buffer, so
    # read to EOF -- the handler closes the connection once "done" is emitted (BaseHTTPRequestHandler's HTTP/1.0
    # default, no keep-alive, since this response is framed by neither Content-Length nor chunked encoding).
    body = resp.read().decode("utf-8")
    assert "event: progress" in body and "event: done" in body


def test_turn_streams_say_view_and_done(client):
    conn, d = client
    conn.request("POST", "/api/planning/sessions", json.dumps({"decision_output": d}), {"Content-Type": "application/json"})
    sid = json.loads(conn.getresponse().read())["id"]
    conn.request("GET", f"/api/planning/sessions/{sid}/variants")
    vid = json.loads(conn.getresponse().read())[0]["id"]
    conn.request("POST", f"/api/planning/sessions/{sid}/act", json.dumps({"type": "pick_variant", "id": vid}),
                {"Content-Type": "application/json"})
    conn.getresponse().read()
    conn.request("POST", f"/api/planning/sessions/{sid}/turn", json.dumps({"text": "đi chậm lại thôi"}),
                {"Content-Type": "application/json"})
    resp = conn.getresponse()
    assert resp.status == 200 and resp.getheader("Content-Type").startswith("text/event-stream")
    body = resp.read().decode("utf-8")
    kinds = [line[len("event: "):] for line in body.splitlines() if line.startswith("event: ")]
    assert kinds == ["say", "view", "done"]  # the server's Engine has no agent: the keyword policy answers


def test_turn_rejects_an_empty_text(client):
    conn, d = client
    conn.request("POST", "/api/planning/sessions", json.dumps({"decision_output": d}), {"Content-Type": "application/json"})
    sid = json.loads(conn.getresponse().read())["id"]
    conn.request("POST", f"/api/planning/sessions/{sid}/turn", json.dumps({"text": "   "}),
                {"Content-Type": "application/json"})
    assert conn.getresponse().status == 400
