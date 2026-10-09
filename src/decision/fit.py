"""④ Context fit (docs/PLACE_DECISION.md §7): rough, cheap, before the shortlist; no route service."""

from .geo import km, minutes, point
from .model import Cand, value
from .trip_days import month_of

DAYTIME = ("morning", "noon", "afternoon", "evening")


def centers(si, by_id: dict, cfg) -> list[tuple[str, tuple[float, float]]]:
    """Base (when resolved) or the city center first, then every anchor that has a location."""
    out = []
    base = si.context.base
    if base and base.place_id and (r := by_id.get(base.place_id)) and point(r):
        out.append((r["identity"]["name"], point(r)))
    elif base and base.lat is not None and base.lng is not None:  # a lodging picked from a search: no record
        out.append((base.text, (base.lat, base.lng)))
    if not out:
        out.append((cfg.center["name"], (cfg.center["lat"], cfg.center["lng"])))
    for a in si.anchors:
        r = by_id.get(a.place_id)
        if r and point(r):
            out.append((r["identity"]["name"], point(r)))
    return out


def radius(si, profile, cfg) -> float:
    mob = si.context.mobility or "motorbike"
    r = cfg.radius_km[mob] * profile.travel_mult
    if si.pace.max_leg_min:
        r = min(r, si.pace.max_leg_min * cfg.speed_kmh[mob] / 60 / cfg.road_factor)
    return r


def fit(c: Cand, si, days, ctrs, anchor_areas: set[str], profile, cfg) -> None:
    t = cfg.labels["time"]
    mob = si.context.mobility
    flags = []
    p = point(c.rec)
    dist = 0.0
    if p:
        name, d = min(((n, km(p, q)) for n, q in ctrs), key=lambda x: x[1])
        c.km, c.minutes, c.center = round(d, 1), minutes(d, mob, cfg), name
        dist = 1 - min(1.0, d / radius(si, profile, cfg))
    area = cfg.area_bonus if c.rec["identity"].get("area") in anchor_areas else 0.0
    crowd = 0.0
    cbt = c.rec["operation"].get("crowd_by_time")
    if (profile.crowd_tolerance or si.pace.crowd_tolerance) == "avoid" and cbt:
        known = sorted({d.day_type for d in days if d.day_type})
        busy = [(dt, b) for dt in (known or ["weekday", "weekend"]) for b in DAYTIME
                if (cbt.get(dt) or {}).get(b, 0) >= cfg.crowd_busy_pct]
        if busy:
            dt, b = busy[0]
            flags.append({"code": "crowded", "text": f"Đông {t[b]} {t[dt]} (Google)", "sid": None})
            if known:
                crowd = -cfg.crowd_penalty
    m = month_of(si.context)
    exposed = value(c.rec, "weather_exposed") == "present"
    if m in cfg.rainy_months and (exposed or value(c.rec, "setting") == "outdoor"):
        flags.append({"code": "rain", "text": f"Ngoài trời, tháng {m} hay mưa: cần phương án dự phòng",
                      "sid": "weather_exposed" if exposed else "setting"})
    if value(c.rec, "rough_road_access") == "present":
        flags.append({"code": "rough_road", "sid": "rough_road_access",
                      "text": "Đường vào xấu, xe công nghệ khó vào" if mob == "ride" else "Đường vào xấu, đi xe cẩn thận"})
    c.flags = flags
    c.fit = round(max(0.0, min(1.0, dist + area + crowd)), 4)
