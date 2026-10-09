"""Google Calendar export (docs/COMPANION.md §Calendar): one calendar per trip that the app created itself (scope
calendar.app.created), one event per stop, no reminders. Every write goes preview -> the user confirms that exact
preview (preview_hash) -> apply. Nothing syncs on its own; a changed plan only marks the calendar "drifted"."""

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request

from psycopg.types.json import Jsonb

from .trips import TZ

API = "https://www.googleapis.com/calendar/v3"
TIMEOUT_S = 15


class CalendarError(RuntimeError):
    pass


class NotConnected(CalendarError):
    """The user has not granted Calendar (or revoked it)."""


class GoogleCalendarApi:
    """The few Calendar v3 calls the export needs, with one access token."""

    def __init__(self, access_token: str):
        self.token = access_token

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(API + path, json.dumps(body).encode() if body is not None else None, method=method,
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as res:
                raw = res.read()
        except urllib.error.HTTPError as exc:
            if method == "DELETE" and exc.code in (404, 410):
                return {}  # already gone
            raise CalendarError(f"calendar {exc.code}: {exc.read()[:200]!r}") from exc
        except OSError as exc:
            raise CalendarError(f"calendar unreachable: {exc}") from exc
        return json.loads(raw) if raw else {}

    def create_calendar(self, summary: str) -> str:
        return self._call("POST", "/calendars", {"summary": summary, "timeZone": "Asia/Ho_Chi_Minh"})["id"]

    def delete_calendar(self, calendar_id: str) -> None:
        self._call("DELETE", f"/calendars/{urllib.parse.quote(calendar_id)}")

    def insert(self, calendar_id: str, event: dict) -> dict:
        return self._call("POST", f"/calendars/{urllib.parse.quote(calendar_id)}/events", event)

    def patch(self, calendar_id: str, event_id: str, event: dict) -> dict:
        return self._call("PATCH", f"/calendars/{urllib.parse.quote(calendar_id)}/events/{urllib.parse.quote(event_id)}",
                          event)

    def delete(self, calendar_id: str, event_id: str) -> None:
        self._call("DELETE", f"/calendars/{urllib.parse.quote(calendar_id)}/events/{urllib.parse.quote(event_id)}")


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


class Calendar:
    def __init__(self, pool, accounts, records: dict[str, dict], base_url: str, api=None):
        """accounts: accounts.Accounts (refresh token, Google client); api: (access token) -> GoogleCalendarApi."""
        self.pool, self.accounts, self.records, self.base_url = pool, accounts, records, base_url.rstrip("/")
        self.api = api or GoogleCalendarApi

    def _client(self, user_id: str):
        token = self.accounts.calendar_token(user_id)
        if not token:
            raise NotConnected("Google Calendar is not connected")
        return self.api(self.accounts.google.access_token(token))

    def _event(self, stop: dict, warnings: list[dict]) -> dict:
        rec = self.records.get(stop["place_id"]) or {}
        lines = [w["text"] for w in warnings if stop["name"] and stop["name"] in w.get("text", "")]
        lines.append(f"{self.base_url}/app/today?stop={stop['id']}")
        return {"summary": stop["name"] or (rec.get("identity") or {}).get("name") or "Điểm dừng",
                "location": (rec.get("identity") or {}).get("address") or "",
                "description": "\n".join(lines),
                "start": {"dateTime": stop["planned_arrive"].astimezone(TZ).isoformat(), "timeZone": "Asia/Ho_Chi_Minh"},
                "end": {"dateTime": stop["planned_leave"].astimezone(TZ).isoformat(), "timeZone": "Asia/Ho_Chi_Minh"},
                "reminders": {"useDefault": False, "overrides": []}}

    def _state(self, conn, journey_id: str, plan: dict) -> tuple[dict, dict, list[dict]]:
        trip = conn.execute("SELECT * FROM trips WHERE journey_id = %s", (journey_id,)).fetchone()
        if not trip:
            raise KeyError(journey_id)
        sync = conn.execute("SELECT * FROM calendar_sync WHERE trip_id = %s", (trip["id"],)).fetchone() or {}
        stops = conn.execute("SELECT * FROM trip_stops WHERE trip_id = %s AND planned_arrive IS NOT NULL "
                             "AND planned_leave IS NOT NULL ORDER BY day, seq", (trip["id"],)).fetchall()
        synced = {r["stop_id"]: r for r in conn.execute("SELECT * FROM calendar_events WHERE trip_id = %s",
                                                        (trip["id"],))}
        warnings = plan.get("warnings") or []
        changes = []
        for s in stops:
            event = self._event(s, warnings)
            have = synced.pop(s["id"], None)
            if have is None:
                changes.append({"op": "create", "stop": str(s["id"]), "after": event})
            elif have["synced_hash"] != _digest(event):
                changes.append({"op": "update", "stop": str(s["id"]), "event_id": have["google_event_id"],
                                "after": event})
        for stop_id, have in synced.items():
            changes.append({"op": "delete", "stop": str(stop_id), "event_id": have["google_event_id"]})
        return trip, dict(sync), changes

    def preview(self, journey_id: str, user_id: str, plan: dict) -> dict:
        """{state, connected, calendar, changes, preview_hash}; stored so apply can check it was this one."""
        with self.pool.connection() as conn:
            trip, sync, changes = self._state(conn, journey_id, plan)
            summary = None
            if not sync.get("calendar_id"):
                start, end = trip["start_date"], trip["end_date"]
                summary = f"TripGuardian · Đà Lạt {start:%d}–{end:%d/%m}" if start and end else "TripGuardian · Đà Lạt"
            body = {"calendar": summary, "changes": changes}
            digest = _digest(body)
            conn.execute("INSERT INTO calendar_sync (trip_id, last_preview, preview_hash) VALUES (%s, %s, %s) "
                         "ON CONFLICT (trip_id) DO UPDATE SET last_preview = EXCLUDED.last_preview, "
                         "preview_hash = EXCLUDED.preview_hash", (trip["id"], Jsonb(body), digest))
        state = sync.get("state") or "none"
        if state == "synced" and changes:
            state = "drifted"
        return {"state": state, "connected": self.accounts.calendar_token(user_id) is not None,
                "calendar": {"create": summary is not None, "summary": summary}, "changes": changes,
                "preview_hash": digest}

    def apply(self, journey_id: str, user_id: str, plan: dict, preview_hash: str) -> dict:
        """Apply exactly the preview the user confirmed. Stops at the first failure: what was applied is recorded,
        the rest is reported as not done, nothing is retried."""
        current = self.preview(journey_id, user_id, plan)
        if current["preview_hash"] != preview_hash:
            return {"stale": True, "preview": current}
        api = self._client(user_id)
        done, failed = [], None
        with self.pool.connection() as conn:
            trip, sync, changes = self._state(conn, journey_id, plan)
            calendar_id = sync.get("calendar_id")
            if not calendar_id:
                calendar_id = api.create_calendar(current["calendar"]["summary"])
                conn.execute("UPDATE calendar_sync SET calendar_id = %s WHERE trip_id = %s", (calendar_id, trip["id"]))
                conn.commit()
            for ch in changes:
                try:
                    if ch["op"] == "create":
                        ev = api.insert(calendar_id, ch["after"])
                        conn.execute("INSERT INTO calendar_events (stop_id, trip_id, google_event_id, etag, synced_hash) "
                                     "VALUES (%s, %s, %s, %s, %s)", (ch["stop"], trip["id"], ev["id"], ev.get("etag"),
                                                                     _digest(ch["after"])))
                    elif ch["op"] == "update":
                        ev = api.patch(calendar_id, ch["event_id"], ch["after"])
                        conn.execute("UPDATE calendar_events SET etag = %s, synced_hash = %s WHERE stop_id = %s",
                                     (ev.get("etag"), _digest(ch["after"]), ch["stop"]))
                    else:
                        api.delete(calendar_id, ch["event_id"])
                        conn.execute("DELETE FROM calendar_events WHERE stop_id = %s", (ch["stop"],))
                    conn.commit()
                    done.append(ch)
                except CalendarError as exc:
                    failed = {"change": ch, "error": str(exc)}
                    break
            complete = failed is None
            conn.execute("UPDATE calendar_sync SET state = %s, synced_plan_hash = CASE WHEN %s THEN %s "
                         "ELSE synced_plan_hash END, preview_hash = NULL WHERE trip_id = %s",
                         ("synced" if complete else "drifted", complete, trip["plan_hash"], trip["id"]))
        remaining = changes[len(done):]  # applied in order: the failed change and everything after it
        return {"stale": False, "applied": len(done), "failed": failed, "not_done": remaining,
                "state": "synced" if failed is None else "drifted"}

    def disconnect(self, user_id: str, delete_calendar: bool) -> dict:
        """Revoke the token; the calendars stay in Google unless the user asked to delete them."""
        deleted = 0
        with self.pool.connection() as conn:
            rows = conn.execute("SELECT s.trip_id, s.calendar_id FROM calendar_sync s JOIN trips t ON t.id = s.trip_id "
                                "WHERE t.user_id = %s", (user_id,)).fetchall()
        if delete_calendar and rows:
            api = self._client(user_id)
            for r in rows:
                if r["calendar_id"]:
                    api.delete_calendar(r["calendar_id"])
                    deleted += 1
        with self.pool.connection() as conn:
            for r in rows:
                conn.execute("DELETE FROM calendar_events WHERE trip_id = %s", (r["trip_id"],))
                conn.execute("DELETE FROM calendar_sync WHERE trip_id = %s", (r["trip_id"],))
        self.accounts.unlink_calendar(user_id)
        return {"disconnected": True, "calendars_deleted": deleted}
