"""Journeys in Postgres (table journeys): same interface as the file Store, with a revision guard on every write."""

import json
from datetime import datetime, timezone
from pathlib import Path

from psycopg.types.json import Jsonb

from .contracts import Conflict, Journey
from .session import Store


class PgStore(Store):
    """One process keeps a copy of each journey it touched (envelopes reach a few MB); a write only lands when the
    row still has the revision this process last read or wrote, so a second writer gets Conflict instead of a lost
    update."""

    def __init__(self, pool, app_version: str | None = None):
        super().__init__(None)
        self.pool, self.app_version = pool, app_version
        self._rev: dict[str, int] = {}

    def get(self, jid: str) -> Journey:
        with self.lock(jid):
            if jid not in self._mem:
                with self.pool.connection() as conn:
                    row = conn.execute("SELECT envelope, revision FROM journeys WHERE id = %s", (jid,)).fetchone()
                if not row:
                    raise KeyError(jid)
                session = Journey.model_validate(row["envelope"])
                if session.id != jid:
                    raise ValueError("journey row ID mismatch")
                self._mem[jid], self._rev[jid] = session, row["revision"]
            return self._mem[jid].model_copy(deep=True)

    def save(self, session: Journey) -> None:
        with self.lock(session.id):
            envelope = Jsonb(session.model_dump(mode="json"))
            with self.pool.connection() as conn:
                if session.id in self._rev:
                    done = conn.execute(
                        "UPDATE journeys SET stage = %s, revision = %s, envelope = %s, user_id = %s, app_version = %s, "
                        "updated_at = now() WHERE id = %s AND revision = %s",
                        (session.stage, session.revision, envelope, session.user_id, self.app_version, session.id,
                         self._rev[session.id])).rowcount
                else:
                    done = conn.execute(
                        "INSERT INTO journeys (id, user_id, stage, revision, envelope, app_version) "
                        "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                        (session.id, session.user_id, session.stage, session.revision, envelope, self.app_version)).rowcount
            if not done:
                self._mem.pop(session.id, None)
                self._rev.pop(session.id, None)
                raise Conflict("the journey was changed elsewhere; reload it")
            self._mem[session.id], self._rev[session.id] = session.model_copy(deep=True), session.revision

    def append_feedback(self, record: dict) -> None:
        with self.pool.connection() as conn:
            conn.execute("INSERT INTO feedback (journey_id, user_id, at, scores, more_search, note) "
                         "VALUES (%s, %s, %s, %s, %s, %s)",
                         (record["journey"], record.get("user_id"), record["at"], Jsonb(record["scores"]),
                          record["more_search"], record["note"]))

    def list_for(self, owner: str, limit: int = 50) -> list[str]:
        with self.pool.connection() as conn:
            rows = conn.execute("SELECT id FROM journeys WHERE user_id = %s ORDER BY updated_at DESC LIMIT %s",
                                (owner, limit)).fetchall()
        return [r["id"] for r in rows]


def milestones(session: Journey) -> list[tuple[str, str | None]]:
    """The funnel steps an imported journey had reached, read from its saved state (it has no events of its own):
    (event name, time or None). Selections keep their Decision log time."""
    out: list[tuple[str, str | None]] = [("journey.create", None)]
    if "trip" in session.outputs or "decision" in session.sessions:
        out.append(("trip.turn", None))
    if "decision" in session.sessions:
        out.append(("trip.advance", None))
        snap = session.snapshots.get("decision") or {}
        picks = [e for e in snap.get("log") or [] if (e.get("action") or {}).get("type") == "select"]
        if picks:
            out.append(("decision.act.select", picks[0].get("at")))
        elif (snap.get("state") or {}).get("selected"):
            out.append(("decision.act.select", None))
    if "planning" in session.sessions:
        out.append(("decision.advance", None))
    if "planning" in session.outputs:
        out.append(("planning.confirm", None))
    return out


def import_files(pool, sessions: Path, feedback: Path | None) -> tuple[int, int]:
    """Load the file-store journeys (user_id NULL, timestamps from the file), their funnel milestones as events
    (props.imported) and the feedback lines; rerunning adds nothing twice. Returns (journeys, feedback rows) added."""
    journeys = added = 0
    with pool.connection() as conn:
        for path in sorted(sessions.glob("*.json")):
            session = Journey.model_validate_json(path.read_text(encoding="utf-8"))
            when = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            journeys += conn.execute(
                "INSERT INTO journeys (id, user_id, stage, revision, envelope, updated_at, created_at) "
                "VALUES (%s, NULL, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (session.id, session.stage, session.revision, Jsonb(session.model_dump(mode="json")), when, when)
            ).rowcount
            if not conn.execute("SELECT 1 FROM events WHERE journey_id = %s AND props ? 'imported'",
                                (session.id,)).fetchone():
                for name, at in milestones(session):
                    conn.execute("INSERT INTO events (at, journey_id, source, name, props) "
                                 "VALUES (%s, %s, 'server', %s, %s)",
                                 (at or when, session.id, name,
                                  Jsonb({"imported": True, **({"compiled": True} if name == "trip.turn" else {})})))
        for line in (feedback.read_text(encoding="utf-8").splitlines() if feedback and feedback.exists() else []):
            if not line.strip():
                continue
            r = json.loads(line)
            new = conn.execute(
                "INSERT INTO feedback (journey_id, at, scores, more_search, note) SELECT %s, %s, %s, %s, %s "
                "WHERE NOT EXISTS (SELECT 1 FROM feedback WHERE journey_id = %s AND at = %s)",
                (r["journey"], r["at"], Jsonb(r.get("scores") or {}), r.get("more_search"), r.get("note") or "",
                 r["journey"], r["at"])).rowcount
            conn.execute("INSERT INTO events (at, journey_id, source, name, props) "
                         "SELECT %s, %s, 'server', 'feedback.submit', %s WHERE NOT EXISTS (SELECT 1 FROM events "
                         "WHERE journey_id = %s AND name = 'feedback.submit' AND at = %s)",
                         (r["at"], r["journey"], Jsonb({"imported": True}), r["journey"], r["at"]))
            added += new
    return journeys, added
