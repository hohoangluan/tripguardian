"""What the date itself changes (docs/P4_PLANNING.md §Điều kiện từng ngày): weather beyond rain probability, crowds on
weekends / holidays / festivals, shops closed for Tết, hazard notices.

Pure: the facts arrive from src/live (fetch() is the one place that calls it). A day with no signal has no DayCond, so
everything built on it stays inert. Nothing here invents a figure; an unknown stays unknown and is worded that way.
"""

import math
from dataclasses import dataclass
from datetime import date, timedelta

import live

from .model import Day, Place
from .settings import Settings
from .traits import crowd, exposure
from .travel import km

BUCKETS = ("morning", "noon", "afternoon", "evening")
BUCKET_TEXT = {"morning": "buổi sáng", "noon": "buổi trưa", "afternoon": "buổi chiều", "evening": "buổi tối"}
DAY_TYPE_TEXT = {"weekday": "ngày thường", "weekend": "cuối tuần", "holiday": "ngày lễ"}
WIDE_KINDS = ("flood", "landslide", "fire", "road_closed", "other")   # hurt every place in scope, not only exposed ones


@dataclass(frozen=True)
class DayCond:
    weather: str = "none"                       # none | heavy | severe
    storm: bool = False
    rain_mm: float | None = None
    gust_kmh: float | None = None
    day_type: str = "weekday"                   # weekday | weekend | holiday: the key of a place's crowd_by_time
    crowd: str = "normal"                       # normal | busy | peak
    crowd_reasons: tuple[str, ...] = ()
    closure_risk: str | None = None             # name of the period many shops close in
    advisories: tuple[dict, ...] = ()


def weather_level(w: dict | None, cfg: Settings) -> str:
    """none | heavy | severe from a live.weather day. Missing figures count for nothing."""
    if not w:
        return "none"
    c, mm, gust = cfg.conditions, w.get("rain_mm"), w.get("gust_kmh")
    if (mm is not None and mm >= c["severe_rain_mm"]) or (gust is not None and gust >= c["severe_gust_kmh"]):
        return "severe"
    if w.get("storm") or (mm is not None and mm >= c["heavy_rain_mm"]) or (gust is not None and gust >= c["heavy_gust_kmh"]):
        return "heavy"
    return "none"


def build_cond(day: Day, weather: dict | None, signals: dict | None, cfg: Settings) -> DayCond | None:
    """None when the day has no date, or nothing was fetched for it (no signals and no extended weather figures)."""
    if day.date is None:
        return None
    w = (weather or {}).get(day.date.isoformat())
    sig = (signals or {}).get(day.date.isoformat())
    extended = bool(w) and any(w.get(k) is not None for k in ("rain_mm", "gust_kmh", "storm"))
    if signals is None and not extended:
        return None
    sig = sig or {}
    events, holiday = sig.get("events") or [], sig.get("holiday")
    peak = bool(holiday) or any(e["crowd"] == "peak" for e in events)
    weekend = day.weekday in ("sat", "sun")
    reasons = ([f"Ngày lễ: {holiday}"] if holiday else []) + [e["name"] for e in events] \
        + (["Cuối tuần"] if weekend and not holiday else [])
    closing = next((e["name"] for e in events if e.get("closure_risk")), None)
    return DayCond(weather=weather_level(w, cfg), storm=bool(w and w.get("storm")),
                   rain_mm=w.get("rain_mm") if w else None, gust_kmh=w.get("gust_kmh") if w else None,
                   day_type="holiday" if peak else "weekend" if weekend else "weekday",
                   crowd="peak" if peak else "busy" if (weekend or events) else "normal",
                   crowd_reasons=tuple(reasons), closure_risk=closing, advisories=tuple(sig.get("advisories") or ()))


# ---------- what a condition means for one place ----------

def advisory_hits(p: Place, cond: DayCond | None) -> list[dict]:
    """Notices whose area covers the place: the city, or a circle around a point."""
    out = []
    for a in (cond.advisories if cond else ()):
        area = a["area"]
        if area == "city" or km((p.lat, p.lng), (area["lat"], area["lng"])) <= area["radius_km"]:
            out.append(a)
    return out


def hazard(p: Place, cond: DayCond | None) -> str | None:
    """Why the place cannot be scheduled that day at all (fail-closed), or None. A severe storm or rain keeps out only
    weather-exposed places; a severe flood / landslide / fire / closed-road notice keeps out every place in its area."""
    if cond is None:
        return None
    exposed = exposure(p) == "exposed"
    if cond.weather == "severe" and exposed:
        return "weather_severe"
    for a in advisory_hits(p, cond):
        if a["severity"] == "severe" and (exposed or a["kind"] in WIDE_KINDS):
            return f"advisory:{a['kind']}"
    return None


def warned(p: Place, cond: DayCond | None) -> bool:
    """A notice below severe covers the place: scheduled, but flagged and given a backup."""
    return bool(cond) and hazard(p, cond) is None and bool(advisory_hits(p, cond))


def busy_buckets(p: Place, day_type: str, cfg: Settings) -> list[str]:
    """Times of day the place's own popular-times data says are busy on this kind of day."""
    row = (p.rec["operation"].get("crowd_by_time") or {}).get(day_type) or {}
    return [b for b in BUCKETS if row.get(b, 0) >= cfg.crowd_busy_pct]


def crowd_sensitive(p: Place, cond: DayCond | None, cfg: Settings) -> bool:
    """The place is busy on this kind of day, by its own evidence: a verified `crowd = high`, or popular-times busy."""
    if cond is None or cond.crowd == "normal":
        return False
    return crowd(p) == "high" or bool(busy_buckets(p, cond.day_type, cfg))


def queue_minutes(p: Place, visit: int, cond: DayCond | None, cfg: Settings) -> int:
    """Minutes a visit to a crowd-sensitive place grows by on a busy day."""
    if not crowd_sensitive(p, cond, cfg):
        return 0
    return math.ceil(visit * cfg.conditions["crowd_visit_pct"][cond.crowd] / 100)


def crowd_tips(places: list[Place], conds: list[DayCond | None], cfg: Settings) -> list[dict]:
    """For each crowd-sensitive place: its busiest and calmest time of day on the kind of day the trip has. Only from the
    place's own popular-times figures; a place without them gets no tip."""
    out = []
    for dt in sorted({c.day_type for c in conds if c and c.crowd != "normal"}):
        cond = next(c for c in conds if c and c.crowd != "normal" and c.day_type == dt)
        for p in places:
            row = (p.rec["operation"].get("crowd_by_time") or {}).get(dt) or {}
            if not crowd_sensitive(p, cond, cfg) or not row:
                continue
            busy = max(BUCKETS, key=lambda b: row.get(b, -1))
            calm = min((b for b in BUCKETS if b in row), key=lambda b: row[b], default=None)
            if row.get(busy, 0) >= cfg.crowd_busy_pct and calm and calm != busy:
                out.append({"place_id": p.id, "name": p.name, "day_type": dt, "busy": busy, "calm": calm,
                            "text": f"{p.name}: đông nhất {BUCKET_TEXT[busy]} {DAY_TYPE_TEXT[dt]}, vắng hơn {BUCKET_TEXT[calm]}."})
    return out


def describe(cond: DayCond | None) -> dict | None:
    """One day's conditions for the user: facts and their wording, no decisions."""
    if cond is None:
        return None
    return {"weather": cond.weather, "storm": cond.storm, "rain_mm": cond.rain_mm, "gust_kmh": cond.gust_kmh,
            "day_type": cond.day_type, "crowd": cond.crowd, "crowd_reasons": list(cond.crowd_reasons),
            "closure_risk": cond.closure_risk,
            "advisories": [{k: a[k] for k in ("kind", "severity", "note", "source")} for a in cond.advisories]}


# ---------- fetching (the only I/O) ----------

def trip_dates(decision: dict) -> list[date]:
    ctx = decision["trip_context"]["context"]
    if not (ctx.get("start_date") and ctx.get("days")):
        return []
    first = date.fromisoformat(ctx["start_date"])
    return [first + timedelta(days=i) for i in range(ctx["days"])]


def fetch_live(live_cfg):
    """conditions_fn for the Engine: (decision, by_id) -> (weather, signals); (None, None) without dates. A weather
    source that does not answer leaves weather None (Planning says so); the hand-entered files never fail a trip."""
    def conditions(decision: dict, by_id: dict) -> tuple[dict | None, dict | None]:
        dates = trip_dates(decision)
        if not dates:
            return None, None
        pts = [(r["identity"]["lat"], r["identity"]["lng"]) for c in decision["confirmed"]
               if (r := by_id.get(c["id"])) and r["identity"].get("lat") is not None]
        weather = None
        if pts:
            try:
                weather = live.weather(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts),
                                       [d.isoformat() for d in dates], live_cfg)
            except live.Unavailable:
                weather = None
        hol, evs, adv = live.holidays(dates), live.events(dates), live.advisories(dates)
        signals = {d.isoformat(): {"holiday": hol.get(d), "events": evs.get(d, []), "advisories": adv.get(d, [])}
                   for d in dates}
        return weather, signals
    return conditions
