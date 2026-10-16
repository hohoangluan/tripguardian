import threading

import pytest


def test_rate_window_is_bounded_and_expired_clients_can_retry():
    from harness.protection import RateGate
    now = [0.0]
    gate = RateGate(max_keys=2, clock=lambda: now[0])
    assert gate.allow("a", 2) and gate.allow("a", 2)
    assert not gate.allow("a", 2)
    assert gate.allow("b", 2)
    assert not gate.allow("c", 2)
    now[0] = 61
    assert gate.allow("a", 2) and gate.allow("c", 2)


def test_rate_limit_is_atomic_under_concurrent_requests():
    from harness.protection import RateGate
    gate = RateGate(max_keys=10)
    results = []
    threads = [threading.Thread(target=lambda: results.append(gate.allow("user", 2))) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(results) == 2


def test_http_chat_limit_returns_429_before_harness_runs(monkeypatch):
    import http.client
    import json
    from http.server import ThreadingHTTPServer
    from harness.server import handler
    from harness.protection import ProtectionSettings
    from test_dispatch import make
    from test_harness_server import FakeAccounts, ORIGIN, headers

    h, tools = make()
    v = h.create(owner="a" * 32)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(h, FakeAccounts(), ORIGIN,
        protection=ProtectionSettings(per_ip_minute=2, per_user_minute=1)))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    try:
        path = f"/api/harness/sessions/{v['id']}/request"
        body = {"request_id": "first", "stage": "trip", "operation": "turn", "expected_revision": 0,
                "payload": {"kind": "text", "text": "3 ngày"}}
        connection.request("POST", path, json.dumps(body), headers())
        first = connection.getresponse()
        assert first.status == 200
        first.read()
        body.update(request_id="second", expected_revision=1)
        connection.request("POST", path, json.dumps(body), headers(**{"X-Forwarded-For": "1.2.3.4"}))
        response = connection.getresponse()
        assert response.status == 429 and response.getheader("Retry-After") == "60"
        response.read()
        assert tools["trip"].calls == 1
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        worker.join()
