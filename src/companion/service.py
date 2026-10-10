"""Đang đi (docs/P5_COMPANION.md): the Today view of a confirmed trip, voluntary check-ins, skips and 👍 / 👎, what to do
here and nearby, and the neutral "rest of the day is tight" options. Never a "missed" state: a stop nobody checked in
at stays planned, which means unknown."""

import uuid
from datetime import datetime
from pathlib import Path

import yaml
from decision import hard_check

from . import suggest
from .trips import TZ, sync

ROOT = Path(__file__).resolve().parents[2]


def load_settings(path: Path = ROOT / "config" / "companion.yaml") -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _hm(t: datetime | None) -> str | None:
    return t.astimezone(TZ).strftime("%H:%M") if t else None


class Companion:
    def __init__(self, pool, records: list[dict], cfg: dict | None = None, now=None):
        """records: serving records (corpus.serving.load()); now: clock for tests."""
        self.pool, self.cfg = pool, cfg or load_settings()
        self.records = {r["id"]: r for r in records}
        self._now = now or (lambda: datetime.now(TZ))

    def now(self) -> datetime:
        return self._now().astimezone(TZ)

    # --- trip rows ---------------------------------------------------------------------------------------------

    def sync(self, journey_id: str, user_id: str | None, plan: dict) -> str:
        with self.pool.connection() as conn:
            return sync(conn, journey_id, user_id, plan)

    def _trip(self, conn, journey_id: str) -> dict:
        trip = conn.execute("SELECT * FROM trips WHERE journey_id = %s", (journey_id,)).fetchone()
        if not trip:
            raise KeyError(journey_id)
        return trip

    def _stops(self, conn, trip_id) -> list[dict]:
        return [dict(r) for r in conn.execute("SELECT * FROM trip_stops WHERE trip_id = %s ORDER BY day, seq",
                                              (trip_id,))]

    def _stop(self, conn, trip_id, stop_id: str) -> dict:
        try:
            stop_id = str(uuid.UUID(stop_id))
        except (TypeError, ValueError, AttributeError):
            raise ValueError("bad stop_id") from None
        row = conn.execute("SELECT * FROM trip_stops WHERE trip_id = %s AND id = %s", (trip_id, stop_id)).fetchone()
        if not row:
            raise ValueError("no such stop on this trip")
        return row

    # --- reads -------------------------------------------------------------------------------------------------

    def today(self, journey_id: str, plan: dict, day: int | None = None) -> dict:
        """The trip by day with the stops' state; `day` defaults to today's day of the trip, else the first."""
        now = self.now()
        with self.pool.connection() as conn:
            trip = self._trip(conn, journey_id)
            stops = self._stops(conn, trip["id"])
            last = conn.execute("SELECT place_id, stop_id, at FROM checkins WHERE trip_id = %s ORDER BY at DESC LIMIT 1",
                                (trip["id"],)).fetchone()
            cal = conn.execute("SELECT state FROM calendar_sync WHERE trip_id = %s", (trip["id"],)).fetchone()
            off_plan = conn.execute("SELECT id, place_id, at FROM checkins WHERE trip_id = %s AND stop_id IS NULL "
                                    "ORDER BY at", (trip["id"],)).fetchall()
        days = plan.get("itinerary") or []
        today = now.date().isoformat()
        current = next((d["day"] for d in days if d.get("date") == today), None)
        shown = day or current or (days[0]["day"] if days else 1)
        by_day = []
        for d in days:
            by_day.append({"day": d["day"], "date": d.get("date"), "window": d.get("window"),
                           "stops": [self._stop_view(s) for s in stops if s["day"] == d["day"]]})
        extra = [self._stop_view(s) for s in stops if s["day"] not in {d["day"] for d in days}]
        extra += [self._off_plan_view(c, days) for c in off_plan]
        status = trip["status"]
        if trip["end_date"] and now.date() > trip["end_date"]:
            status = "done"
        starts_in = (trip["start_date"] - now.date()).days if trip["start_date"] else None
        return {"trip": {"id": str(trip["id"]), "start_date": trip["start_date"] and trip["start_date"].isoformat(),
                         "end_date": trip["end_date"] and trip["end_date"].isoformat(), "status": status,
                         "starts_in": starts_in if starts_in and starts_in > 0 else 0},
                "day": shown, "today": current, "days": by_day, "extra": extra,
                "here": {"place_id": last["place_id"], "stop_id": last["stop_id"] and str(last["stop_id"]),
                         "at": _hm(last["at"])} if last else None,
                "tight": self._tight(stops, plan, now),
                "warnings": plan.get("warnings") or [],
                "conditions": next((c for c in plan.get("day_conditions") or [] if c.get("day") == shown), None),
                "calendar": cal["state"] if cal else "none"}

    @staticmethod
    def _stop_view(s: dict) -> dict:
        return {"id": str(s["id"]), "day": s["day"], "seq": s["seq"], "place_id": s["place_id"], "name": s["name"],
                "arrive": _hm(s["planned_arrive"]), "leave": _hm(s["planned_leave"]), "status": s["status"],
                "arrived_at": _hm(s["arrived_at"]), "rating": s["rating"], "skip_reason": s["skip_reason"],
                "added_on_trip": s["added_on_trip"]}

    def _off_plan_view(self, c: dict, days: list[dict]) -> dict:
        """A check-in at a place outside the plan ("Tôi đang ở nơi khác"), shaped like a stop of the day it happened."""
        on = c["at"].astimezone(TZ).date().isoformat()
        rec = self.records.get(c["place_id"]) or {}
        return {"id": f"checkin:{c['id']}", "day": next((d["day"] for d in days if d.get("date") == on), None),
                "seq": None, "place_id": c["place_id"], "name": (rec.get("identity") or {}).get("name") or "",
                "arrive": None, "leave": None, "status": "arrived", "arrived_at": _hm(c["at"]), "rating": None,
                "skip_reason": None, "added_on_trip": True, "off_plan": True}

    def _tight(self, stops: list[dict], plan: dict, now: datetime) -> dict | None:
        """After a late check-in today, with planned stops left that day: how late, and the plan's own ways out."""
        arrived = [s for s in stops if s["status"] == "arrived" and s["arrived_at"] and s["planned_arrive"]
                   and s["arrived_at"].astimezone(TZ).date() == now.date()]
        if not arrived:
            return None
        last = max(arrived, key=lambda s: s["arrived_at"])
        late = round((last["arrived_at"] - last["planned_arrive"]).total_seconds() / 60)
        left = [s for s in stops if s["day"] == last["day"] and s["seq"] > last["seq"] and s["status"] == "planned"]
        if late < self.cfg["tight_threshold_min"] or not left:
            return None
        return {"late_min": late, "day": last["day"], "options": self.options(stops, plan, last["day"])}

    def options(self, stops: list[dict], plan: dict, day: int) -> list[dict]:
        """Ways to lighten the rest of a day, all from Planning: its on_delay backups (drop that stop)."""
        planned = {s["place_id"] for s in stops if s["day"] == day and s["status"] == "planned"}
        out = []
        for b in (plan.get("backups") or {}).get("on_delay") or []:
            if b.get("day") == day and b.get("place_id") in planned:
                out.append({"id": f"drop:{b['place_id']}", "text": f"Bỏ {b.get('name') or 'một điểm'} để phần còn lại thong thả",
                            "action": {"type": "drop_place", "place": b["place_id"]}})
        return out

    def option(self, journey_id: str, plan: dict, option_id: str) -> dict:
        """The Planning act behind one adjust option, refused when the option is not offered now."""
        with self.pool.connection() as conn:
            stops = self._stops(conn, self._trip(conn, journey_id)["id"])
        for day in {s["day"] for s in stops}:
            for o in self.options(stops, plan, day):
                if o["id"] == option_id:
                    return o["action"]
        raise ValueError("that option is not offered for this trip now")

    def suggestions(self, journey_id: str, search_input: dict, plan: dict, place_id: str, disliked: set[str],
                    similar: bool = False) -> dict:
        rec = self.records.get(place_id)
        if rec is None:
            raise ValueError("unknown place")
        now = self.now()
        with self.pool.connection() as conn:
            trip = self._trip(conn, journey_id)
            stops = self._stops(conn, trip["id"])
        soft = search_input.get("soft_weights") or []
        hard = search_input.get("hard_filters") or []
        mobility = (search_input.get("context") or {}).get("mobility")
        skip = {s["place_id"] for s in stops} | disliked | {s["place_id"] for s in stops if s["skip_reason"] == "dislike"}
        nxt = next((s for s in stops if s["status"] == "planned" and s["planned_arrive"] and s["planned_arrive"] > now
                    and s["planned_arrive"].astimezone(TZ).date() == now.date()), None)  # today's next stop only
        if nxt:
            budget = round((nxt["planned_arrive"] - now).total_seconds() / 60)
        else:
            end = datetime.combine(now.date(), datetime.strptime(self.cfg["day_end"], "%H:%M").time(), TZ)
            budget = max(0, round((end - now).total_seconds() / 60))
        args = dict(when=now, budget_min=budget, mobility=mobility, soft=soft, hard=hard, skip=skip, cfg=self.cfg)
        return {"place_id": place_id, "play": suggest.play(rec, soft, self.cfg["suggest_count"]),
                "practical": suggest.practical(rec, self.cfg["practical"]),
                "timely": suggest.timely(rec, now, self.cfg["timely_sun"]),
                "nearby": suggest.nearby(rec, self.records, **args),
                "similar": suggest.nearby(rec, self.records, **args, same_group=True) if similar else [],
                "budget_min": budget, "next": self._stop_view(nxt) if nxt else None}

    def quality(self, plan: dict, search_input: dict) -> dict:
        """Hard filters on the planned places: fail must stay 0 (an alarm otherwise); unknown is the share of checks
        that had no evidence either way."""
        places = {i["place_id"] for d in plan.get("itinerary") or [] for i in d.get("items") or []
                  if i.get("kind") == "visit" and i.get("place_id")}
        results = [hard_check(self.records[p], h) for p in places if p in self.records
                   for h in search_input.get("hard_filters") or []]
        return {"places": len(places), "hard_checks": len(results), "hard_fail": results.count("fail"),
                "hard_unknown": results.count("unknown")}

    # --- writes ------------------------------------------------------------------------------------------------

    def checkin(self, journey_id: str, stop_id: str | None = None, place_id: str | None = None) -> dict:
        """"Đã đến": a planned stop, or any served place off the plan ("Tôi đang ở nơi khác")."""
        if bool(stop_id) == bool(place_id):
            raise ValueError("give stop_id or place_id")
        now = self.now()
        with self.pool.connection() as conn:
            trip = self._trip(conn, journey_id)
            if stop_id:
                stop = self._stop(conn, trip["id"], stop_id)
                if stop["planned_arrive"] and stop["planned_arrive"].astimezone(TZ).date() != now.date():
                    raise ValueError("a stop is checked in on its own day only")
                place_id = stop["place_id"]
            else:
                if place_id not in self.records:
                    raise ValueError("unknown place")
                if not self._on_trip(trip, now):
                    raise ValueError("a check-in is only taken during the trip")
                stop = next((s for s in self._stops(conn, trip["id"]) if s["place_id"] == place_id and s["status"] == "planned"
                             and (not s["planned_arrive"] or s["planned_arrive"].astimezone(TZ).date() == now.date())), None)
            if stop:
                conn.execute("UPDATE trip_stops SET status = 'arrived', arrived_at = %s, skip_reason = NULL WHERE id = %s",
                             (now, stop["id"]))
            conn.execute("INSERT INTO checkins (trip_id, stop_id, place_id, at) VALUES (%s, %s, %s, %s)",
                         (trip["id"], stop and stop["id"], place_id, now))
            conn.execute("UPDATE trips SET status = 'active', updated_at = now() WHERE id = %s AND status = 'planned'",
                         (trip["id"],))
        return {"place_id": place_id, "stop_id": stop and str(stop["id"]), "on_plan": bool(stop), "at": _hm(now)}

    @staticmethod
    def _on_trip(trip: dict, now: datetime) -> bool:
        """False only when the trip has dates and today is outside them; an undated trip cannot be told apart."""
        start, end = trip["start_date"], trip["end_date"]
        return not ((start and now.date() < start) or (end and now.date() > end))

    def skip(self, journey_id: str, stop_id: str, reason: str | None = None) -> dict:
        """A skip is something that happened: refused for a stop whose day has not come yet."""
        if reason is not None and reason not in self.cfg["skip_reasons"]:
            raise ValueError("unknown reason")
        with self.pool.connection() as conn:
            trip = self._trip(conn, journey_id)
            stop = self._stop(conn, trip["id"], stop_id)
            if stop["status"] == "arrived":
                raise ValueError("this stop is already checked in")
            if stop["planned_arrive"] and stop["planned_arrive"].astimezone(TZ).date() > self.now().date():
                raise ValueError("a stop is skipped on or after its own day only")
            conn.execute("UPDATE trip_stops SET status = 'skipped', skip_reason = %s WHERE id = %s", (reason, stop["id"]))
        return {"stop_id": stop_id, "status": "skipped"}

    def rate(self, journey_id: str, stop_id: str, value: int | None) -> dict:
        """👍 = 1, 👎 = -1, None takes it back."""
        if value not in (1, -1, None) or isinstance(value, bool):
            raise ValueError("value must be 1, -1 or null")
        with self.pool.connection() as conn:
            trip = self._trip(conn, journey_id)
            stop = self._stop(conn, trip["id"], stop_id)
            conn.execute("UPDATE trip_stops SET rating = %s WHERE id = %s", (value, stop["id"]))
        return {"stop_id": stop_id, "rating": value}
