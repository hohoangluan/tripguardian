import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from test_engine import engine, trip

from decision.server import handler


@pytest.fixture
def base():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler(engine()))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/api/decision/sessions"
    srv.shutdown()


def post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=10)


def get(url):
    return json.load(urllib.request.urlopen(url, timeout=10))


def code(fn):
    with pytest.raises(urllib.error.HTTPError) as e:
        fn()
    return e.value.code


def test_session_flow(base):
    v = json.load(post(base, {"search_input": trip()}))
    sid = v["id"]
    assert get(f"{base}/{sid}")["view"]["shortlist"] == v["view"]["shortlist"]
    r = json.load(post(f"{base}/{sid}/act", {"type": "select", "place_id": "C0"}))
    assert r["view"]["selected"] == ["C0"]
    assert get(f"{base}/{sid}/compare?a=C0&b=C1")["b"]["id"] == "C1"
    assert get(f"{base}/{sid}/why-not/C0")["reasons"] == ["Nơi này đang có trong gợi ý"]
    t = post(f"{base}/{sid}/turn", {"text": "Quán Cà Phê Số 1 xa quá"})
    assert t.headers["Content-Type"].startswith("text/event-stream")
    events = [l[7:] for l in t.read().decode().splitlines() if l.startswith("event: ")]
    assert events == ["say", "view", "done"]
    assert json.load(post(f"{base}/{sid}/confirm", {}))["confirmed"][0]["id"] == "C0"


def test_errors(base):
    sid = json.load(post(base, {"search_input": trip()}))["id"]
    assert code(lambda: post(base, {"search_input": {"bad": 1}})) == 400
    assert code(lambda: post(base, {"search_input": {**trip(), "ontology_version": 1}})) == 409
    assert code(lambda: get(f"{base}/0123456789ab")) == 404
    assert code(lambda: post(f"{base}/{sid}/act", {"type": "drop", "place_id": "C0", "reason": "ugly"})) == 400
    assert code(lambda: post(f"{base}/{sid}/turn", {"text": ""})) == 400
    assert code(lambda: get(f"{base}/../../etc")) == 404
