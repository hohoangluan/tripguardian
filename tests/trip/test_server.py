import json
import threading
import urllib.request
from datetime import date
from http.server import ThreadingHTTPServer

import pytest

from trip.api.engine import Engine
from trip.api.server import handler
from trip.infrastructure.sessions import SessionStore

from trip_fixtures import ScriptedChat, ask, fact, reply


@pytest.fixture
def base(catalog, cfg):
    engine = Engine(catalog, cfg, SessionStore(None), ScriptedChat(reply(fact("days", "3", "3 ngày"), ask("Đi cùng ai?", "Một mình", "Bạn bè"), text="Mình ghi rồi.")),
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
    r = post(f"{base}/sessions/{v['id']}/turn", {"kind": "text", "text": "đi 3 ngày"})
    assert r.headers["Content-Type"].startswith("text/event-stream")
    assert [e for e, _ in sse(r)] == ["preview", "state", "say", "state", "card"]
    again = json.load(urllib.request.urlopen(f"{base}/sessions/{v['id']}", timeout=5))
    assert again["card"]["text"] == "Đi cùng ai?"
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


def test_user_id_is_validated_and_forget_is_a_delete(base):
    for bad in ({"user_id": "../etc"}, {"user_id": 7}, {"remember": "yes"}):
        with pytest.raises(urllib.error.HTTPError) as e:
            post(f"{base}/sessions", bad)
        assert e.value.code == 400
    assert json.load(post(f"{base}/sessions", {"user_id": "user-abc-123", "remember": True}))["card"]["qid"] == "frame"
    req = urllib.request.Request(f"{base}/profile/user-abc-123", method="DELETE")
    assert json.load(urllib.request.urlopen(req, timeout=5)) == {"forgotten": False}  # learning is off in this engine
