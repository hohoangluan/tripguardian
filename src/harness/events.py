"""Usage events in Postgres (table events; docs/ANALYTICS.md). Server events follow each journey mutation; client
events come in batches from the web and only names on the allowlist are kept. Events never carry email, names or
free text typed by the user; a failed write is logged and never fails the request that caused it."""

import json
import sys
from datetime import datetime, UTC

from psycopg.types.json import Jsonb

MAX_BATCH = 50
MAX_BATCH_BYTES = 32 * 1024
# name -> allowed prop keys
CLIENT = {
    "page_view": {"route"},
    "landing_cta": {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"},
    "card_impression": {"place_id", "group", "rank"},
    "detail_open": {"place_id", "from"},
    "evidence_play": {"place_id", "video_id"},
    "compare_open": {"a", "b"},
    "outbound_click": {"kind", "place_id"},
    "tab_hidden": {"stage", "ms"},
    "today_open": set(),
    "suggestion_open": {"place_id", "kind"},
    "install_prompt_seen": set(),
    "push_permission": {"result"},
}
ANONYMOUS = {"page_view", "landing_cta"}  # the landing is public: these two are kept without a session
ACT_PROPS = ("place_id", "reason", "with_id", "group", "id", "objective", "pace")


def _clean(value):
    """Short scalars only: a prop is a label or a number, never a document."""
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value[:120]
    return None


class EventLog:
    def __init__(self, pool, app_version: str | None = None):
        self.pool, self.app_version = pool, app_version

    def _write(self, rows: list[tuple]) -> None:
        if not rows:
            return
        try:
            with self.pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.executemany("INSERT INTO events (at, user_id, journey_id, source, name, props, app_version) "
                                    "VALUES (%s, %s, %s, %s, %s, %s, %s)", rows)
        except Exception as exc:  # analytics must never break the journey
            print(f"events not written: {type(exc).__name__}: {exc}", file=sys.stderr)

    def server(self, name: str, user_id: str | None = None, journey_id: str | None = None, **props) -> None:
        self._write([(datetime.now(UTC), user_id, journey_id, "server", name,
                      Jsonb({k: v for k, v in props.items() if v is not None}), self.app_version)])

    def client(self, batch, user_id: str | None) -> int:
        """Keep allowlisted events of a web batch; returns how many were stored. Unknown names and props are dropped."""
        if not isinstance(batch, list) or len(batch) > MAX_BATCH or len(json.dumps(batch)) > MAX_BATCH_BYTES:
            raise ValueError(f"send at most {MAX_BATCH} events / 32 KiB")
        now = datetime.now(UTC)
        rows = []
        for e in batch:
            if not isinstance(e, dict) or e.get("name") not in CLIENT:
                continue
            if user_id is None and e["name"] not in ANONYMOUS:
                continue
            props = e.get("props") if isinstance(e.get("props"), dict) else {}
            kept = {k: _clean(v) for k, v in props.items() if k in CLIENT[e["name"]] and _clean(v) is not None}
            jid = e.get("journey_id")
            jid = jid if isinstance(jid, str) and len(jid) == 12 and jid.isalnum() else None
            rows.append((now, user_id, jid, "client", e["name"], Jsonb(kept), self.app_version))
        self._write(rows)
        return len(rows)

    def act_props(self, payload: dict) -> dict:
        return {k: _clean(payload[k]) for k in ACT_PROPS if k in payload}
