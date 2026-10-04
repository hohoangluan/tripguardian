"""HTTP API for the web (docs/PLANNING.md §API và web). Local only: binds 127.0.0.1."""

import json
import re
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .engine import Engine, NoSession, NotConfirmable
from .lodging import progress_event
from .session import ActionError

BASE = "/api/planning/sessions"
SESSION = re.compile(BASE + r"/([0-9a-f]{12})")
SUB = re.compile(BASE + r"/([0-9a-f]{12})/(act|confirm|variants|lodging|turn)")
MAX_TEXT = 1000
EVENTS = re.compile(BASE + r"/([0-9a-f]{12})/lodging/events")


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
            except (ActionError, ValueError) as e:
                return self._json(400, {"error": str(e).splitlines()[0]})
            except NotConfirmable as e:
                return self._json(409, {"error": str(e)})
            except Exception:
                traceback.print_exc(file=sys.stderr)
                return self._json(500, {"error": "server error"})

        def do_GET(self):
            path = urlparse(self.path).path
            if m := SESSION.fullmatch(path):
                return self._call(lambda: engine.load(m[1]))
            if m := SUB.fullmatch(path):
                if m[2] == "variants":
                    return self._call(lambda: engine.variants(m[1]))
                if m[2] == "lodging":
                    return self._call(lambda: engine.lodging(m[1]))
            if m := EVENTS.fullmatch(path):
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
                    lod = engine.lodging(m[1])
                    if lod["status"] == "pending":
                        import time
                        for _ in range(200):          # best-effort poll: the crawl thread has no direct callback in
                            time.sleep(0.05)           # this minimal transport; good enough for a handful of seconds
                            lod = engine.lodging(m[1])
                            if lod["status"] != "pending":
                                break
                    emit("progress", progress_event(lod["candidates"], None))
                    emit("view", engine.load(m[1])["view"])
                    emit("done", {})
                except Exception:
                    traceback.print_exc(file=sys.stderr)
                    emit("error", {"message": "Máy chủ gặp lỗi, bạn thử lại nhé."})
                return
            self._json(404, {"error": "not found"})

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                body = self._body()
            except json.JSONDecodeError:
                return self._json(400, {"error": "body is not a JSON object"})
            if path == BASE:
                return self._call(lambda: engine.create(body.get("decision_output"), body.get("decision_session_id")))
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


def run(engine: Engine, port: int = 8768) -> None:
    ThreadingHTTPServer(("127.0.0.1", port), handler(engine)).serve_forever()
