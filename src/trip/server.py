"""HTTP API for the web (docs/TRIP_UNDERSTANDING.md §14). Local only: binds 127.0.0.1."""

import json
import re
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from pydantic import ValidationError

from .engine import Engine, TurnInput

SESSION = re.compile(r"/api/trip/sessions/([0-9a-f]{12})")
TURN = re.compile(r"/api/trip/sessions/([0-9a-f]{12})/turn")


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
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            url = urlparse(self.path)
            if m := SESSION.fullmatch(url.path):
                try:
                    return self._json(200, engine.load(m[1]))
                except KeyError:
                    return self._json(404, {"error": "no such session"})
            if url.path == "/api/trip/places":
                return self._json(200, engine.places(parse_qs(url.query).get("q", [""])[0]))
            self._json(404, {"error": "not found"})

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                body = self._body()
            except json.JSONDecodeError:
                return self._json(400, {"error": "body is not JSON"})
            if path == "/api/trip/sessions":
                exp, start = body.get("experience"), body.get("start_with")
                if exp not in (None, "first", "returning") or start not in (None, "nothing", "saved", "must", "itinerary"):
                    return self._json(400, {"error": "bad experience / start_with"})
                return self._json(200, engine.create(exp, start))
            if m := TURN.fullmatch(path):
                try:
                    inp = TurnInput.model_validate(body)
                    engine.store.get(m[1])
                except ValidationError as e:
                    return self._json(400, {"error": str(e).splitlines()[0]})
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
                    engine.turn(m[1], inp, emit)
                except Exception:
                    traceback.print_exc(file=sys.stderr)
                    emit("error", {"message": "Máy chủ gặp lỗi, bạn thử lại nhé."})
                return
            self._json(404, {"error": "not found"})

        def log_message(self, *args):
            pass

    return Handler


def run(engine: Engine, port: int = 8766) -> None:
    ThreadingHTTPServer(("127.0.0.1", port), handler(engine)).serve_forever()
