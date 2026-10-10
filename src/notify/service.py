"""Notifications in Postgres + web push (docs/P5_COMPANION.md §Thông báo). The worker (`python -m notify run`) plans
the notes of every confirmed trip, checks the forecast during trips and sends what is due; the harness uses the
same class for the inbox, preferences and push subscriptions. Every note sent also stays in the inbox."""

import json
import os
import random
import sys
import time as clock
from datetime import datetime, timedelta, UTC

from psycopg.types.json import Jsonb

from . import plan as P

FOREVER = datetime(9999, 1, 1, tzinfo=UTC)


class Gone(Exception):
    """The push service says this subscription no longer exists (404 / 410)."""


def web_push(sub: dict, payload: dict) -> None:
    from pywebpush import WebPushException, webpush
    try:
        webpush(subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                data=json.dumps(payload, ensure_ascii=False), vapid_private_key=os.environ["VAPID_PRIVATE_KEY"],
                vapid_claims={"sub": os.environ.get("VAPID_SUBJECT", "")}, ttl=3600)
    except WebPushException as exc:
        if exc.response is not None and exc.response.status_code in (404, 410):
            raise Gone() from exc
        raise


class Notify:
    def __init__(self, pool, records: list[dict] | dict, cfg: dict | None = None, push=web_push, weather=None,
                 now=None):
        """push(sub, payload) sends one web push; weather(lat, lng, dates) -> {date: {"rain_prob", "source"}}."""
        self.pool, self.cfg, self.push = pool, cfg or P.load_settings(), push
        self.records = records if isinstance(records, dict) else {r["id"]: r for r in records}
        self.weather = weather
        self._now = now or (lambda: datetime.now(UTC))
        self._last_weather: datetime | None = None
        self.rng = random.Random()

    def now(self) -> datetime:
        return self._now()

    # --- harness side ------------------------------------------------------------------------------------------

    def public_key(self) -> str:
        return os.environ.get("VAPID_PUBLIC_KEY", "")

    def subscribe(self, user_id: str, sub: dict, user_agent: str = "") -> dict:
        keys = sub.get("keys") if isinstance(sub.get("keys"), dict) else {}
        endpoint, p256dh, auth = sub.get("endpoint"), keys.get("p256dh"), keys.get("auth")
        if not (isinstance(endpoint, str) and endpoint.startswith("https://") and len(endpoint) < 1000
                and isinstance(p256dh, str) and isinstance(auth, str) and len(p256dh) < 200 and len(auth) < 100):
            raise ValueError("bad push subscription")
        with self.pool.connection() as conn:
            conn.execute("INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, user_agent) "
                         "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (endpoint) DO UPDATE SET user_id = EXCLUDED.user_id, "
                         "p256dh = EXCLUDED.p256dh, auth = EXCLUDED.auth", (user_id, endpoint, p256dh, auth, user_agent[:300]))
            conn.execute("INSERT INTO notification_prefs (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
        return {"subscribed": True}

    def unsubscribe(self, user_id: str, endpoint: str) -> dict:
        with self.pool.connection() as conn:
            n = conn.execute("DELETE FROM push_subscriptions WHERE user_id = %s AND endpoint = %s",
                             (user_id, endpoint)).rowcount
        return {"unsubscribed": bool(n)}

    def inbox(self, user_id: str, limit: int = 50) -> list[dict]:
        with self.pool.connection() as conn:
            rows = conn.execute("SELECT id, kind, payload, sent_at, opened_at FROM notifications WHERE user_id = %s "
                                "AND status = 'sent' ORDER BY sent_at DESC LIMIT %s", (user_id, limit)).fetchall()
        return [{"id": str(r["id"]), "kind": r["kind"], "title": r["payload"].get("title"), "body": r["payload"].get("body"),
                 "url": r["payload"].get("url"), "sent_at": r["sent_at"].isoformat(), "opened": r["opened_at"] is not None}
                for r in rows]

    def open(self, user_id: str, note_id: str, action: str | None = None) -> dict:
        """Opened from the push or the inbox: resets the ignored streak (and a pause, since the user came back)."""
        with self.pool.connection() as conn:
            n = conn.execute("UPDATE notifications SET opened_at = coalesce(opened_at, now()), action = coalesce(%s, action) "
                             "WHERE id = %s AND user_id = %s", (action and action[:40], note_id, user_id)).rowcount
            if not n:
                raise KeyError(note_id)
        self.resume(user_id)
        return {"opened": True}

    def resume(self, user_id: str) -> None:
        """The user opened the app: a pause set by the worker ends, the streak starts over."""
        with self.pool.connection() as conn:
            conn.execute("UPDATE notification_prefs SET ignored_streak = 0, paused_until = NULL "
                         "WHERE user_id = %s AND (ignored_streak > 0 OR paused_until = %s)", (user_id, FOREVER))

    def prefs(self, user_id: str) -> dict:
        with self.pool.connection() as conn:
            conn.execute("INSERT INTO notification_prefs (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
            r = conn.execute("SELECT * FROM notification_prefs WHERE user_id = %s", (user_id,)).fetchone()
            subs = conn.execute("SELECT count(*) AS n FROM push_subscriptions WHERE user_id = %s", (user_id,)).fetchone()["n"]
        kinds = [k for k in self.cfg["kinds"] if k != "paused"]
        return {"kinds": kinds, "enabled_kinds": r["enabled_kinds"] if r["enabled_kinds"] is not None else kinds,
                "quiet_start": r["quiet_start"].strftime("%H:%M"), "quiet_end": r["quiet_end"].strftime("%H:%M"),
                "paused": r["paused_until"] is not None and r["paused_until"] > self.now(), "push_devices": subs}

    def set_prefs(self, user_id: str, patch: dict) -> dict:
        if not patch or set(patch) - {"enabled_kinds", "paused"}:
            raise ValueError("unknown notification setting")
        self.prefs(user_id)
        with self.pool.connection() as conn:
            if "enabled_kinds" in patch:
                kinds = patch["enabled_kinds"]
                if not isinstance(kinds, list) or any(k not in self.cfg["kinds"] or k == "paused" for k in kinds):
                    raise ValueError("unknown notification kind")
                conn.execute("UPDATE notification_prefs SET enabled_kinds = %s WHERE user_id = %s", (kinds, user_id))
            if "paused" in patch:
                if not isinstance(patch["paused"], bool):
                    raise ValueError("paused must be true or false")
                conn.execute("UPDATE notification_prefs SET paused_until = %s, ignored_streak = 0 WHERE user_id = %s",
                             (FOREVER if patch["paused"] else None, user_id))
        return self.prefs(user_id)

    # --- worker: planning ----------------------------------------------------------------------------------------

    def schedule(self) -> int:
        """(Re)plan the notes of trips whose plan changed since their notes were made: unsent ones are cancelled
        and made again; a key already sent (day 1's brief, say) is not sent twice."""
        now, made = self.now(), 0
        with self.pool.connection() as conn:
            trips = conn.execute(
                "SELECT t.*, j.envelope->'outputs'->'planning' AS plan FROM trips t JOIN journeys j ON j.id = t.journey_id "
                "WHERE t.user_id IS NOT NULL AND (t.end_date IS NULL OR t.end_date >= %s) AND NOT EXISTS ("
                "SELECT 1 FROM notifications n WHERE n.trip_id = t.id AND n.payload->>'plan_hash' = t.plan_hash)",
                (now.date() - timedelta(days=2),)).fetchall()
            for trip in trips:
                if not trip["plan"]:
                    continue
                stops = conn.execute("SELECT * FROM trip_stops WHERE trip_id = %s ORDER BY day, seq", (trip["id"],)).fetchall()
                sent = {r["key"] for r in conn.execute("SELECT payload->>'key' AS key FROM notifications "
                                                       "WHERE trip_id = %s AND status = 'sent'", (trip["id"],))}
                conn.execute("UPDATE notifications SET status = 'cancelled' WHERE trip_id = %s AND status = 'scheduled'",
                             (trip["id"],))
                inserted = 0
                for n in P.trip_notes(trip, stops, trip["plan"], self.records, self.cfg):
                    if n["key"] in sent or n["valid_until"] < now:
                        continue
                    self._insert(conn, trip["user_id"], trip["id"], n, trip["plan_hash"])
                    inserted += 1
                made += inserted
                if not inserted:  # keep a marker so an unchanged trip is not planned again every minute
                    self._insert(conn, trip["user_id"], trip["id"], {"kind": "post_trip", "key": "none",
                                 "scheduled_at": now, "valid_until": now, "data": {}}, trip["plan_hash"], status="cancelled")
            made += self._plan_unfinished(conn, now)
        return made

    def _insert(self, conn, user_id, trip_id, n: dict, plan_hash: str | None, status: str = "scheduled") -> None:
        payload = {"key": n["key"], "data": n["data"], "valid_until": n["valid_until"].isoformat(), "plan_hash": plan_hash}
        conn.execute("INSERT INTO notifications (user_id, trip_id, kind, payload, scheduled_at, status) "
                     "VALUES (%s, %s, %s, %s, %s, %s)", (user_id, trip_id, n["kind"], Jsonb(payload), n["scheduled_at"],
                                                         status))

    def _plan_unfinished(self, conn, now: datetime) -> int:
        """One nudge 24 h after the shortlist when the plan was never confirmed (journeys with an owner only)."""
        rows = conn.execute(
            "SELECT j.id, j.user_id, j.envelope, min(e.at) AS at FROM journeys j JOIN events e ON e.journey_id = j.id "
            "AND e.name = 'trip.advance' AND e.props->>'error' IS NULL WHERE j.user_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM events c WHERE c.journey_id = j.id AND c.name = 'planning.confirm') "
            "AND NOT EXISTS (SELECT 1 FROM notifications n WHERE n.kind = 'plan_unfinished' AND n.payload->>'journey' = j.id) "
            "GROUP BY j.id HAVING min(e.at) > %s", (now - timedelta(hours=48),)).fetchall()
        for r in rows:
            snap = ((r["envelope"].get("snapshots") or {}).get("decision") or {}).get("state") or {}
            due = r["at"] + timedelta(hours=24)
            payload = {"key": "plan_unfinished", "journey": r["id"], "data": {"n": len(snap.get("selected") or []) or None},
                       "valid_until": (due + timedelta(hours=self.cfg["kinds"]["plan_unfinished"]["valid_h"])).isoformat()}
            conn.execute("INSERT INTO notifications (user_id, kind, payload, scheduled_at) VALUES (%s, 'plan_unfinished', "
                         "%s, %s)", (r["user_id"], Jsonb(payload), due))
        return len(rows)

    def check_weather(self) -> int:
        """Every few hours on trip days: a high rain chance today with an outdoor stop left -> one note per day."""
        if self.weather is None:
            return 0
        now, made = self.now(), 0
        today = now.astimezone(P.TZ).date()
        with self.pool.connection() as conn:
            trips = conn.execute("SELECT t.*, j.envelope->'outputs'->'planning' AS plan FROM trips t "
                                 "JOIN journeys j ON j.id = t.journey_id WHERE t.user_id IS NOT NULL "
                                 "AND t.start_date <= %s AND t.end_date >= %s", (today, today)).fetchall()
            for trip in trips:
                key = f"weather_change:{today.isoformat()}"
                if conn.execute("SELECT 1 FROM notifications WHERE trip_id = %s AND payload->>'key' = %s",
                                (trip["id"], key)).fetchone():
                    continue
                stops = conn.execute("SELECT * FROM trip_stops WHERE trip_id = %s AND status = 'planned' "
                                     "AND planned_arrive > %s ORDER BY planned_arrive", (trip["id"], now)).fetchall()
                outdoor = next((s for s in stops if s["planned_arrive"].astimezone(P.TZ).date() == today and (
                    P._firm(self.records.get(s["place_id"]), "weather_exposed", "present")
                    or P._firm(self.records.get(s["place_id"]), "setting", "outdoor"))), None)
                if not outdoor or not ((trip["plan"] or {}).get("backups") or {}).get("places"):
                    continue  # nothing exposed today, or no other option in the plan to point to
                ident = (self.records.get(outdoor["place_id"]) or {}).get("identity") or {}
                try:
                    day = self.weather(ident.get("lat"), ident.get("lng"), [today.isoformat()]).get(today.isoformat()) or {}
                except Exception as exc:
                    print(f"weather check failed: {exc}", file=sys.stderr)
                    continue
                if day.get("source") != "open-meteo" or (day.get("rain_prob") or 0) < self.cfg["rain_alert"]:
                    continue
                self._insert(conn, trip["user_id"], trip["id"], {
                    "kind": "weather_change", "key": key, "scheduled_at": now,
                    "valid_until": now + timedelta(hours=self.cfg["kinds"]["weather_change"]["valid_h"]),
                    "data": {"p": round(day["rain_prob"] * 100), "place": outdoor["name"]}}, trip["plan_hash"])
                made += 1
        return made

    # --- worker: sending ------------------------------------------------------------------------------------------

    def _fill(self, conn, note: dict) -> dict:
        data = dict(note["payload"].get("data") or {})
        if data.pop("weather", None) and note["trip_id"]:  # eve of trip: the forecast is read when it is sent
            trip = conn.execute("SELECT start_date FROM trips WHERE id = %s", (note["trip_id"],)).fetchone()
            prob = None
            if self.weather and trip and trip["start_date"]:
                try:
                    day = self.weather(11.9404, 108.4583, [trip["start_date"].isoformat()]).get(trip["start_date"].isoformat()) or {}
                    prob = day.get("rain_prob") if day.get("source") == "open-meteo" else None
                except Exception as exc:
                    print(f"weather for eve_of_trip failed: {exc}", file=sys.stderr)
            data["rain_phrase"], data["pack"] = P.rain_phrase(prob)
            data["t_min"] = None  # the forecast has no temperature: the variant that needs it is not used
        return data

    def _link(self, conn, note: dict) -> str:
        path = self.cfg["links"].get(note["kind"], "/app")
        journey = note["payload"].get("journey")
        if not journey and note["trip_id"]:
            row = conn.execute("SELECT journey_id FROM trips WHERE id = %s", (note["trip_id"],)).fetchone()
            journey = row and row["journey_id"]
        sep = "&" if "?" in path else "?"
        return f"{path}{sep}{'journey=' + journey + '&' if journey else ''}n={note['id']}"

    def send_due(self) -> dict:
        now, counts = self.now(), {"sent": 0, "skipped": 0, "later": 0}
        with self.pool.connection() as conn:
            due = conn.execute("SELECT * FROM notifications WHERE status = 'scheduled' AND scheduled_at <= %s "
                               "ORDER BY scheduled_at LIMIT 200", (now,)).fetchall()
        for note in due:
            outcome = self._send_one(note, now)
            counts[outcome] += 1
        return counts

    def _skip(self, conn, note_id, reason: str) -> str:
        conn.execute("UPDATE notifications SET status = 'skipped', skip_reason = %s WHERE id = %s", (reason, note_id))
        return "skipped"

    def _send_one(self, note: dict, now: datetime) -> str:
        with self.pool.connection() as conn:
            if not note["user_id"]:
                return self._skip(conn, note["id"], "no_user")
            conn.execute("INSERT INTO notification_prefs (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (note["user_id"],))
            prefs = dict(conn.execute("SELECT * FROM notification_prefs WHERE user_id = %s FOR UPDATE",
                                      (note["user_id"],)).fetchone())
            prefs["quiet_start"], prefs["quiet_end"] = prefs["quiet_start"].strftime("%H:%M"), prefs["quiet_end"].strftime("%H:%M")
            local_day = now.astimezone(P.TZ).date()
            start_of_day = datetime.combine(local_day, datetime.min.time(), P.TZ)
            sent_today = conn.execute("SELECT count(*) AS n FROM notifications WHERE user_id = %s AND status = 'sent' "
                                      "AND sent_at >= %s", (note["user_id"], start_of_day)).fetchone()["n"]
            trip = conn.execute("SELECT start_date, end_date FROM trips WHERE id = %s", (note["trip_id"],)).fetchone() \
                if note["trip_id"] else None
            note = {**note, "valid_until": datetime.fromisoformat(note["payload"]["valid_until"])}
            verdict, arg = P.decide(note, prefs, sent_today, (trip and trip["start_date"], trip and trip["end_date"]),
                                    now, self.cfg)
            if verdict == "skip":
                return self._skip(conn, note["id"], arg)
            if verdict == "later":
                conn.execute("UPDATE notifications SET scheduled_at = %s WHERE id = %s", (arg, note["id"]))
                return "later"
            filled = P.render(self.cfg["kinds"][note["kind"]], self._fill(conn, note), str(note["id"]),
                              P.bandit(self._variant_stats(conn, note["kind"]), self.cfg["bandit_min_sends"], self.rng))
            if filled is None:
                return self._skip(conn, note["id"], "no_data")
            if note["kind"] != "paused":
                last = conn.execute("SELECT opened_at IS NULL AS ignored FROM notifications WHERE user_id = %s "
                                    "AND status = 'sent' AND kind <> 'paused' ORDER BY sent_at DESC LIMIT 1",
                                    (note["user_id"],)).fetchone()
                streak = prefs["ignored_streak"] + (1 if last and last["ignored"] else 0)
                conn.execute("UPDATE notification_prefs SET ignored_streak = %s WHERE user_id = %s",
                             (streak, note["user_id"]))
                if streak >= self.cfg["pause_after_ignored"]:
                    self._pause(conn, note, now)
                    return self._skip(conn, note["id"], "paused")
            variant, title, body = filled
            url = self._link(conn, note)
            subs = conn.execute("SELECT * FROM push_subscriptions WHERE user_id = %s", (note["user_id"],)).fetchall()
            conn.execute("UPDATE notifications SET status = 'sent', sent_at = %s, template_id = %s, variant = %s, "
                         "payload = payload || %s WHERE id = %s",
                         (now, note["kind"], variant, Jsonb({"title": title, "body": body, "url": url}), note["id"]))
        for sub in subs:  # the inbox copy is already stored; a push that fails does not undo it
            try:
                self.push(sub, {"id": str(note["id"]), "title": title, "body": body, "url": url})
            except Gone:
                with self.pool.connection() as conn:
                    conn.execute("DELETE FROM push_subscriptions WHERE id = %s", (sub["id"],))
            except Exception as exc:
                print(f"push failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return "sent"

    def _variant_stats(self, conn, kind: str) -> dict[str, tuple[int, int]]:
        """(sends, rewards) per variant over 60 days; reward = opened, then a journey action by the same user within
        open_window_h (docs/ANALYTICS.md §Thông báo)."""
        rows = conn.execute(
            "SELECT variant, count(*) AS sends, count(*) FILTER (WHERE opened_at IS NOT NULL AND EXISTS ("
            "SELECT 1 FROM events e WHERE e.user_id = n.user_id AND e.source = 'server' AND e.at > n.opened_at "
            "AND e.at <= n.opened_at + make_interval(hours => %s))) AS rewards FROM notifications n "
            "WHERE kind = %s AND status = 'sent' AND sent_at > now() - interval '60 days' GROUP BY variant",
            (self.cfg["open_window_h"], kind)).fetchall()
        return {r["variant"]: (r["sends"], r["rewards"]) for r in rows}

    def _pause(self, conn, note: dict, now: datetime) -> None:
        """Three notes in a row went unopened: say so once, then stay quiet until the user opens the app."""
        conn.execute("UPDATE notification_prefs SET paused_until = %s WHERE user_id = %s", (FOREVER, note["user_id"]))
        payload = {"key": "paused", "data": {}, "valid_until": (now + timedelta(hours=24)).isoformat()}
        conn.execute("INSERT INTO notifications (user_id, kind, payload, scheduled_at) VALUES (%s, 'paused', %s, %s)",
                     (note["user_id"], Jsonb(payload), now))

    # --- the loop -----------------------------------------------------------------------------------------------------

    def tick(self) -> dict:
        out = {"planned": self.schedule()}
        if self._last_weather is None or self.now() - self._last_weather >= timedelta(hours=self.cfg["weather_every_h"]):
            out["weather"] = self.check_weather()
            self._last_weather = self.now()
        out.update(self.send_due())
        return out

    def run(self, once: bool = False) -> None:
        while True:
            try:
                out = self.tick()
                if any(out.values()):
                    print(f"{datetime.now():%H:%M:%S} {out}", flush=True)
            except Exception as exc:  # one bad tick must not stop the worker
                print(f"tick failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            if once:
                return
            clock.sleep(self.cfg["tick_s"])
