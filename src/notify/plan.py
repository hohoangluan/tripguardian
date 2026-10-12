"""Pure parts of the notifications (docs/COMPANION.md §Thông báo): which notes a trip gets and when, the send rules
(quiet hours, daily caps, per-kind switches, pause), and filling a reviewed template. No I/O here."""

import hashlib
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from corpus.ontology import load as load_ontology
from corpus.serving import feature
from live import sun_times

ROOT = Path(__file__).resolve().parents[2]
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
SLOT = re.compile(r"\{(\w+)\}")
FIRM = ("VERIFIED", "OUTDATED")
WEEKDAY = ("thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật")
TRIP_KINDS = ("book_ahead", "eve_of_trip", "day_brief", "checkin_hint", "golden_hour", "post_trip")
FORBIDDEN = ("bạn đã lỡ", "bạn chưa check-in", "bạn chưa check in", "người khác")


def load_settings(path: Path = ROOT / "config" / "notifications.yaml") -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _clock(s: str) -> time:
    return datetime.strptime(s, "%H:%M").time()


def at(day: date, clock: str) -> datetime:
    return datetime.combine(day, _clock(clock), TZ)


def hm(t: datetime) -> str:
    return t.astimezone(TZ).strftime("%H:%M")


# --- templates ------------------------------------------------------------------------------------------------

def render(kind_cfg: dict, data: dict, seed: str, pick=None) -> tuple[str, str, str] | None:
    """(variant id, title, body) from a variant whose every slot has a real value; None when no variant can be
    filled. pick(variant ids) -> id chooses (the bandit); without one, seed picks (stable per notification)."""
    usable = [v for v in kind_cfg["variants"]
              if all(data.get(k) not in (None, "") for k in SLOT.findall(v["title"] + v["body"]))]
    if not usable:
        return None
    chosen = pick([v["id"] for v in usable]) if pick and len(usable) > 1 else None
    v = next((x for x in usable if x["id"] == chosen), None) or \
        usable[int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(usable)]
    fill = {k: str(x) for k, x in data.items() if x is not None}
    return v["id"], v["title"].format(**fill), v["body"].format(**fill)


# --- what a trip gets -----------------------------------------------------------------------------------------

def _when(t: datetime) -> str:
    h = t.astimezone(TZ).hour
    part = "sáng" if h < 11 else "trưa" if h < 14 else "chiều" if h < 18 else "tối"
    return f"{part} {WEEKDAY[t.astimezone(TZ).weekday()]}"


def highlight(rec: dict | None) -> str | None:
    """A short phrase for the best-supported experience of a place (its ontology hint), or None."""
    if not rec:
        return None
    ont = load_ontology().features
    found = sorted(((f.get("n", 0), fid) for fid, f in (rec.get("experience") or {}).items()
                    if f.get("status") in FIRM and f.get("value") == "present" and fid in ont), reverse=True)
    for _, fid in found:
        hint = ont[fid].hint
        if len(hint) <= 45 and not any(c in hint for c in '"(:/'):
            return hint
    return None


def _firm(rec: dict | None, fid: str, value: str) -> bool:
    f = feature(rec, fid) if rec else None
    return bool(f and f.get("status") in FIRM and f.get("value") == value)


def trip_notes(trip: dict, stops: list[dict], plan: dict, records: dict[str, dict], cfg: dict) -> list[dict]:
    """Every note a confirmed trip may get: {kind, key, scheduled_at, valid_until, data}. Data still unknown at
    planning time (the forecast) is filled when the note is sent."""
    kinds, out = cfg["kinds"], []
    start, end = trip["start_date"], trip["end_date"]
    timed = sorted((s for s in stops if s["planned_arrive"]), key=lambda s: s["planned_arrive"])

    def add(kind, key, when, data, valid_h=None):
        valid = when + timedelta(hours=valid_h if valid_h is not None else kinds[kind].get("valid_h", 2))
        out.append({"kind": kind, "key": key, "scheduled_at": when, "valid_until": valid, "data": data})

    if start:
        booking = next((s for s in timed if _firm(records.get(s["place_id"]), "booking_needed", "yes")), None)
        if booking:
            add("book_ahead", "book_ahead", at(start - timedelta(days=3), "10:00"),
                {"place": booking["name"], "when": _when(booking["planned_arrive"])})
        add("eve_of_trip", "eve_of_trip", at(start - timedelta(days=1), "20:00"), {"weather": True})
    loads = {t["day"]: t for t in plan.get("travel_load") or []}
    for d in plan.get("itinerary") or []:
        if not d.get("date"):
            continue
        day = date.fromisoformat(d["date"])
        mine = [s for s in timed if s["day"] == d["day"]]
        if mine:
            add("day_brief", f"day_brief:{d['day']}", at(day, "07:30"),
                {"d": d["day"], "n": len(mine), "travel": (loads.get(d["day"]) or {}).get("travel_min"),
                 "first": mine[0]["name"], "time": hm(mine[0]["planned_arrive"])})
        for s in mine:
            rec = records.get(s["place_id"]) or {}
            ident = rec.get("identity") or {}
            if ident.get("lat") is None:
                continue
            sun = sun_times(day, ident["lat"], ident["lng"])
            if not sun:
                continue
            for fid, minute in (("sunset_view", sun[1]), ("cloud_hunting", sun[0])):
                if not _firm(rec, fid, "present"):
                    continue
                moment = datetime.combine(day, time(minute // 60, minute % 60), TZ)
                g = kinds["golden_hour"]
                if s["planned_leave"] and s["planned_leave"] < moment - timedelta(minutes=g["lead_min"]):
                    continue  # the stop is over before the light: nothing to catch
                add("golden_hour", f"golden_hour:{d['day']}:{fid}", moment - timedelta(minutes=g["lead_min"]),
                    {"sunset": hm(moment), "place": s["name"], "by": hm(moment - timedelta(minutes=g["arrive_by_min"]))},
                    valid_h=g["lead_min"] / 60)
                break
    for s in timed[: kinds["checkin_hint"]["first_stops"]]:
        add("checkin_hint", f"checkin_hint:{s['id']}", s["planned_arrive"],
            {"place": s["name"], "highlight": highlight(records.get(s["place_id"]))})
    if end:
        add("post_trip", "post_trip", at(end + timedelta(days=1), "10:00"), {})
    return out


def rain_phrase(prob: float | None) -> tuple[str | None, str | None]:
    """(rain phrase, what to pack) from a forecast; (None, None) without one."""
    if prob is None:
        return None, None
    if prob >= 0.6:
        return f"khả năng mưa {round(prob * 100)}%", "áo mưa và áo khoác"
    if prob >= 0.3:
        return "có thể mưa rào", "áo khoác mỏng và ô nhỏ"
    return "trời ít mưa", "áo khoác"


# --- send rules -----------------------------------------------------------------------------------------------

def decide(note: dict, prefs: dict, sent_today: int, trip_days: tuple[date | None, date | None], now: datetime,
           cfg: dict) -> tuple[str, object]:
    """("send", None) | ("later", new time) | ("skip", reason). Order: switches, pause, expiry, quiet hours, cap."""
    local = now.astimezone(TZ)
    kinds = prefs.get("enabled_kinds")
    if kinds is not None and note["kind"] not in kinds and note["kind"] != "paused":
        return "skip", "kind_off"
    if prefs.get("paused_until") and now < prefs["paused_until"] and note["kind"] != "paused":
        return "skip", "paused"
    if now > note["valid_until"]:
        return "skip", "expired"
    q_start, q_end = _clock(prefs.get("quiet_start") or cfg["quiet"][0]), _clock(prefs.get("quiet_end") or cfg["quiet"][1])
    t = local.time()
    quiet = (q_start <= t or t < q_end) if q_start > q_end else (q_start <= t < q_end)
    if quiet:
        wake = datetime.combine(local.date() + (timedelta(days=1) if t >= q_end else timedelta()), q_end, TZ)
        return ("later", wake) if wake <= note["valid_until"] else ("skip", "quiet_expired")
    start, end = trip_days
    during = bool(start and end and start <= local.date() <= end)
    if sent_today >= cfg["per_day"]["during" if during else "before"]:
        return "skip", "daily_cap"
    return "send", None


def bandit(stats: dict[str, tuple[int, int]], min_sends: int, rng) -> object:
    """A pick(variant ids) for render: Thompson sampling on (sends, rewards) once every candidate has min_sends;
    before that, None (the stable seed spreads sends evenly)."""
    def pick(ids: list[str]) -> str | None:
        if any(stats.get(i, (0, 0))[0] < min_sends for i in ids):
            return None
        return max(ids, key=lambda i: rng.betavariate(stats[i][1] + 1, stats[i][0] - stats[i][1] + 1))
    return pick
