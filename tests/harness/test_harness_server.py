import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from test_dispatch import make


@pytest.fixture
def client():
    from harness.server import handler
    harness, _ = make()
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(harness))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    yield connection
    connection.close()
    server.shutdown()
    server.server_close()
    worker.join()


def call(client, method, path, data=None):
    client.request(method, path, json.dumps(data) if data is not None else None, {"Content-Type": "application/json"})
    response = client.getresponse()
    return response.status, json.loads(response.read())


def test_http_validates_input_and_routes_a_journey(client):
    code, view = call(client, "POST", "/api/harness/sessions", {})
    assert code == 200 and view["stage"] == "trip"
    assert call(client, "POST", "/api/harness/sessions", [1])[0] == 400
    assert call(client, "GET", "/api/harness/sessions/000000000000")[0] == 404
    req = {"request_id": "wrong-stage", "stage": "planning", "operation": "act", "expected_revision": 0}
    assert call(client, "POST", f"/api/harness/sessions/{view['id']}/request", req)[0] == 409
    assert call(client, "POST", f"/api/harness/sessions/{view['id']}/request", {})[0] == 400


def test_turn_sse_has_request_stage_and_committed_revision(client):
    _, view = call(client, "POST", "/api/harness/sessions", {})
    req = {"request_id": "trip-turn", "stage": "trip", "operation": "turn", "expected_revision": 0,
        "payload": {"kind": "show"}}
    client.request("POST", f"/api/harness/sessions/{view['id']}/request", json.dumps(req),
        {"Content-Type": "application/json", "Accept": "text/event-stream"})
    response = client.getresponse()
    raw = response.read().decode()
    envelopes = [json.loads(line[6:]) for line in raw.splitlines() if line.startswith("data: ")]
    assert response.status == 200 and envelopes
    assert all(e["request_id"] == "trip-turn" and e["stage"] == "trip" for e in envelopes)
    assert envelopes[-1]["event"] == "journey" and envelopes[-1]["revision"] == 1
    assert envelopes[-1]["data"]["revision"] == 1
    _, current = call(client, "GET", f"/api/harness/sessions/{view['id']}")
    assert current["revision"] == 1


def test_bad_start_does_not_create_a_journey(client):
    assert call(client, "POST", "/api/harness/sessions", {"experience": "not-valid"})[0] == 400
    assert call(client, "POST", "/api/harness/sessions", {"user_id": "../escape"})[0] == 400


def test_profile_delete_is_available_through_the_harness(client):
    code, body = call(client, "DELETE", "/api/harness/profile/user-abc-123")
    assert code == 200 and body == {"forgotten": True}


def test_sse_conflict_after_headers_preserves_conflict_status(client):
    _, view = call(client, "POST", "/api/harness/sessions", {})
    path = f"/api/harness/sessions/{view['id']}/request"
    req = {"request_id": "same-id", "stage": "trip", "operation": "turn", "expected_revision": 0,
           "payload": {"kind": "show"}}
    assert call(client, "POST", path, req)[0] == 200
    req['payload'] = {"kind": "text", "text": "changed request"}
    client.request("POST", path, json.dumps(req), {"Content-Type": "application/json", "Accept": "text/event-stream"})
    response = client.getresponse()
    events = [json.loads(line[6:]) for line in response.read().decode().splitlines() if line.startswith('data: ')]
    assert events[-1]['event'] == 'error'
    assert events[-1]['data']['status'] == 409


def test_preview_and_trip_summaries_are_reads(client):
    _, view = call(client, "POST", "/api/harness/sessions", {})
    assert call(client, "GET", f"/api/harness/sessions/{view['id']}/preview")[0] == 409
    code, body = call(client, "GET", f"/api/harness/trips?ids={view['id']},000000000000")
    assert code == 200 and [s["id"] for s in body] == [view["id"]]


def test_reports_go_to_decision_and_bad_input_is_400(client):
    body = {"place_id": "place-1", "text": "Quán đóng cửa thứ Hai", "reporter": "browser-123"}
    assert call(client, "POST", "/api/harness/reports", body) == (200, {"id": "r1", "stored": True})
    assert call(client, "POST", "/api/harness/reports", {**body, "text": ""})[0] == 400


def test_decision_page_is_a_read(client):
    _, view = call(client, "POST", "/api/harness/sessions", {})
    base = f"/api/harness/sessions/{view['id']}"
    req = {"request_id": "t", "stage": "trip", "operation": "turn", "expected_revision": 0, "payload": {"kind": "show"}}
    call(client, "POST", f"{base}/request", req)
    call(client, "POST", f"{base}/request", {"request_id": "a", "stage": "trip", "operation": "advance", "expected_revision": 1})
    code, body = call(client, "GET", f"{base}/read/decision/page?group=chill")
    assert code == 200 and body == {"operation": "page", "payload": {"group": "chill"}}
