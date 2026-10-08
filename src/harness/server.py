"""Local journey HTTP/SSE boundary; the router owns stage permissions."""

import json
import re
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from pydantic import ValidationError
from agents import ToolError
from trip import USER_ID

from .contracts import Request
from .dispatch import Conflict
from .router import RouteError, route

BASE = "/api/harness/sessions"
PROFILE = re.compile(r"/api/harness/profile/([A-Za-z0-9_-]{8,64})")
SESSION = re.compile(BASE + r"/([0-9a-f]{12})")
REQUEST = re.compile(BASE + r"/([0-9a-f]{12})/request")
READ = re.compile(BASE + r"/([0-9a-f]{12})/read/(decision|planning)/(compare|why-not|lodging|variants|page)")
LODGING = re.compile(BASE + r"/([0-9a-f]{12})/planning/lodging/events")
PREVIEW = re.compile(BASE + r"/([0-9a-f]{12})/preview")
FEEDBACK = re.compile(BASE + r"/([0-9a-f]{12})/feedback")
MAX_BODY = 65536


def handler(harness):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, code, value):
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            size = int(self.headers.get("Content-Length") or 0)
            if not 0 <= size <= MAX_BODY:
                raise ValueError("request body too large")
            body = json.loads(self.rfile.read(size) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("body must be a JSON object")
            return body

        def _call(self, fn):
            try:
                return self._json(200, fn())
            except KeyError:
                return self._json(404, {"error": "no such session"})
            except (Conflict, RouteError) as exc:
                return self._json(409, {"error": str(exc)})
            except ToolError as exc:
                return self._json(exc.status, {"error": str(exc)})
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
            self.end_headers()
            self.close_connection = True

        def _event(self, value):
            try:
                self.wfile.write(f"event: event\ndata: {json.dumps(value, ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()
            except OSError:
                pass  # finish and commit the request even when its browser disconnects

        def do_GET(self):
            url = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            if url.path == "/api/harness/places":
                return self._call(lambda: harness.places(query.get("q", "")))
            if url.path == "/api/harness/trips":
                ids = [i for i in query.get("ids", "").split(",") if i]
                return self._call(lambda: harness.summaries(ids))
            if m := PREVIEW.fullmatch(url.path):
                return self._call(lambda: harness.preview(m[1]))
            if m := SESSION.fullmatch(url.path):
                stage = query.get("stage")
                if stage not in (None, "trip", "decision", "planning"):
                    return self._json(400, {"error": "unknown stage"})
                return self._call(lambda: harness.load(m[1], stage))
            if m := READ.fullmatch(url.path):
                return self._call(lambda: harness.read(m[1], m[2], m[3], query))
            if m := LODGING.fullmatch(url.path):
                try:
                    current = harness.load(m[1], "planning")
                except KeyError:
                    return self._json(404, {"error": "no such session"})
                except Conflict as exc:
                    return self._json(409, {"error": str(exc)})
                self._stream_headers()
                for _ in range(200):
                    lod = harness.read(m[1], "planning", "lodging")
                    if lod["status"] != "pending":
                        break
                    time.sleep(0.05)
                updated = harness.load(m[1], "planning")
                self._event({"stage": "planning", "revision": updated["revision"], "event": "view",
                    "data": updated["result"]["view"]})
                self._event({"stage": "planning", "revision": updated["revision"], "event": "done", "data": {}})
                return
            self._json(404, {"error": "not found"})

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                body = self._body()
                if path == BASE:
                    if set(body) - {"experience", "start_with", "user_id", "remember"}:
                        raise ValueError("unknown start field")
                    if body.get("experience") not in (None, "first", "returning"):
                        raise ValueError("bad experience")
                    if body.get("start_with") not in (None, "nothing", "saved", "must", "itinerary"):
                        raise ValueError("bad start_with")
                    uid = body.get("user_id")
                    if not isinstance(body.get("remember", False), bool) or \
                            (uid is not None and not (isinstance(uid, str) and USER_ID.fullmatch(uid))):
                        raise ValueError("bad user_id / remember")
                    return self._call(lambda: harness.create(body.get("experience"), body.get("start_with"),
                                                             body.get("user_id"), body.get("remember", False)))
                if path == "/api/harness/reports":
                    return self._call(lambda: harness.report(body))
                if fb := FEEDBACK.fullmatch(path):
                    return self._call(lambda: harness.feedback(fb[1], body))
                m = REQUEST.fullmatch(path)
                if not m:
                    return self._json(404, {"error": "not found"})
                req = Request.model_validate(body)
            except (ValueError, ValidationError) as exc:
                return self._json(400, {"error": str(exc).splitlines()[0]})
            if "text/event-stream" not in self.headers.get("Accept", ""):
                return self._call(lambda: harness.request(m[1], req))
            try:
                with harness.store.lock(m[1]):
                    session = harness._get(m[1])
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
                response = harness.request(m[1], req, emit)
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

        def do_DELETE(self):
            if m := PROFILE.fullmatch(urlparse(self.path).path):
                return self._call(lambda: {"forgotten": harness.forget_profile(m[1])})
            self._json(404, {"error": "not found"})

        def log_message(self, *args):
            pass
    return Handler


def run(harness, port=8769):
    ThreadingHTTPServer(("127.0.0.1", port), handler(harness)).serve_forever()
