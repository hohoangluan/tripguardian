"""Local review page: python -m corpus review [--port 8765]. Serves on 127.0.0.1 only; no login, no internet exposure.

GET  /                page.html
GET  /api/queue       {items:[…]}   ?decided=1 also returns decided items
POST /api/decision    {kind, id, decision, note} -> the stored record
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .decisions import decide
from .queue import queue

PAGE = Path(__file__).with_name("page.html")


def handler(city: str):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/":
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/queue":
                decided = parse_qs(url.query).get("decided", ["0"])[0] == "1"
                self._json(200, {"city": city, "items": queue(city, decided=decided)})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            if urlparse(self.path).path != "/api/decision":
                return self._json(404, {"error": "not found"})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                self._json(200, decide(body["kind"], str(body["id"]), body["decision"], body.get("note", "")))
            except (KeyError, ValueError) as e:
                self._json(400, {"error": str(e)})

        def log_message(self, *args):
            pass  # quiet terminal

    return Handler


def run(city: str, port: int = 8765) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), handler(city))
    print(f"review {city}: http://127.0.0.1:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
