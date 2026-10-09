"""Local journey HTTP/SSE boundary; the router owns stage permissions, accounts own sign-in (docs/ACCOUNTS.md).

Every /api/harness/* call needs a signed-in session (cookie tg_session); /api/auth/* is the sign-in flow itself.
Mutations must come from the app's own origin. Another account's journey is answered 404, as if it did not exist.
"""

import json
import re
import sys
import time
import traceback
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from pydantic import ValidationError
from accounts import AVATAR_MAX_BYTES, AuthError, safe_next
from agents import ToolError
from companion import CalendarError, NotConnected

from .contracts import Request
from .dispatch import Conflict
from .router import RouteError, route

BASE = "/api/harness/sessions"
PROFILE = re.compile(r"/api/harness/profile/([A-Za-z0-9_-]{8,64})")
AVATAR = re.compile(r"/api/harness/avatars/([0-9a-f]{32})")
SESSION = re.compile(BASE + r"/([0-9a-f]{12})")
REQUEST = re.compile(BASE + r"/([0-9a-f]{12})/request")
READ = re.compile(BASE + r"/([0-9a-f]{12})/read/(decision|planning)/(compare|why-not|lodging|variants|page)")
LODGING = re.compile(BASE + r"/([0-9a-f]{12})/planning/lodging/events")
PREVIEW = re.compile(BASE + r"/([0-9a-f]{12})/preview")
FEEDBACK = re.compile(BASE + r"/([0-9a-f]{12})/feedback")
TODAY = re.compile(BASE + r"/([0-9a-f]{12})/today")
SUGGEST = re.compile(BASE + r"/([0-9a-f]{12})/companion/suggest")
COMPANION = re.compile(BASE + r"/([0-9a-f]{12})/companion")
NOTE_OPEN = re.compile(r"/api/harness/notifications/([0-9a-f-]{36})/open")
MAX_BODY = 65536
TRANSIT_WAIT_S = 90  # a live flight crawl takes ~5-40 s; past this the stream says unavailable
TRANSIT_POLL_S = 0.5
COOKIE = "tg_session"
STATE_COOKIE = "tg_oauth"
SESSION_MAX_AGE = 30 * 86400


class StalePreview(Exception):
    def __init__(self, preview: dict):
        super().__init__("stale preview")
        self.preview = preview


def handler(harness, accounts, base_url: str = "", test_login: bool = False):
    """base_url: the public origin (APP_BASE_URL); https makes cookies Secure. test_login enables
    GET /api/auth/test/login for browser walk-throughs and is refused on an https base URL."""
    secure = "; Secure" if base_url.startswith("https://") else ""
    base = urlparse(base_url)
    base_origin = f"{base.scheme}://{base.netloc}" if base.netloc else None
    test_login = test_login and not secure

    def cookie(name, value, max_age, path="/"):
        return f"{name}={value}; HttpOnly; SameSite=Lax; Path={path}; Max-Age={max_age}{secure}"

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body: bytes, content_type, headers=()):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for name, value in [*self._set, *headers]:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, value):
            self._send(code, json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def _redirect(self, location):
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            for name, value in self._set:
                self.send_header(name, value)
            self.end_headers()

        def _cookie(self, name):
            jar = SimpleCookie()
            try:
                jar.load(self.headers.get("Cookie", ""))
            except Exception:
                return None
            return jar[name].value if name in jar else None

        def _user(self):
            """The signed-in account or None; a session idle for a while gets its cookie re-sent (sliding 30 days)."""
            token = self._cookie(COOKIE)
            user, refreshed = accounts.user_for(token)
            if refreshed:
                self._set.append(("Set-Cookie", cookie(COOKIE, token, SESSION_MAX_AGE)))
            return user

        def _same_origin(self):
            origin = self.headers.get("Origin")
            if not origin:
                return False
            return origin == base_origin or urlparse(origin).netloc == self.headers.get("Host")

        def _body(self):
            size = int(self.headers.get("Content-Length") or 0)
            if not 0 <= size <= MAX_BODY:
                raise ValueError("request body too large")
            body = json.loads(self.rfile.read(size) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("body must be a JSON object")
            return body

        def _raw(self, limit):
            size = int(self.headers.get("Content-Length") or 0)
            if not 0 < size <= limit:
                raise ValueError(f"body must be 1 byte to {limit // (1024 * 1024)} MB")
            return self.rfile.read(size)

        def _call(self, fn):
            try:
                return self._json(200, fn())
            except KeyError:
                return self._json(404, {"error": "no such session"})
            except (Conflict, RouteError) as exc:
                return self._json(409, {"error": str(exc)})
            except ToolError as exc:
                return self._json(exc.status, {"error": str(exc)})
            except StalePreview as exc:  # the user saw an older preview: show the new one, write nothing
                return self._json(409, {"error": "the calendar changes differ from the preview you saw",
                                        "preview": exc.preview})
            except NotConnected as exc:
                return self._json(409, {"error": str(exc), "connect": "/api/auth/google/start?purpose=calendar"})
            except CalendarError as exc:
                return self._json(502, {"error": str(exc)})
            except (ValueError, ValidationError) as exc:
                return self._json(400, {"error": str(exc).splitlines()[0]})
            except Exception:
                traceback.print_exc(file=sys.stderr)
                return self._json(500, {"error": "server error"})

        def _stream_headers(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Connection", "close")
            for name, value in self._set:
                self.send_header(name, value)
            self.end_headers()
            self.close_connection = True

        def _event(self, value):
            try:
                self.wfile.write(f"event: event\ndata: {json.dumps(value, ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()
            except OSError:
                pass  # finish and commit the request even when its browser disconnects

        def _begin(self, mutation):
            """(path, query, user) for an /api/harness/* call, or None after answering 401 / 403 / 404."""
            self._set = []
            url = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            if url.path.startswith("/api/auth/"):
                return url.path, query, None
            if not url.path.startswith("/api/harness/"):
                self._json(404, {"error": "not found"})
                return None
            user = self._user()
            if not user and url.path == "/api/harness/events":
                user = {"id": None, "role": "anonymous"}  # the public landing may report page_view / landing_cta
            if not user:
                self._json(401, {"error": "sign in first"})
                return None
            if mutation and not self._same_origin():
                self._json(403, {"error": "cross-origin request refused"})
                return None
            return url.path, query, user

        # --- sign-in ------------------------------------------------------------------------------------------

        def _auth_get(self, path, query):
            if path == "/api/auth/google/start":
                purpose = query.get("purpose", "login")
                uid = None
                if purpose == "calendar":
                    user = self._user()
                    if not user:
                        return self._json(401, {"error": "sign in first"})
                    uid = user["id"]
                try:
                    state, url = accounts.start(purpose, query.get("next"), uid)
                except AuthError as exc:
                    return self._json(400, {"error": str(exc)})
                self._set.append(("Set-Cookie", cookie(STATE_COOKIE, state, 600, "/api/auth")))
                return self._redirect(url)
            if path == "/api/auth/google/callback":
                self._set.append(("Set-Cookie", cookie(STATE_COOKIE, "", 0, "/api/auth")))
                state = query.get("state", "")
                if not state or state != self._cookie(STATE_COOKIE):
                    return self._redirect("/app/login?error=state")
                try:
                    if "error" in query or not query.get("code"):
                        raise AuthError(query.get("error", "no code"))
                    out = accounts.callback(state, query["code"], self.headers.get("User-Agent", ""))
                except AuthError as exc:
                    print(f"sign-in refused: {exc}", file=sys.stderr)
                    if exc.purpose == "calendar":
                        sep = "&" if "?" in exc.next else "?"
                        return self._redirect(f"{exc.next}{sep}calendar=failed")
                    return self._redirect("/app/login?error=" + ("denied" if "access_denied" in str(exc) else "failed"))
                if out["purpose"] == "login":
                    self._set.append(("Set-Cookie", cookie(COOKIE, out["token"], SESSION_MAX_AGE)))
                    harness._event("auth.login", (accounts.user_for(out["token"])[0] or {}).get("id"), None)
                    return self._redirect(out["next"])
                harness._event("calendar.connect", None, None)
                sep = "&" if "?" in out["next"] else "?"
                return self._redirect(f"{out['next']}{sep}calendar=connected")
            if path == "/api/auth/test/login" and test_login:
                email = query.get("email", "walker@test.local")
                token = accounts.test_login(email, query.get("name", "Walker"), self.headers.get("User-Agent", ""))
                self._set.append(("Set-Cookie", cookie(COOKIE, token, SESSION_MAX_AGE)))
                return self._redirect(safe_next(query.get("next")))
            return self._json(404, {"error": "not found"})

        # --- routes -------------------------------------------------------------------------------------------

        def do_GET(self):
            begun = self._begin(False)
            if not begun:
                return
            path, query, user = begun
            if user is None:
                return self._auth_get(path, query)
            owner = user["id"]
            if path == "/api/harness/me":
                if harness.notify is not None:
                    harness.notify.resume(owner)  # the user opened the app: a notification pause ends
                return self._call(lambda: accounts.me(owner))
            if path == "/api/harness/me/notification-prefs" and harness.notify is not None:
                return self._call(lambda: harness.notify.prefs(owner))
            if path == "/api/harness/notifications" and harness.notify is not None:
                return self._call(lambda: harness.notify.inbox(owner))
            if path == "/api/harness/push/key" and harness.notify is not None:
                return self._call(lambda: {"key": harness.notify.public_key()})
            if m := AVATAR.fullmatch(path):
                try:
                    data = accounts.avatar_path(m[1]).read_bytes()
                except KeyError:
                    return self._json(404, {"error": "not found"})
                return self._send(200, data, "image/webp")
            if path == "/api/harness/places":
                return self._call(lambda: harness.places(query.get("q", ""), owner))
            if path == "/api/harness/geo":
                return self._call(lambda: harness.geo(query.get("q", "")))
            if path == "/api/harness/lodging/suggest":
                return self._call(lambda: harness.lodging_suggest(query.get("q", "")))
            if path == "/api/harness/transit":
                return self._call(lambda: harness.transit(query))
            if path == "/api/harness/transit/events":
                try:
                    current = harness.transit(query)
                except (ValueError, ValidationError) as exc:
                    return self._json(400, {"error": str(exc).splitlines()[0]})
                self._stream_headers()
                deadline = time.monotonic() + TRANSIT_WAIT_S
                while current["status"] == "pending" and time.monotonic() < deadline:
                    time.sleep(TRANSIT_POLL_S)
                    current = harness.transit(query)
                if current["status"] == "pending":
                    current = {**current, "status": "unavailable"}
                return self._event(current)
            if path == "/api/harness/trips":
                return self._call(lambda: harness.trips(owner))
            if m := PREVIEW.fullmatch(path):
                return self._call(lambda: harness.preview(m[1], owner))
            if path == "/api/harness/calendar/preview":
                return self._call(lambda: harness.calendar_preview(query.get("journey", ""), owner))
            if m := TODAY.fullmatch(path):
                day = query.get("day")
                if day is not None and not day.isdigit():
                    return self._json(400, {"error": "day must be a number"})
                return self._call(lambda: harness.today(m[1], owner, int(day) if day else None))
            if m := SUGGEST.fullmatch(path):
                return self._call(lambda: harness.suggest(m[1], query.get("place", ""), owner, query.get("similar") == "1"))
            if m := SESSION.fullmatch(path):
                stage = query.get("stage")
                if stage not in (None, "trip", "decision", "planning"):
                    return self._json(400, {"error": "unknown stage"})
                return self._call(lambda: harness.load(m[1], stage, owner))
            if m := READ.fullmatch(path):
                return self._call(lambda: harness.read(m[1], m[2], m[3], query, owner))
            if m := LODGING.fullmatch(path):
                try:
                    harness.load(m[1], "planning", owner)
                except KeyError:
                    return self._json(404, {"error": "no such session"})
                except Conflict as exc:
                    return self._json(409, {"error": str(exc)})
                self._stream_headers()
                for _ in range(200):
                    lod = harness.read(m[1], "planning", "lodging", None, owner)
                    if lod["status"] != "pending":
                        break
                    time.sleep(0.05)
                updated = harness.load(m[1], "planning", owner)
                self._event({"stage": "planning", "revision": updated["revision"], "event": "view",
                    "data": updated["result"]["view"]})
                self._event({"stage": "planning", "revision": updated["revision"], "event": "done", "data": {}})
                return
            self._json(404, {"error": "not found"})

        def do_POST(self):
            begun = self._begin(True)
            if not begun:
                return
            path, query, user = begun
            if user is None:
                if path == "/api/auth/logout":
                    if not self._same_origin():
                        return self._json(403, {"error": "cross-origin request refused"})
                    accounts.logout(self._cookie(COOKIE))
                    self._set.append(("Set-Cookie", cookie(COOKIE, "", 0)))
                    return self._json(200, {"signed_out": True})
                return self._json(404, {"error": "not found"})
            owner = user["id"]
            if path == "/api/harness/events":
                try:
                    batch = self._body().get("events")
                    stored = harness.events.client(batch, owner) if harness.events else 0
                except ValueError as exc:
                    return self._json(400, {"error": str(exc)})
                return self._json(200, {"stored": stored})
            if owner is None:
                return self._json(401, {"error": "sign in first"})
            if path == "/api/harness/me/avatar":
                try:
                    data = self._raw(AVATAR_MAX_BYTES)
                except ValueError as exc:
                    return self._json(413, {"error": str(exc)})
                return self._call(lambda: accounts.set_avatar(owner, data))
            try:
                body = self._body()
                if path == BASE:
                    if set(body) - {"experience", "start_with"}:
                        raise ValueError("unknown start field")
                    if body.get("experience") not in (None, "first", "returning"):
                        raise ValueError("bad experience")
                    if body.get("start_with") not in (None, "nothing", "saved", "must", "itinerary"):
                        raise ValueError("bad start_with")
                    me = accounts.me(owner)
                    prior = {k: me.get(k) for k in ("usual_mobility", "usual_companions") if me.get(k)}
                    return self._call(lambda: harness.create(body.get("experience"), body.get("start_with"), owner,
                                                             me["consents"].get("patterns") is True, owner, prior))
                if path == "/api/harness/me/consent":
                    def consent():
                        out = accounts.consent(owner, body.get("version"))
                        harness._event("auth.consent", owner, None, version=body.get("version"))
                        return out
                    return self._call(consent)
                if path == "/api/harness/reports":
                    return self._call(lambda: harness.report(body))
                if fb := FEEDBACK.fullmatch(path):
                    return self._call(lambda: harness.feedback(fb[1], body, owner))
                if path == "/api/harness/calendar/apply":
                    def apply():
                        out = harness.calendar_apply(body.get("journey", ""), body.get("preview_hash"), owner)
                        if out["stale"]:
                            raise StalePreview(out["preview"])
                        return out
                    return self._call(apply)
                if harness.notify is not None and path == "/api/harness/push/subscribe":
                    return self._call(lambda: harness.notify.subscribe(owner, body.get("subscription") or {},
                                                                       self.headers.get("User-Agent", "")))
                if harness.notify is not None and path == "/api/harness/push/unsubscribe":
                    return self._call(lambda: harness.notify.unsubscribe(owner, str(body.get("endpoint", ""))))
                if harness.notify is not None and (no := NOTE_OPEN.fullmatch(path)):
                    return self._call(lambda: harness.notify.open(owner, no[1], body.get("action")))
                if path == "/api/harness/calendar/disconnect":
                    return self._call(lambda: harness.calendar_disconnect(owner, body.get("delete_calendar", False)))
                if cm := COMPANION.fullmatch(path):
                    op = body.pop("operation", None)
                    return self._call(lambda: harness.companion_act(cm[1], op, body, owner))
                m = REQUEST.fullmatch(path)
                if not m:
                    return self._json(404, {"error": "not found"})
                req = Request.model_validate(body)
            except (ValueError, ValidationError) as exc:
                return self._json(400, {"error": str(exc).splitlines()[0]})
            if "text/event-stream" not in self.headers.get("Accept", ""):
                return self._call(lambda: harness.request(m[1], req, None, owner))
            try:
                with harness.store.lock(m[1]):
                    session = harness._get(m[1], owner)
                    if req.request_id not in session.receipts:
                        if req.expected_revision != session.revision:
                            raise Conflict("stale revision")
                        route(session.stage, req)
            except KeyError:
                return self._json(404, {"error": "no such session"})
            except (RouteError, Conflict) as exc:
                return self._json(409, {"error": str(exc)})
            self._stream_headers()
            def emit(event, data):
                provisional = event in ("say", "preview")
                self._event({"request_id": req.request_id, "stage": req.stage,
                    "revision": req.expected_revision if provisional else req.expected_revision + 1,
                    "provisional": provisional, "event": event, "data": data})
            try:
                response = harness.request(m[1], req, emit, owner)
                self._event({"request_id": req.request_id, "stage": response["stage"], "revision": response["revision"],
                    "event": "journey", "data": response})
            except Exception as exc:
                status = (409 if isinstance(exc, (Conflict, RouteError)) else exc.status if isinstance(exc, ToolError)
                          else 404 if isinstance(exc, KeyError) else 400 if isinstance(exc, ValueError) else 500)
                if status == 500:
                    traceback.print_exc(file=sys.stderr)
                message = str(exc).splitlines()[0] if status < 500 else "Không xử lý được yêu cầu, bạn thử lại nhé."
                self._event({"request_id": req.request_id, "stage": req.stage, "revision": req.expected_revision,
                    "event": "error", "data": {"status": status, "message": message}})

        def do_PATCH(self):
            begun = self._begin(True)
            if not begun:
                return
            path, _, user = begun
            if user and path in ("/api/harness/me", "/api/harness/me/notification-prefs"):
                try:
                    body = self._body()
                except ValueError as exc:
                    return self._json(400, {"error": str(exc)})
                if path == "/api/harness/me":
                    return self._call(lambda: accounts.update(user["id"], body))
                if harness.notify is not None:
                    def prefs():
                        out = harness.notify.set_prefs(user["id"], body)
                        harness._event("notify.prefs", user["id"], None, paused=out["paused"],
                                       kinds_off=len(out["kinds"]) - len(out["enabled_kinds"]))
                        return out
                    return self._call(prefs)
            self._json(404, {"error": "not found"})

        def do_DELETE(self):
            begun = self._begin(True)
            if not begun:
                return
            path, _, user = begun
            if user and path == "/api/harness/me":
                try:
                    if self._body().get("confirm") is not True:
                        raise ValueError("deleting the account needs confirm: true")
                except ValueError as exc:
                    return self._json(400, {"error": str(exc)})
                harness.forget_profile(user["id"])
                accounts.delete(user["id"])
                self._set.append(("Set-Cookie", cookie(COOKIE, "", 0)))
                return self._json(200, {"deleted": True})
            if user and (m := PROFILE.fullmatch(path)):
                if m[1] != user["id"]:
                    return self._json(404, {"error": "not found"})
                return self._call(lambda: {"forgotten": harness.forget_profile(m[1])})
            self._json(404, {"error": "not found"})

        def log_message(self, *args):
            pass
    return Handler


def run(harness, accounts, port=8769, base_url="", test_login=False):
    ThreadingHTTPServer(("127.0.0.1", port), handler(harness, accounts, base_url, test_login)).serve_forever()
