"""A confirmed Plan Output becomes a trip with one row per stop (tables trips, trip_stops). Confirming again moves the
stops not visited yet and never touches a stop the user already checked in at or skipped."""

import hashlib
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _at(day: str | None, clock: str | None) -> datetime | None:
    if not day or not clock:
        return None
    return datetime.combine(date.fromisoformat(day), datetime.strptime(clock, "%H:%M").time(), TZ)


def stops_of(plan: dict) -> list[dict]:
    """Visits of the itinerary in order: {day (1-based), seq, place_id, name, arrive, leave} (times None undated)."""
    out = []
    for d in plan.get("itinerary") or []:
        seq = 0
        for item in d.get("items") or []:
            if item.get("kind") != "visit" or not item.get("place_id"):
                continue
            seq += 1
            out.append({"day": d["day"], "seq": seq, "place_id": item["place_id"], "name": item.get("name") or "",
                        "arrive": _at(d.get("date"), item.get("start")), "leave": _at(d.get("date"), item.get("end"))})
    return out


def plan_hash(stops: list[dict]) -> str:
    rows = [[s["day"], s["seq"], s["place_id"], s["arrive"] and s["arrive"].isoformat(),
             s["leave"] and s["leave"].isoformat()] for s in stops]
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()[:16]


def sync(conn, journey_id: str, user_id: str | None, plan: dict) -> str:
    """Create or update the trip of a journey from its confirmed plan; returns the trip id."""
    stops = stops_of(plan)
    dates = [d["date"] for d in plan.get("itinerary") or [] if d.get("date")]
    digest = plan_hash(stops)
    trip = conn.execute(
        "INSERT INTO trips (journey_id, user_id, start_date, end_date, plan_hash) VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (journey_id) DO UPDATE SET start_date = EXCLUDED.start_date, end_date = EXCLUDED.end_date, "
        "plan_hash = EXCLUDED.plan_hash, updated_at = now() RETURNING id",
        (journey_id, user_id, min(dates) if dates else None, max(dates) if dates else None, digest)).fetchone()["id"]
    rows = conn.execute("SELECT id, place_id, status FROM trip_stops WHERE trip_id = %s ORDER BY day, seq",
                        (trip,)).fetchall()
    done = {r["place_id"] for r in rows if r["status"] != "planned"}
    planned = [r for r in rows if r["status"] == "planned"]
    used: set = set()
    for s in stops:
        if s["place_id"] in done:
            continue  # already checked in or skipped: that row stays as it happened
        row = next((r for r in planned if r["place_id"] == s["place_id"] and r["id"] not in used), None)
        if row:
            used.add(row["id"])
            conn.execute("UPDATE trip_stops SET day = %s, seq = %s, name = %s, planned_arrive = %s, planned_leave = %s "
                         "WHERE id = %s", (s["day"], s["seq"], s["name"], s["arrive"], s["leave"], row["id"]))
        else:
            conn.execute("INSERT INTO trip_stops (trip_id, day, seq, place_id, name, planned_arrive, planned_leave) "
                         "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                         (trip, s["day"], s["seq"], s["place_id"], s["name"], s["arrive"], s["leave"]))
    for r in planned:
        if r["id"] not in used:
            conn.execute("DELETE FROM trip_stops WHERE id = %s", (r["id"],))
    conn.execute("UPDATE calendar_sync SET state = 'drifted' WHERE trip_id = %s AND state = 'synced' "
                 "AND synced_plan_hash IS DISTINCT FROM %s", (trip, digest))
    return str(trip)
