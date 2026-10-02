"""Local review page: python -m corpus review [--port 8765]. Serves on 127.0.0.1 only; no login, no internet exposure.

GET  /                page.html
GET  /api/queue       {items:[…]}   ?decided=1 also returns decided items
GET  /api/decisions   ?kind=feature_review -> {decisions: {id: record}}   latest per item
POST /api/decision    {kind, id, decision, note} -> the stored record
GET  /api/labels/next ?n=1&feature=<id> -> {items:[...]}   unlabelled review observations, least-labelled value first
POST /api/labels      {id, label, note} -> the stored record   label: correct | wrong | unsure
GET  /api/labels/stats                    precision per (feature, value) and the gate
GET  /api/labels/photo ?place=<fid_dir>&file=<photos/x.jpg>  a Maps photo a photo observation was read from
GET  /api/labels/frame ?video=<id>&n=<1-4>  a TikTok keyframe (image/jpeg) a frame observation was read from
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import labels
from .decisions import ACTIONS, decide, latest
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
            elif url.path == "/api/decisions":
                kind = parse_qs(url.query).get("kind", [""])[0]
                if kind not in ACTIONS:
                    return self._json(400, {"error": f"unknown kind {kind!r}"})
                self._json(200, {"decisions": latest(kind)})
            elif url.path == "/api/labels/next":
                q = parse_qs(url.query)
                n = max(1, min(20, int(q.get("n", ["1"])[0])))
                self._json(200, {"items": labels.sample(n, q.get("feature", [None])[0] or None)})
            elif url.path == "/api/labels/stats":
                self._json(200, labels.stats())
            elif url.path == "/api/labels/photo":
                q = parse_qs(url.query)
                f = labels.photo_path(q.get("place", [""])[0], q.get("file", [""])[0])
                if f is None:
                    return self._json(404, {"error": "no such photo"})
                self._send(200, f.read_bytes(), "image/jpeg")
            elif url.path == "/api/labels/frame":
                q = parse_qs(url.query)
                try:
                    f = labels.frame_path(q.get("video", [""])[0], int(q.get("n", ["0"])[0]))
                except ValueError:
                    f = None
                if f is None:
                    return self._json(404, {"error": "no such frame"})
                self._send(200, f.read_bytes(), "image/jpeg")
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            path = urlparse(self.path).path
            if path not in ("/api/decision", "/api/labels"):
                return self._json(404, {"error": "not found"})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if path == "/api/labels":
                    self._json(200, labels.label(str(body["id"]), body["label"], body.get("note", "")))
                else:
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
