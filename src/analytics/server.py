"""Private analytics HTTP server: 127.0.0.1 only, GET only, read-only database role. Never proxied by web/server.mjs."""

import json
import re
import sys
import traceback
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse
from uuid import UUID

from . import queries, tabs

SESSION = re.compile(r"/api/analytics/sessions/([0-9a-f]{12})")
PLACE = re.compile(r"/api/analytics/places/([^/]{1,120})")


def _plain(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return value.hex
    raise TypeError(type(value).__name__)


def handler(pool):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, code, value):
            body = json.dumps(value, ensure_ascii=False, default=_plain).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlparse(self.path)
            params = {k: v[0] for k, v in parse_qs(url.query).items()}
            routes = {"/api/analytics/funnel": lambda: queries.funnel(pool, params),
                      "/api/analytics/decision": lambda: queries.decision(pool, params),
                      "/api/analytics/sessions": lambda: queries.sessions(pool, params),
                      "/api/analytics/today": lambda: queries.today(pool),
                      "/api/analytics/versions": lambda: queries.versions(pool),
                      "/api/analytics/trip": lambda: tabs.trip(pool, params),
                      "/api/analytics/planning": lambda: tabs.planning(pool, params),
                      "/api/analytics/reality": lambda: tabs.reality(pool, params),
                      "/api/analytics/notifications": lambda: tabs.notifications(pool, params),
                      "/api/analytics/agent": lambda: tabs.agent(pool, params),
                      "/api/analytics/quality": lambda: tabs.quality(pool, params),
                      "/api/analytics/insights": lambda: tabs.insights(pool, params),
                      "/api/analytics/clusters": lambda: tabs.clusters(pool)}
            fn = routes.get(url.path)
            if fn is None and (m := SESSION.fullmatch(url.path)):
                fn = lambda: queries.session(pool, m[1])  # noqa: E731
            elif fn is None and (m := PLACE.fullmatch(url.path)):
                fn = lambda: tabs.place(pool, unquote(m[1]), params)  # noqa: E731
            if fn is None:
                return self._json(404, {"error": "not found"})
            try:
                return self._json(200, fn())
            except KeyError:
                return self._json(404, {"error": "no such journey"})
            except ValueError as exc:
                return self._json(400, {"error": str(exc)})
            except Exception:
                traceback.print_exc(file=sys.stderr)
                return self._json(500, {"error": "server error"})

        def log_message(self, *args):
            pass
    return Handler


def run(pool, port=8770):
    ThreadingHTTPServer(("127.0.0.1", port), handler(pool)).serve_forever()
