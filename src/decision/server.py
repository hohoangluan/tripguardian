"""HTTP API for the web (docs/P3_PLACE_DECISION.md §18). Local only: binds 127.0.0.1."""

import json
import re
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from pydantic import ValidationError

from .curation import ActionError
from .engine import Engine, NoSession, NotConfirmable, VersionMismatch

BASE = "/api/decision/sessions"
REPORTS = "/api/reports"  # a traveller reports something about a place (corpus.review.reports)
SESSION = re.compile(BASE + r"/([0-9a-f]{12})")
SUB = re.compile(BASE + r"/([0-9a-f]{12})/(act|turn|compare|confirm)")
WHY = re.compile(BASE + r"/([0-9a-f]{12})/why-not/([^/]+)")
MAX_TEXT = 1000


def handler(engine: Engine):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, code: int, obj) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict):
                raise json.JSONDecodeError("not an object", "", 0)
            return body

        def _call(self, fn) -> None:
            try:
                return self._json(200, fn())
            except NoSession:
                return self._json(404, {"error": "no such session"})
            except (ActionError, ValidationError, ValueError) as e:
                return self._json(400, {"error": str(e).splitlines()[0]})
            except (VersionMismatch, NotConfirmable) as e:
                return self._json(409, {"error": str(e)})
            except Exception:
                traceback.print_exc(file=sys.stderr)
                return self._json(500, {"error": "server error"})

        def do_GET(self):
            url = urlparse(self.path)
            q = parse_qs(url.query)
            if m := SESSION.fullmatch(url.path):
                return self._call(lambda: engine.load(m[1]))
            if (m := SUB.fullmatch(url.path)) and m[2] == "compare":
                return self._call(lambda: engine.compare(m[1], q.get("a", [""])[0], q.get("b", [""])[0]))
            if m := WHY.fullmatch(url.path):
                return self._call(lambda: engine.why_not(m[1], unquote(m[2])))
            self._json(404, {"error": "not found"})

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                body = self._body()
            except json.JSONDecodeError:
                return self._json(400, {"error": "body is not a JSON object"})
            if path == BASE:
                return self._call(lambda: engine.create(body.get("search_input") or {}, body.get("trip_session")))
            if path == REPORTS:
                return self._call(lambda: engine.report(body.get("place_id"), body.get("text"), body.get("reporter")))
            m = SUB.fullmatch(path)
            if m and m[2] == "act":
                return self._call(lambda: engine.act(m[1], body))
            if m and m[2] == "confirm":
                return self._call(lambda: engine.confirm(m[1]))
            if m and m[2] == "turn":
                text = body.get("text")
                if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
                    return self._json(400, {"error": f"text must be 1-{MAX_TEXT} characters"})
                try:
                    engine.store.get(m[1])
                except KeyError:
                    return self._json(404, {"error": "no such session"})
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()

                def emit(event: str, data: dict) -> None:
                    self.wfile.write(f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode())
                    self.wfile.flush()

                try:
                    engine.turn(m[1], text.strip(), emit)
                except Exception:
                    traceback.print_exc(file=sys.stderr)
                    emit("error", {"message": "Máy chủ gặp lỗi, bạn thử lại nhé."})
                return
            self._json(404, {"error": "not found"})

        def log_message(self, *args):
            pass

    return Handler


def run(engine: Engine, port: int = 8767) -> None:
    ThreadingHTTPServer(("127.0.0.1", port), handler(engine)).serve_forever()
