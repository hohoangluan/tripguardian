import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from test_dispatch import make


ORIGIN = "http://app.test"
USERS = {"tok-a": "a" * 32, "tok-b": "b" * 32}
GUEST = {"tok-g": "9" * 32}


class FakeAccounts:
    """Sessions tok-a / tok-b; the real service is covered in tests/accounts."""
    def __init__(self):
        self.logged_out, self.deleted, self.places, self.guests, self.patterns = [], [], {}, 0, {}

    def user_for(self, token):
        if token in GUEST:
            return {"id": GUEST[token], "role": "guest"}, False
        return ({"id": USERS[token], "role": "user"}, False) if token in USERS else (None, False)

    def guest(self, user_agent=""):
        self.guests += 1
        return "tok-g"

    def consent(self, uid, version):
        if version != "v1":
            raise ValueError("terms version is not current")
        return self.me(uid)

    def set_patterns(self, uid, on):
        if not isinstance(on, bool):
            raise ValueError("patterns must be true or false")
        self.patterns[uid] = on
        return self.me(uid)

    def me(self, uid):
        return {"id": uid, "role": "guest" if uid in GUEST.values() else "user",
                "consents": {"patterns": True} if self.patterns.get(uid) else {},
                "usual_mobility": "motorbike", "usual_companions": None}

    def update(self, uid, patch):
        if set(patch) - {"home_city"}:
            raise ValueError("unknown profile field")
        return {"id": uid, **patch}

    def set_avatar(self, uid, data):
        return {"id": uid, "bytes": len(data)}

    def saved(self, uid):
        return self.places.setdefault(uid, [])

    def save_places(self, uid, ids):
        if not isinstance(ids, list) or not ids:
            raise ValueError("place_ids must be a list")
        self.places[uid] = ids + [p for p in self.saved(uid) if p not in ids]
        return self.places[uid]

    def unsave_place(self, uid, pid):
        self.places[uid] = [p for p in self.saved(uid) if p != pid]
        return self.places[uid]

    def logout(self, token):
        self.logged_out.append(token)

    def delete(self, uid):
        self.deleted.append(uid)


@pytest.fixture
def server_parts():
    harness, tools = make()
    return harness, tools, FakeAccounts()


@pytest.fixture
def client(server_parts):
    from harness.server import handler
    harness, _, accounts = server_parts
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(harness, accounts, ORIGIN))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    yield connection
    connection.close()
    server.shutdown()
    server.server_close()
    worker.join()


def headers(token="tok-a", origin=ORIGIN, **extra):
    out = {"Content-Type": "application/json", **extra}
    if token:
        out["Cookie"] = f"tg_session={token}"
    if origin:
        out["Origin"] = origin
    return out


def call(client, method, path, data=None, token="tok-a", origin=ORIGIN):
    client.request(method, path, json.dumps(data) if data is not None else None, headers(token, origin))
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


def test_only_a_missing_journey_is_404_and_a_stage_key_error_is_500(server_parts, client):
    harness, _, _ = server_parts
    _, view = call(client, "POST", "/api/harness/sessions", {})

    def broken(*args, **kwargs):  # e.g. Planning indexing a place it never loaded
        raise KeyError("place-9")
    harness.load = broken
    code, body = call(client, "GET", f"/api/harness/sessions/{view['id']}")
    assert code == 500 and body == {"error": "server error"}
    assert call(client, "GET", "/api/harness/sessions/000000000000")[0] == 500  # load itself is broken here
    del harness.load
    assert call(client, "GET", "/api/harness/sessions/000000000000")[0] == 404


def test_turn_sse_has_request_stage_and_committed_revision(client):
    _, view = call(client, "POST", "/api/harness/sessions", {})
    req = {"request_id": "trip-turn", "stage": "trip", "operation": "turn", "expected_revision": 0,
        "payload": {"kind": "show"}}
    client.request("POST", f"/api/harness/sessions/{view['id']}/request", json.dumps(req),
        headers(Accept="text/event-stream"))
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


def test_profile_delete_is_only_for_the_own_profile(client):
    code, body = call(client, "DELETE", f"/api/harness/profile/{USERS['tok-a']}")
    assert code == 200 and set(body) == {"forgotten"}
    assert call(client, "DELETE", "/api/harness/profile/user-abc-123")[0] == 404


def test_sse_conflict_after_headers_preserves_conflict_status(client):
    _, view = call(client, "POST", "/api/harness/sessions", {})
    path = f"/api/harness/sessions/{view['id']}/request"
    req = {"request_id": "same-id", "stage": "trip", "operation": "turn", "expected_revision": 0,
           "payload": {"kind": "show"}}
    assert call(client, "POST", path, req)[0] == 200
    req['payload'] = {"kind": "text", "text": "changed request"}
    client.request("POST", path, json.dumps(req), headers(Accept="text/event-stream"))
    response = client.getresponse()
    events = [json.loads(line[6:]) for line in response.read().decode().splitlines() if line.startswith('data: ')]
    assert events[-1]['event'] == 'error'
    assert events[-1]['data']['status'] == 409


def test_preview_and_trip_summaries_are_reads(client):
    _, view = call(client, "POST", "/api/harness/sessions", {})
    assert call(client, "GET", f"/api/harness/sessions/{view['id']}/preview")[0] == 409
    code, body = call(client, "GET", "/api/harness/trips")
    assert code == 200 and [s["id"] for s in body] == [view["id"]]
    assert call(client, "GET", "/api/harness/trips", token="tok-b") == (200, [])


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


def test_decision_fit_is_a_read(client):
    _, view = call(client, "POST", "/api/harness/sessions", {})
    base = f"/api/harness/sessions/{view['id']}"
    req = {"request_id": "t", "stage": "trip", "operation": "turn", "expected_revision": 0, "payload": {"kind": "show"}}
    call(client, "POST", f"{base}/request", req)
    call(client, "POST", f"{base}/request", {"request_id": "a", "stage": "trip", "operation": "advance", "expected_revision": 1})
    code, body = call(client, "GET", f"{base}/read/decision/fit?places=a,b")
    assert code == 200 and body == {"operation": "fit", "payload": {"places": "a,b"}}


def test_logistics_lookups_need_no_journey(client):
    code, rows = call(client, "GET", "/api/harness/geo?q=B%E1%BA%BFn%20Th%C3%A0nh")
    assert code == 200 and rows[0]["text"] == "Bến Thành" and rows[0]["source"] == "photon"
    code, rows = call(client, "GET", "/api/harness/lodging/suggest?q=Ana")
    assert code == 200 and rows[0]["kind"] == "address"
    assert call(client, "GET", "/api/harness/transit?mode=boat&from=SGN&to=DLI&date=2026-11-12")[0] == 400
    code, body = call(client, "GET", "/api/harness/transit?mode=plane&from=SGN&to=DLI&date=2026-11-12")
    assert code == 200 and body["status"] == "pending" and body["book_url"]
    assert call(client, "GET", "/api/harness/rentals?mode=car")[0] == 400
    code, body = call(client, "GET", "/api/harness/rentals?mode=bus")
    assert code == 200 and body["status"] in ("ready", "none") and body["hub"]["text"] == "Bến xe Liên tỉnh Đà Lạt"


def test_transit_events_push_one_event_when_the_crawl_lands(client, monkeypatch):
    from harness import server
    monkeypatch.setattr(server, "TRANSIT_POLL_S", 0.01)
    client.request("GET", "/api/harness/transit/events?mode=plane&from=SGN&to=DLI&date=2026-11-12",
                   headers=headers(Accept="text/event-stream"))
    response = client.getresponse()
    assert response.status == 200 and response.getheader("Content-Type").startswith("text/event-stream")
    events = [json.loads(line[6:]) for line in response.read().decode().splitlines() if line.startswith("data: ")]
    assert len(events) == 1
    assert events[0]["status"] == "ready" and events[0]["trips"][0]["carrier"] == "Vietjet"


def test_transit_events_give_up_as_unavailable(client, monkeypatch):
    from harness import server
    monkeypatch.setattr(server, "TRANSIT_POLL_S", 0.01)
    monkeypatch.setattr(server, "TRANSIT_WAIT_S", 0.0)
    client.request("GET", "/api/harness/transit/events?mode=bus&from=S%C3%A0i%20G%C3%B2n&to=L%C3%A2m%20%C4%90%E1%BB%93ng&date=2026-11-12",
                   headers=headers())
    response = client.getresponse()
    events = [json.loads(line[6:]) for line in response.read().decode().splitlines() if line.startswith("data: ")]
    assert events == [{"status": "unavailable", "book_url": "https://book", "trips": []}]


def test_every_harness_route_needs_a_session(client):
    for method, path in (("GET", "/api/harness/me"), ("GET", "/api/harness/trips"), ("GET", "/api/harness/places?q=a"),
                         ("POST", "/api/harness/sessions"), ("PATCH", "/api/harness/me"), ("DELETE", "/api/harness/me")):
        assert call(client, method, path, {}, token=None)[0] == 401, path
        assert call(client, method, path, {}, token="forged")[0] == 401, path


def test_another_accounts_journey_is_not_found(client):
    _, view = call(client, "POST", "/api/harness/sessions", {})
    base = f"/api/harness/sessions/{view['id']}"
    req = {"request_id": "t", "stage": "trip", "operation": "turn", "expected_revision": 0, "payload": {"kind": "show"}}
    assert call(client, "GET", base, token="tok-b")[0] == 404
    assert call(client, "GET", f"{base}/preview", token="tok-b")[0] == 404
    assert call(client, "GET", f"{base}/read/decision/page", token="tok-b")[0] == 404
    assert call(client, "POST", f"{base}/request", req, token="tok-b")[0] == 404
    assert call(client, "POST", f"{base}/feedback", {"scores": {"fit": 5}}, token="tok-b")[0] == 404
    client.request("POST", f"{base}/request", json.dumps(req), headers("tok-b", Accept="text/event-stream"))
    response = client.getresponse()
    assert response.status == 404
    response.read()
    assert call(client, "GET", base)[0] == 200


def test_mutations_need_the_apps_origin(client):
    assert call(client, "POST", "/api/harness/sessions", {}, origin=None)[0] == 403
    assert call(client, "POST", "/api/harness/sessions", {}, origin="https://evil.example")[0] == 403
    assert call(client, "POST", "/api/auth/logout", {}, origin="https://evil.example")[0] == 403
    assert call(client, "GET", "/api/harness/trips", origin=None)[0] == 200  # reads carry no Origin requirement


def test_start_takes_the_user_from_the_session_not_the_body(client):
    assert call(client, "POST", "/api/harness/sessions", {"user_id": USERS["tok-b"]})[0] == 400
    assert call(client, "POST", "/api/harness/sessions", {"remember": True})[0] == 400


def test_logout_clears_the_cookie(client):
    client.request("POST", "/api/auth/logout", "{}", headers())
    response = client.getresponse()
    assert response.status == 200 and "tg_session=;" in response.getheader("Set-Cookie")
    response.read()


def test_test_login_route_is_off_unless_enabled(client):
    assert call(client, "GET", "/api/auth/test/login?email=a@b.c")[0] == 404


def test_profile_patch_avatar_cap_and_two_step_delete(client, server_parts, monkeypatch):
    from harness import server
    assert call(client, "PATCH", "/api/harness/me", {"home_city": "Huế"}) == (200, {"id": USERS["tok-a"], "home_city": "Huế"})
    assert call(client, "PATCH", "/api/harness/me", {"role": "admin"})[0] == 400
    monkeypatch.setattr(server, "AVATAR_MAX_BYTES", 10)
    client.request("POST", "/api/harness/me/avatar", b"x" * 11, headers(**{"Content-Type": "image/png"}))
    response = client.getresponse()
    assert response.status == 413
    response.read()
    client.request("POST", "/api/harness/me/avatar", b"x" * 10, headers(**{"Content-Type": "image/png"}))
    response = client.getresponse()
    assert response.status == 200 and json.loads(response.read())["bytes"] == 10
    assert call(client, "DELETE", "/api/harness/me", {})[0] == 400
    assert call(client, "DELETE", "/api/harness/me", {"confirm": True}) == (200, {"deleted": True})
    assert server_parts[2].deleted == [USERS["tok-a"]]


def test_new_journey_gets_the_profile_as_a_trip_prior(client, server_parts):
    _, tools, _ = server_parts
    _, view = call(client, "POST", "/api/harness/sessions", {})
    sent = tools["trip"].states[view["sessions"]["trip"]]["input"]
    assert sent["user_id"] is None and sent["profile"] == {"usual_mobility": "motorbike"}  # nothing learned without consent


def test_events_route_takes_anonymous_landing_batches_but_not_cross_origin(client):
    batch = {"events": [{"name": "page_view", "props": {"route": "/"}}]}
    assert call(client, "POST", "/api/harness/events", batch, token=None) == (200, {"stored": 0})
    assert call(client, "POST", "/api/harness/events", batch, token=None, origin="https://evil.example")[0] == 403
    assert call(client, "GET", "/api/harness/events", token=None)[0] == 404
    assert call(client, "POST", "/api/harness/me/consent", {"version": "x"}, token=None)[0] == 401


def test_calendar_apply_answers_409_with_the_new_preview_when_stale(client, server_parts):
    harness = server_parts[0]

    class Cal:
        def apply(self, jid, uid, plan, h):
            return {"stale": True, "preview": {"preview_hash": "new"}}

    harness.calendar = Cal()
    harness._confirmed = lambda jid, owner, op="checkin": type("S", (), {"outputs": {"planning": {}}})()
    code, body = call(client, "POST", "/api/harness/calendar/apply", {"journey": "0123456789ab", "preview_hash": "old"})
    assert code == 409 and body["preview"] == {"preview_hash": "new"}


def test_notification_routes_need_a_session_and_reach_notify(client, server_parts):
    harness = server_parts[0]

    class N:
        resumed, opened = [], []

        def resume(self, uid):
            self.resumed.append(uid)

        def inbox(self, uid):
            return [{"id": "1"}]

        def open(self, uid, nid, action):
            self.opened.append((uid, nid))
            return {"opened": True}

        def set_prefs(self, uid, patch):
            return {"paused": patch.get("paused", False), "kinds": ["a", "b"], "enabled_kinds": ["a"]}

    harness.notify = N()
    assert call(client, "GET", "/api/harness/notifications") == (200, [{"id": "1"}])
    assert call(client, "GET", "/api/harness/notifications", token=None)[0] == 401
    nid = "0f0e0d0c-0b0a-4908-8706-050403020100"
    assert call(client, "POST", f"/api/harness/notifications/{nid}/open", {}) == (200, {"opened": True})
    assert call(client, "PATCH", "/api/harness/me/notification-prefs", {"paused": True}) == \
        (200, {"paused": True, "kinds": ["a", "b"], "enabled_kinds": ["a"]})
    call(client, "GET", "/api/harness/me")
    assert harness.notify.resumed == [USERS["tok-a"]]


def test_saved_places_are_per_account_and_mutations_need_the_app_origin(client):
    assert call(client, "GET", "/api/harness/me/saved") == (200, {"saved": []})
    assert call(client, "POST", "/api/harness/me/saved", {"place_ids": ["0x1:0xa"]}, origin="http://evil.test")[0] == 403
    assert call(client, "POST", "/api/harness/me/saved", {"place_ids": ["0x1:0xa", "0x2:0xb"]}) == \
        (200, {"saved": ["0x1:0xa", "0x2:0xb"]})
    assert call(client, "POST", "/api/harness/me/saved", {"ids": []})[0] == 400
    assert call(client, "GET", "/api/harness/me/saved", token="tok-b") == (200, {"saved": []})
    assert call(client, "DELETE", "/api/harness/me/saved/0x1%3A0xa", origin="http://evil.test")[0] == 403
    assert call(client, "DELETE", "/api/harness/me/saved/0x1%3A0xa") == (200, {"saved": ["0x2:0xb"]})
    assert call(client, "GET", "/api/harness/me/saved", token=None)[0] == 401


# --- guests: one trial journey, no history, no account features -------------------------------------------------------

def test_guest_start_sets_a_one_day_cookie_and_is_not_repeated_for_a_session(client, server_parts):
    client.request("POST", "/api/auth/guest", "{}", headers(token=None))
    response = client.getresponse()
    assert response.status == 200 and json.loads(response.read())["role"] == "guest"
    cookie = response.getheader("Set-Cookie")
    assert "tg_session=tok-g" in cookie and "Max-Age=86400" in cookie
    assert call(client, "POST", "/api/auth/guest", {}, token="tok-g")[0] == 200
    assert call(client, "POST", "/api/auth/guest", {}, token="tok-a")[0] == 200
    assert server_parts[2].guests == 1  # a session that already exists does not make another guest
    assert call(client, "POST", "/api/auth/guest", {}, token=None, origin="https://evil.example")[0] == 403


def test_a_guest_gets_one_journey_and_no_history(client):
    code, view = call(client, "POST", "/api/harness/sessions", {}, token="tok-g")
    assert code == 200
    assert call(client, "GET", f"/api/harness/sessions/{view['id']}", token="tok-g")[0] == 200
    code, body = call(client, "POST", "/api/harness/sessions", {}, token="tok-g")
    assert code == 409 and body["error"] == "guest_limit"
    assert call(client, "GET", "/api/harness/trips", token="tok-g") == (200, [])
    assert call(client, "POST", "/api/harness/sessions", {}, token="tok-a")[0] == 200  # accounts are not limited
    assert call(client, "POST", "/api/harness/sessions", {}, token="tok-a")[0] == 200


def test_a_guest_cannot_use_account_features(client):
    for method, path, body in (("GET", "/api/harness/me/saved", None), ("POST", "/api/harness/me/saved", {"place_ids": ["p"]}),
                               ("PATCH", "/api/harness/me", {"home_city": "Huế"}), ("DELETE", "/api/harness/me", {"confirm": True}),
                               ("POST", "/api/harness/me/consent", {"version": "x"}),
                               ("POST", "/api/harness/calendar/apply", {"journey": "a" * 12}),
                               ("POST", "/api/harness/calendar/disconnect", {})):
        code, out = call(client, method, path, body, token="tok-g")
        assert (code, out["error"]) == (403, "sign_in_required"), path


# --- remembering choices across trips (docs/P2_TRIP_UNDERSTANDING.md §17) --------------------------------------------------

def test_the_choice_to_remember_is_set_apart_from_the_terms_and_must_be_a_boolean(client, server_parts):
    _, _, accounts = server_parts
    assert call(client, "POST", "/api/harness/me/consent", {"patterns": True})[0] == 200
    assert accounts.patterns == {USERS["tok-a"]: True}
    assert call(client, "POST", "/api/harness/me/consent", {"patterns": "yes"})[0] == 400
    assert call(client, "POST", "/api/harness/me/consent", {})[0] == 400
    assert call(client, "POST", "/api/harness/me/consent", {"version": "old"})[0] == 400
    assert call(client, "POST", "/api/harness/me/consent", {"version": "v1", "patterns": False})[0] == 200
    assert accounts.patterns[USERS["tok-a"]] is False


def test_a_journey_learns_and_is_seeded_only_for_someone_who_agreed(client, server_parts):
    _, tools, _ = server_parts
    call(client, "POST", "/api/harness/sessions", {})
    call(client, "POST", "/api/harness/me/consent", {"patterns": True})
    call(client, "POST", "/api/harness/sessions", {})
    inputs = [v["input"] for v in tools["trip"].states.values()]
    assert (inputs[0]["user_id"], inputs[0]["remember"]) == (None, False)
    assert (inputs[1]["user_id"], inputs[1]["remember"]) == (USERS["tok-a"], True)
