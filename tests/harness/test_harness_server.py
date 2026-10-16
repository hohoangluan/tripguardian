import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from accounts import AuthError

from test_dispatch import make


ORIGIN = "http://app.test"
USERS = {"tok-a": "a" * 32, "tok-b": "b" * 32}
GUESTS = {"tok-g": "c" * 32}


class FakeAccounts:
    """Sessions tok-a / tok-b; the real service is covered in tests/accounts."""
    def __init__(self):
        self.logged_out, self.deleted, self.dropped, self.guests_made = [], [], [], 0

    def user_for(self, token):
        if token in USERS:
            return {"id": USERS[token], "role": "user", "guest": False}, False
        if token in GUESTS:
            return {"id": GUESTS[token], "role": "user", "guest": True}, False
        return None, False

    def guest(self, user_agent=""):
        self.guests_made += 1
        return "tok-g"

    def register(self, email, password, name="", user_agent=""):
        if email == "taken@x.vn":
            raise ValueError("email is taken")
        if len(password) < 8:
            raise ValueError("password must have 8-128 characters")
        return "tok-a"

    def login_password(self, email, password, user_agent=""):
        if (email, password) != ("a@x.vn", "mat-khau-dai"):
            raise AuthError("wrong email or password")
        return "tok-a"

    def leave(self, token):
        self.left = [*getattr(self, "left", []), token]

    def drop_guest(self, uid):
        self.dropped.append(uid)
        return uid in GUESTS.values()

    def me(self, uid):
        return {"id": uid, "consents": {}, "usual_mobility": "motorbike", "usual_companions": None}

    def update(self, uid, patch):
        if set(patch) - {"home_city"}:
            raise ValueError("unknown profile field")
        return {"id": uid, **patch}

    def set_avatar(self, uid, data):
        return {"id": uid, "bytes": len(data)}

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


def test_evidence_http_is_typed_owner_scoped_and_read_only(client, server_parts):
    from decision import Data, Engine, Store, Tools, load_settings
    from fixtures import srec
    from test_dispatch import run

    harness, _, _ = server_parts
    engine = Engine(Data([srec("cafe", features={"scenic_view": "present"})]), load_settings(), Store(None))
    tools = Tools(engine)
    harness.tools["decision"] = tools
    _, view = call(client, "POST", "/api/harness/sessions", {})
    view = run(harness, view, "turn", "compile", {"kind": "show"})
    view = run(harness, view, "advance", "decision")
    before = tools.snapshot(view["sessions"]["decision"])
    path = f"/api/harness/sessions/{view['id']}/read/decision/evidence?place=cafe&feature=scenic_view"

    code, result = call(client, "GET", path)

    assert code == 200
    assert result["place_id"] == "cafe" and result["status"] == "VERIFIED"
    assert result["reason"] == "legacy_lineage_unavailable" and result["items"] == []
    assert tools.snapshot(view["sessions"]["decision"]) == before
    assert harness.load(view["id"])["revision"] == view["revision"]
    assert call(client, "GET", path, token="tok-b")[0] == 404
    assert call(client, "GET", path, token=None)[0] == 401
    assert call(client, "GET", path + "&bad=1")[0] == 400


def test_real_preview_http_enforces_owner_input_and_read_only_revision(client, server_parts):
    from urllib.parse import quote
    from plan_fixtures import CFG, FakeLive, no_geocode, fake_matrix, spot, CENTRE
    from planning import Engine, Tools
    from decision import Data, Engine as DecisionEngine, Store, Tools as DecisionTools, load_settings
    from test_dispatch import run
    harness, tools, _ = server_parts
    records = [spot('place-1', CENTRE, 0)]
    records[0]['provenance'] = {'voices': 1}
    harness.tools['decision'] = DecisionTools(DecisionEngine(Data(records), load_settings(), Store(None)))
    pt = Tools(Engine(records, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode,
                     matrix_fn=fake_matrix, sun_fn=lambda *a: (360, 1050),
                     background=False))
    harness.tools['planning'] = pt
    _, v = call(client, 'POST', '/api/harness/sessions', {})
    v = run(harness, v, 'turn', 'compile', {'kind': 'show'})
    v = run(harness, v, 'advance', 'decision')
    v = run(harness, v, 'act', 'select', {'type': 'select', 'place_id': 'place-1'})
    v = run(harness, v, 'advance', 'planning')
    variant = v['result']['view']['variants'][0]['id']
    v = run(harness, v, 'act', 'pick', {'type': 'pick_variant', 'id': variant})
    sid = v['sessions']['planning']
    before = pt.snapshot(sid)
    path = f"/api/harness/sessions/{v['id']}/read/planning/preview-act?action="
    action = quote(json.dumps({'type': 'drop_place', 'place': 'place-1'}))
    status, preview = call(client, 'GET', path + action)
    assert status == 200 and preview['revision'] == v['revision']
    assert preview['token'] and pt.snapshot(sid) == before
    assert harness.load(v['id'])['revision'] == v['revision']
    assert call(client, 'GET', path + action, token='tok-b')[0] == 404
    assert call(client, 'GET', path + action, token=None)[0] == 401
    for raw in ('{', '[]', 'x' * 8193):
        assert call(client, 'GET', path + quote(raw))[0] == 400
    assert pt.snapshot(sid) == before


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


def test_trip_readback_is_a_read(client):
    """The "Trước khi lập lịch" sheet reads the remaining gate after a partial required answer (ui/ReadbackSheet.tsx)."""
    _, view = call(client, "POST", "/api/harness/sessions", {})
    base = f"/api/harness/sessions/{view['id']}"
    code, body = call(client, "GET", f"{base}/read/trip/readback")
    assert code == 200 and body["operation"] == "readback"
    assert call(client, "GET", f"{base}/read/trip/readback", token="tok-b")[0] == 404
    assert call(client, "GET", f"{base}/read/trip/compare")[0] == 404  # only the read-back is open on the trip stage


def test_logistics_lookups_need_no_journey(client):
    code, rows = call(client, "GET", "/api/harness/geo?q=B%E1%BA%BFn%20Th%C3%A0nh")
    assert code == 200 and rows[0]["text"] == "Bến Thành" and rows[0]["source"] == "photon"
    code, rows = call(client, "GET", "/api/harness/lodging/suggest?q=Ana")
    assert code == 200 and rows[0]["kind"] == "address"
    assert call(client, "GET", "/api/harness/transit?mode=plane&from=SGN&to=DLI&date=2026-11-12")[0] == 404  # no coach / flight flow


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
    assert sent["user_id"] == USERS["tok-a"] and sent["profile"] == {"usual_mobility": "motorbike"}


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


def start_guest(client, origin=ORIGIN, token=None):
    client.request("POST", "/api/auth/guest", "{}", headers(token, origin))
    response = client.getresponse()
    return response.status, json.loads(response.read()), response.getheader("Set-Cookie")


def test_guest_starts_with_a_session_cookie_and_only_from_the_own_origin(client, server_parts):
    _, _, accounts = server_parts
    code, body, cookie = start_guest(client)
    assert code == 200 and body == {"started": True} and accounts.guests_made == 1
    assert cookie.startswith("tg_session=tok-g;") and "Max-Age" not in cookie and "HttpOnly" in cookie  # a session cookie: gone when the browser closes
    assert start_guest(client, origin=None)[0] == 403 and accounts.guests_made == 1
    # a session already open in this browser ends and a new, empty guest starts: never an inherited identity
    code, body, cookie = start_guest(client, token="tok-a")
    assert (code, body) == (200, {"started": True}) and cookie.startswith("tg_session=tok-g;")
    assert accounts.guests_made == 2 and accounts.logged_out == ["tok-a"]


def test_guest_starts_are_not_limited_per_address(client, server_parts):
    # The per-address guest cap is gone (user, 2026-10-15): visitors behind one school or event network share an
    # address and were refused after 20. The same-origin check and the request rate limits still apply.
    assert [start_guest(client)[0] for _ in range(25)] == [200] * 25


def test_guest_plans_but_not_with_members_only_features(client):
    code, view = call(client, "POST", "/api/harness/sessions", {}, token="tok-g")
    assert code == 200 and view["stage"] == "trip"
    assert call(client, "GET", f"/api/harness/sessions/{view['id']}", token="tok-g")[0] == 200
    for path in ("/api/harness/notifications", "/api/harness/push/key", "/api/harness/me/notification-prefs",
                 "/api/harness/calendar/preview?journey=x", f"/api/harness/sessions/{view['id']}/today"):
        code, body = call(client, "GET", path, token="tok-g")
        assert (code, body["error"]) == (403, "guest"), path
    for path in ("/api/harness/calendar/apply", "/api/harness/push/subscribe", "/api/harness/calendar/disconnect",
                 f"/api/harness/sessions/{view['id']}/companion"):
        assert call(client, "POST", path, {}, token="tok-g")[0] == 403, path
    assert call(client, "PATCH", "/api/harness/me", {"home_city": "Huế"}, token="tok-g")[0] == 403
    assert call(client, "PATCH", "/api/harness/me", {"home_city": "Huế"}, token="tok-a")[0] == 200


def test_guest_journey_has_no_profile_prior_and_no_learning(client, server_parts, monkeypatch):
    harness, _, _ = server_parts
    seen = []
    real = harness.create
    monkeypatch.setattr(harness, "create", lambda *args: seen.append(args) or real(*args))
    call(client, "POST", "/api/harness/sessions", {}, token="tok-g")
    call(client, "POST", "/api/harness/sessions", {}, token="tok-a")
    guest_args, member_args = seen
    assert guest_args[3] is False and guest_args[5] == {}  # remember, profile prior
    assert member_args[5] == {"usual_mobility": "motorbike"}


def test_guest_journeys_are_not_capped(client):
    for _ in range(6):
        assert call(client, "POST", "/api/harness/sessions", {}, token="tok-g")[0] == 200
    assert len(call(client, "GET", "/api/harness/trips", token="tok-g")[1]) == 6


def test_guest_delete_ends_the_visit_and_an_account_still_asks_for_confirm(client, server_parts):
    _, _, accounts = server_parts
    assert call(client, "DELETE", "/api/harness/me", {}, token="tok-g") == (200, {"deleted": True})
    assert accounts.dropped == [GUESTS["tok-g"]] and accounts.deleted == []
    assert call(client, "DELETE", "/api/harness/me", {}, token="tok-a")[0] == 400


def test_sign_in_moves_the_guest_journeys_to_the_account(client, server_parts):
    harness, _, _ = server_parts
    _, view = call(client, "POST", "/api/harness/sessions", {}, token="tok-g")
    assert harness.adopt(GUESTS["tok-g"], USERS["tok-a"]) == 1
    assert [s["id"] for s in call(client, "GET", "/api/harness/trips", token="tok-a")[1]] == [view["id"]]
    assert call(client, "GET", "/api/harness/trips", token="tok-g")[1] == []
    assert call(client, "GET", f"/api/harness/sessions/{view['id']}", token="tok-g")[0] == 404
    assert call(client, "GET", f"/api/harness/sessions/{view['id']}", token="tok-a")[0] == 200


class FakeSocial:
    def __init__(self):
        self.sent, self.marked = [], []

    def friends(self, uid):
        return {"friends": [], "incoming": [], "outgoing": [], "uid": uid}

    def send(self, uid, other, text, journey):
        self.sent.append((uid, other, text, journey))
        return {"id": 1}

    def shared(self, uid, mid):
        if mid != 7:
            raise KeyError(mid)
        return self.owner, self.jid, None

    def imported(self, mid, jid):
        self.marked.append((mid, jid))


def test_friends_and_messages_are_for_members_and_a_shared_trip_is_copied(server_parts):
    from harness.server import handler
    harness, _, accounts = server_parts
    social = FakeSocial()
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(harness, accounts, ORIGIN, social=social))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    c = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    try:
        assert call(c, "GET", "/api/harness/friends", token="tok-g")[0] == 403
        assert call(c, "GET", "/api/harness/friends")[1]["uid"] == USERS["tok-a"]
        _, mine = call(c, "POST", "/api/harness/sessions", {})
        _, theirs = call(c, "POST", "/api/harness/sessions", {}, token="tok-b")
        friend = USERS["tok-b"]
        assert call(c, "POST", f"/api/harness/messages/{friend}", {"text": "x", "journey": theirs["id"]})[0] == 400
        assert call(c, "POST", f"/api/harness/messages/{friend}", {"text": "đây", "journey": mine["id"]})[0] == 200
        assert social.sent == [(USERS["tok-a"], friend, "đây", mine["id"])]
        social.owner, social.jid = USERS["tok-a"], mine["id"]
        status, out = call(c, "POST", "/api/harness/messages/7/import", {}, token="tok-b")
        assert status == 200 and social.marked == [(7, out["id"])]
        assert call(c, "GET", f"/api/harness/sessions/{out['id']}", token="tok-b")[0] == 200
        assert call(c, "POST", "/api/harness/messages/8/import", {}, token="tok-b")[0] == 404
    finally:
        c.close()
        server.shutdown()
        server.server_close()


def post_auth(client, path, data, token=None, origin=ORIGIN):
    client.request("POST", path, json.dumps(data), headers(token, origin))
    response = client.getresponse()
    return response.status, json.loads(response.read()), response.getheader("Set-Cookie")


def test_email_register_and_login_set_a_session_cookie(client):
    code, body, cookie = post_auth(client, "/api/auth/register", {"email": "n@x.vn", "password": "mat-khau-dai", "name": "N"})
    assert (code, body) == (200, {"signed_in": True}) and cookie.startswith("tg_session=tok-a;") and "Max-Age=2592000" in cookie
    code, body, cookie = post_auth(client, "/api/auth/login", {"email": "a@x.vn", "password": "mat-khau-dai"})
    assert code == 200 and cookie.startswith("tg_session=tok-a;")


def test_email_auth_answers_clearly_and_only_from_the_own_origin(client):
    assert post_auth(client, "/api/auth/register", {"email": "taken@x.vn", "password": "mat-khau-dai"})[0] == 409
    assert post_auth(client, "/api/auth/register", {"email": "n@x.vn", "password": "short"})[0] == 400
    assert post_auth(client, "/api/auth/register", {"email": 1, "password": "mat-khau-dai"})[0] == 400
    code, body, cookie = post_auth(client, "/api/auth/login", {"email": "a@x.vn", "password": "sai"})
    assert (code, body["error"], cookie) == (401, "wrong email or password", None)
    assert post_auth(client, "/api/auth/login", {"email": "a@x.vn", "password": "mat-khau-dai"}, origin=None)[0] == 403


def test_wrong_passwords_for_one_email_wait(client, monkeypatch):
    from harness import server
    monkeypatch.setattr(server, "AUTH_FAILS_15MIN", 3)
    codes = [post_auth(client, "/api/auth/login", {"email": "a@x.vn", "password": "sai"})[0] for _ in range(5)]
    assert codes == [401, 401, 401, 429, 429]
    assert post_auth(client, "/api/auth/login", {"email": "a@x.vn", "password": "mat-khau-dai"})[0] == 429
    assert post_auth(client, "/api/auth/login", {"email": "other@x.vn", "password": "sai"})[0] == 401


def test_signing_in_by_email_hands_a_guests_trips_to_the_account(client, server_parts):
    harness, _, accounts = server_parts
    code, _, _ = post_auth(client, "/api/auth/login", {"email": "a@x.vn", "password": "mat-khau-dai"}, token="tok-g")
    assert code == 200 and accounts.dropped == [GUESTS["tok-g"]]


def test_a_guest_page_reports_it_is_closing_or_alive_from_its_own_origin_only(client, server_parts):
    _, _, accounts = server_parts
    assert post_auth(client, "/api/auth/guest/leave", {}, token="tok-g")[0] == 200 and accounts.left == ["tok-g"]
    assert post_auth(client, "/api/auth/guest/alive", {}, token="tok-g")[0] == 200 and accounts.left == ["tok-g"]
    assert post_auth(client, "/api/auth/guest/leave", {}, token="tok-g", origin=None)[0] == 403 and accounts.left == ["tok-g"]
