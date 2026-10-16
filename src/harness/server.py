"""Local journey HTTP/SSE boundary; the router owns stage permissions, accounts own sign-in (docs/ACCOUNTS.md).

Every /api/harness/* call needs a session (cookie tg_session): a Google or email account, or a guest made by POST /api/auth/guest
(a guest plans like anyone but keeps no history and gets no Calendar, notifications or Today). /api/auth/* is the sign-in flow:
Google, or an email and a password (register / login).
Mutations must come from the app's own origin. Another account's journey is answered 404, as if it did not exist.
"""

import json
import ipaddress
import re
import sys
import threading
import time
import traceback
from collections import deque
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, quote, urlparse

from pydantic import ValidationError
from accounts import AVATAR_MAX_BYTES, AuthError, safe_next
from agents import ToolError
from companion import CalendarError, NotConnected

from .contracts import Request, TripNotReady
from .dispatch import Conflict, LIVE
from .router import RouteError, route
from .protection import ProtectedHTTPServer, ProtectionSettings, RateGate, settings as protection_settings

BASE = "/api/harness/sessions"
PROFILE = re.compile(r"/api/harness/profile/([A-Za-z0-9_-]{8,64})")
AVATAR = re.compile(r"/api/harness/avatars/([0-9a-f]{32})")
SESSION = re.compile(BASE + r"/([0-9a-f]{12})")
REQUEST = re.compile(BASE + r"/([0-9a-f]{12})/request")
READ = re.compile(BASE + r"/([0-9a-f]{12})/read/(?:(decision|planning)/(compare|why-not|evidence|lodging|variants|page|search|suggestions|preview-act|routes)|(trip)/(readback))")
LODGING = re.compile(BASE + r"/([0-9a-f]{12})/planning/lodging/events")
PREVIEW = re.compile(BASE + r"/([0-9a-f]{12})/preview")
FEEDBACK = re.compile(BASE + r"/([0-9a-f]{12})/feedback")
TODAY = re.compile(BASE + r"/([0-9a-f]{12})/today")
SUGGEST = re.compile(BASE + r"/([0-9a-f]{12})/companion/suggest")
COMPANION = re.compile(BASE + r"/([0-9a-f]{12})/companion")
NOTE_OPEN = re.compile(r"/api/harness/notifications/([0-9a-f-]{36})/open")
FRIEND = re.compile(r"/api/harness/friends/([0-9a-f]{32})")
ACCEPT = re.compile(r"/api/harness/friends/([0-9a-f]{32})/accept")
THREAD = re.compile(r"/api/harness/messages/([0-9a-f]{32})")
TYPING = re.compile(r"/api/harness/messages/([0-9a-f]{32})/typing")
IMPORT = re.compile(r"/api/harness/messages/([0-9]{1,18})/import")
SOCIAL = re.compile(r"/api/harness/(users|friends|messages)(/.*)?")  # friends and messages: members only
MAX_BODY = 65536
COOKIE = "tg_session"
STATE_COOKIE = "tg_oauth"
SESSION_MAX_AGE = 30 * 86400
AUTH_PER_IP_15MIN = 20  # sign-up and sign-in tries one address may make in 15 minutes
AUTH_FAILS_15MIN = 8  # wrong passwords for one email in 15 minutes, from anywhere, before it waits
PURGE_EVERY_S = 3600
LEAVERS_EVERY_S = 15  # how often guests whose page closed are looked for
MEMBERS_ONLY = {"/api/harness/me/notification-prefs", "/api/harness/notifications", "/api/harness/push/key",
                "/api/harness/calendar/preview", "/api/harness/me/avatar", "/api/harness/calendar/apply",
                "/api/harness/calendar/disconnect", "/api/harness/push/subscribe", "/api/harness/push/unsubscribe"}


class StalePreview(Exception):
    def __init__(self, preview: dict):
        super().__init__("stale preview")
        self.preview = preview


def handler(harness, accounts, base_url: str = "", test_login: bool = False,
            protection: ProtectionSettings | None = None, social=None, library=None):
    """base_url: the public origin (APP_BASE_URL); https makes cookies Secure. test_login enables
    GET /api/auth/test/login for browser walk-throughs and is refused on an https base URL.
    social: social.Social (friends, messages); library: accounts.Library (saved, recent). None turns either off."""
    secure = "; Secure" if base_url.startswith("https://") else ""
    base = urlparse(base_url)
    base_origin = f"{base.scheme}://{base.netloc}" if base.netloc else None
    test_login = test_login and not secure

    def cookie(name, value, max_age, path="/"):
        """max_age None: a session cookie, gone when the browser closes (a guest's)."""
        age = "" if max_age is None else f"; Max-Age={max_age}"
        return f"{name}={value}; HttpOnly; SameSite=Lax; Path={path}{age}{secure}"

    auth_tries: dict[str, deque] = {}  # "ip:<addr>" / "mail:<email>" -> times of tries / wrong passwords
    guest_lock = threading.Lock()
    protection = protection or protection_settings()
    gate = RateGate(protection.max_keys)
    active = threading.BoundedSemaphore(protection.max_active)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(protection.read_timeout_s)

        def handle_one_request(self):
            self._set = []
            if not active.acquire(blocking=False):
                try:
                    self.connection.sendall(b"HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\nContent-Length: 0\r\nRetry-After: 1\r\n\r\n")
                except OSError:
                    pass
                self.close_connection = True
                return
            try:
                super().handle_one_request()
            finally:
                active.release()

        def _limited(self, key, limit):
            if gate.allow(key, limit):
                return False
            self.close_connection = True
            self._send(429, b'{"error":"too many requests"}', "application/json", [("Retry-After", "60")])
            return True

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

        def _auth_count(self, key, limit, record):
            """True while `key` has fewer than `limit` entries in the last 15 minutes; `record` adds one."""
            now = time.monotonic()
            with guest_lock:
                if len(auth_tries) > 5000:
                    for k in [k for k, q in auth_tries.items() if not q or now - q[-1] > 900]:
                        del auth_tries[k]
                if key not in auth_tries and len(auth_tries) >= protection.max_keys:
                    return False
                window = auth_tries.setdefault(key, deque())
                while window and now - window[0] > 900:
                    window.popleft()
                if len(window) >= limit:
                    return False
                if record:
                    window.append(now)
            return True

        def _signed_in(self, token, event):
            """The browser now holds this session: a guest session it had before hands its trips to the account."""
            visitor = self._user()
            account = accounts.user_for(token)[0] or {}
            if visitor and visitor["guest"] and account:
                moved = harness.adopt(visitor["id"], account["id"])
                accounts.drop_guest(visitor["id"])
                harness._event("auth.guest_adopted", account["id"], None, journeys=moved)
            self._set.append(("Set-Cookie", cookie(COOKIE, token, SESSION_MAX_AGE)))
            harness._event(event, account.get("id"), None)

        def _password_auth(self, path):
            """POST /api/auth/register {email, password, name?} and /api/auth/login {email, password}."""
            if not self._same_origin():
                return self._json(403, {"error": "cross-origin request refused"})
            try:
                body = self._body()
                email, password = body.get("email"), body.get("password")
                if not isinstance(email, str) or not isinstance(password, str):
                    raise ValueError("email and password are required")
                mail = "mail:" + email.strip().lower()
                if path == "/api/auth/register":
                    token = accounts.register(email, password, body.get("name") or "", self.headers.get("User-Agent", ""))
                    self._signed_in(token, "auth.register")
                    return self._json(200, {"signed_in": True})
                if not self._auth_count(mail, AUTH_FAILS_15MIN, False):
                    return self._json(429, {"error": "too many wrong passwords for this email; wait a few minutes"})
                try:
                    token = accounts.login_password(email, password, self.headers.get("User-Agent", ""))
                except AuthError:
                    self._auth_count(mail, AUTH_FAILS_15MIN, True)
                    return self._json(401, {"error": "wrong email or password"})
                self._signed_in(token, "auth.login")
                return self._json(200, {"signed_in": True})
            except ValueError as exc:
                return self._json(409 if "taken" in str(exc) else 400, {"error": str(exc)})

        def _user(self):
            """The signed-in account or None; a session idle for a while gets its cookie re-sent (sliding 30 days)."""
            token = self._cookie(COOKIE)
            user, refreshed = accounts.user_for(token)
            if refreshed:
                self._set.append(("Set-Cookie", cookie(COOKIE, token, None if user["guest"] else SESSION_MAX_AGE)))
            return user

        def _members_only(self):
            self._json(403, {"error": "guest", "message": "Tính năng này cần đăng nhập Google."})

        def _same_origin(self):
            origin = self.headers.get("Origin")
            if not origin:
                return False
            return origin == base_origin or urlparse(origin).netloc == self.headers.get("Host")

        def _body(self):
            if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Encoding", "identity") != "identity":
                raise ValueError("unsupported request encoding")
            if len(self.headers.get_all("Content-Length") or []) > 1:
                raise ValueError("ambiguous content length")
            size = int(self.headers.get("Content-Length") or 0)
            if not 0 <= size <= MAX_BODY:
                raise ValueError("request body too large")
            try:
                body = json.loads(self.rfile.read(size) or b"{}")
            except RecursionError as exc:
                raise ValueError("request nesting too deep") from exc
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
            except TripNotReady as exc:
                return self._json(409, {"error": "trip_incomplete", "missing": exc.missing, "readback": exc.readback})
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
                user = {"id": None, "role": "anonymous", "guest": False}  # the public landing may report page_view / landing_cta
            if not user:
                self._json(401, {"error": "sign in first"})
                return None
            if user.get("id") and self._limited("user:" + user["id"], protection.per_user_minute):
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
                    self._signed_in(out["token"], "auth.login")
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
            if user["guest"] and (path in MEMBERS_ONLY or TODAY.fullmatch(path) or SUGGEST.fullmatch(path)
                                  or SOCIAL.fullmatch(path)):
                return self._members_only()
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
            if path == "/api/harness/trips":
                return self._call(lambda: harness.trips(owner))
            if path == "/api/harness/me/library" and library is not None:
                return self._call(lambda: library.read(owner))
            if social is not None:
                if path == "/api/harness/users":
                    return self._call(lambda: social.search(owner, query.get("q", "")))
                if path == "/api/harness/friends":
                    return self._call(lambda: social.friends(owner))
                if m := TYPING.fullmatch(path):
                    return self._call(lambda: {"typing": social.is_typing(owner, m[1])})
                if m := THREAD.fullmatch(path):
                    after = query.get("after", "0")
                    if not after.isdigit() or len(after) > 18:
                        return self._json(400, {"error": "after must be a message id"})
                    return self._call(lambda: social.thread(owner, m[1], int(after)))
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
                # trip/readback: the gate still open before planning, read after a partial answer (ui/ReadbackSheet.tsx)
                stage, op = (m[2], m[3]) if m[2] else (m[4], m[5])
                if op == "preview-act" and len(query.get("action", "")) > 8192:
                    return self._json(400, {"error": "preview action too large"})
                return self._call(lambda: harness.read(m[1], stage, op, query, owner))
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
                if path == "/api/auth/guest":
                    if not self._same_origin():
                        return self._json(403, {"error": "cross-origin request refused"})
                    old = self._cookie(COOKIE)
                    if old:  # a session already open here ends: a guest starts clean, never inherits it
                        accounts.logout(old)
                    token = accounts.guest(self.headers.get("User-Agent", ""))
                    self._set.append(("Set-Cookie", cookie(COOKIE, token, None)))
                    harness._event("auth.guest", accounts.user_for(token)[0]["id"], None)
                    return self._json(200, {"started": True})
                if path in ("/api/auth/guest/leave", "/api/auth/guest/alive"):  # sent by the guest's own page (sendBeacon / timer)
                    if not self._same_origin():
                        return self._json(403, {"error": "cross-origin request refused"})
                    token = self._cookie(COOKIE)
                    if path.endswith("leave"):
                        accounts.leave(token)
                    else:
                        accounts.user_for(token)  # a session seen again is no longer leaving
                    return self._json(200, {})
                if path in ("/api/auth/register", "/api/auth/login"):
                    return self._password_auth(path)
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
            if user["guest"] and (path in MEMBERS_ONLY or COMPANION.fullmatch(path) or NOTE_OPEN.fullmatch(path)
                                  or SOCIAL.fullmatch(path)):
                return self._members_only()
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
                    if user["guest"]:  # no profile prior, no long-term learning
                        return self._call(lambda: harness.create(body.get("experience"), body.get("start_with"), owner,
                                                                 False, owner, {}))
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
                if path == "/api/harness/me/library" and library is not None:
                    return self._call(lambda: library.save(owner, body.get("kind"), body.get("id"), body.get("on")))
                if social is not None:
                    if path == "/api/harness/friends":
                        return self._call(lambda: social.request(owner, body.get("to")))
                    if ac := ACCEPT.fullmatch(path):
                        return self._call(lambda: social.accept(owner, ac[1]))
                    if ty := TYPING.fullmatch(path):
                        return self._call(lambda: social.typing(owner, ty[1], body.get("on") is not False) or {"ok": True})
                    if th := THREAD.fullmatch(path):
                        journey = body.get("journey")
                        if journey is not None and not (isinstance(journey, str) and harness.owns(journey, owner)):
                            raise ValueError("journey must be one of your trips")
                        return self._call(lambda: social.send(owner, th[1], body.get("text", ""), journey))
                    if im := IMPORT.fullmatch(path):
                        def take():
                            sender, jid, done = social.shared(owner, int(im[1]))
                            if done:
                                return {"id": done, "already": True}
                            out = harness.copy(jid, sender, owner)
                            social.imported(int(im[1]), out["id"])
                            return out
                        return self._call(take)
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
                provisional = event in LIVE
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
                data = {"status": status, "message": message}
                if isinstance(exc, TripNotReady):
                    data.update(error="trip_incomplete", missing=exc.missing, readback=exc.readback)
                self._event({"request_id": req.request_id, "stage": req.stage, "revision": req.expected_revision,
                    "event": "error", "data": data})

        def do_PATCH(self):
            begun = self._begin(True)
            if not begun:
                return
            path, _, user = begun
            if user and user["guest"] and path in ("/api/harness/me", "/api/harness/me/notification-prefs"):
                return self._members_only()
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
            if user and user["guest"] and path == "/api/harness/me":  # a guest ends the visit: their trips go now
                accounts.drop_guest(user["id"])
                self._set.append(("Set-Cookie", cookie(COOKIE, "", 0)))
                return self._json(200, {"deleted": True})
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
            if user and (m := SESSION.fullmatch(path)):
                def discard():
                    harness.discard(m[1], user["id"])
                    return {"deleted": True}
                return self._call(discard)
            if user and social is not None and (m := FRIEND.fullmatch(path)):
                if user["guest"]:
                    return self._members_only()
                return self._call(lambda: social.remove(user["id"], m[1]))
            if user and (m := PROFILE.fullmatch(path)):
                if m[1] != user["id"]:
                    return self._json(404, {"error": "not found"})
                return self._call(lambda: {"forgotten": harness.forget_profile(m[1])})
            self._json(404, {"error": "not found"})

        def log_message(self, *args):
            pass
    return Handler


def run(harness, accounts, port=8769, base_url="", test_login=False, social=None, library=None):
    def sweep():
        last = 0.0
        while True:  # guests whose page closed or whose sessions ran out are deleted with their trips, even when nobody new arrives
            try:
                accounts.purge_leavers()
                if time.monotonic() - last >= PURGE_EVERY_S:
                    last = time.monotonic()
                    accounts.purge_guests()
            except Exception:
                traceback.print_exc(file=sys.stderr)
            time.sleep(LEAVERS_EVERY_S)
    threading.Thread(target=sweep, daemon=True).start()
    cfg = protection_settings()
    ProtectedHTTPServer(("127.0.0.1", port), handler(harness, accounts, base_url, test_login, cfg, social, library), cfg).serve_forever()
