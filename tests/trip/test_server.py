import json
import threading
import urllib.request
from datetime import date
from http.server import ThreadingHTTPServer

import pytest

from trip.agent import AgentError
from trip.engine import Engine
from trip.server import handler
from trip.sessions import SessionStore

from trip_fixtures import FakeAgent


@pytest.fixture
def base(catalog, cfg):
    engine = Engine(catalog, cfg, SessionStore(None), FakeAgent(error=AgentError("down")),
                    today=lambda: date(2026, 10, 2))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler(engine))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/api/trip"
    srv.shutdown()


def post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=5)


def sse(resp):
    events, ev = [], None
    for line in resp.read().decode().splitlines():
        if line.startswith("event: "):
            ev = line[7:]
        elif line.startswith("data: "):
            events.append((ev, json.loads(line[6:])))
    return events


def test_create_turn_and_reload(base):
    v = json.load(post(f"{base}/sessions", {"experience": "first", "start_with": "nothing"}))
    assert v["card"]["qid"] == "frame"
    r = post(f"{base}/sessions/{v['id']}/turn", {"kind": "answer", "qid": "frame",
                                                 "chips": ["days:3", "who:solo", "mobility:car"]})
    assert r.headers["Content-Type"].startswith("text/event-stream")
    assert [e for e, _ in sse(r)] == ["state", "card"]
    again = json.load(urllib.request.urlopen(f"{base}/sessions/{v['id']}", timeout=5))
    assert again["card"]["qid"] == "dates"
    places = json.load(urllib.request.urlopen(f"{base}/places?q=V%C6%B0%E1%BB%9Dn", timeout=5))
    assert places[0]["id"] == "0x11:0x1"


def test_errors(base):
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(f"{base}/sessions/0123456789ab", timeout=5)
    assert e.value.code == 404
    v = json.load(post(f"{base}/sessions", {}))
    with pytest.raises(urllib.error.HTTPError) as e:
        post(f"{base}/sessions/{v['id']}/turn", {"kind": "dance"})
    assert e.value.code == 400
