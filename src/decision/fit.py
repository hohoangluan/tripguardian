"""④ Context fit (docs/PLACE_DECISION.md §7): rough, cheap, before the shortlist; no route service."""

from functools import cache

from corpus import load_ontology
from corpus.serving import feature

from .geo import km, minutes, point
from .model import FIRM, Cand, value
from .trip_days import month_of

DAYTIME = ("morning", "noon", "afternoon", "evening")
# what each companion needs from a place beyond the fit verdict: feature, value that helps
NEEDS = {"kids": (("kids_play_area", "present"), ("stroller_access", "yes")),
         "baby": (("kids_play_area", "present"), ("stroller_access", "yes")),
         "parents": (("rest_benches", "present"), ("toilet_available", "yes"))}
FIT_PREFIX = "fit."


@cache
def companions():
    return load_ontology().companions


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
                      "text": "Đường vào xấu, đi xe cẩn thận"})
    details = details_fit(c.rec, trip_companions(si, cfg), cfg, flags)
    c.flags = flags
    c.fit = round(max(0.0, min(1.0, dist + area + crowd + details)), 4)


def trip_companions(si, cfg) -> list[str]:
    """Who the trip is for: its companions, whoever a `fit.<who>` hard filter protects (pregnant, wheelchair), and a
    party big enough to need a coach."""
    who = list(si.context.companions)
    who += [h.feature[len(FIT_PREFIX):] for h in si.hard_filters if h.feature.startswith(FIT_PREFIX)]
    if (si.context.people or 0) >= cfg.coach_min_people:
        who.append("large_group")
    return list(dict.fromkeys(who))


def details_fit(rec: dict, who: list[str], cfg, flags: list) -> float:
    """Score change from the place's details for each companion of the trip (docs/PLACE_DECISION.md): a verified
    verdict (good / bad), the features that companion needs. A bad verdict also flags why. Unverified verdicts and
    missing data change nothing."""
    cf, total = cfg.details_fit, 0.0
    for x in who:
        v = (rec.get("details") or {}).get("fit", {}).get(x)
        label = companions()[x].vi.casefold() if x in companions() else x
        if v and v["status"] in FIRM:
            if v["value"] == "good":
                total += cf["good_bonus"]
            elif v["value"] == "bad":
                total -= cf["bad_penalty"]
                why = "; ".join(v["reasons"][:2])
                flags.append({"code": "fit_bad", "sid": None,
                              "text": f"Không hợp với {label}" + (f": {why}" if why else "")})
            elif v["value"] == "conditional" and v["reasons"]:
                flags.append({"code": "fit_conditional", "sid": None,
                              "text": f"Với {label} có điều kiện: {'; '.join(v['reasons'][:2])}"})
        for fid, want in NEEDS.get(x, ()):
            f = feature(rec, fid)
            if f and f["status"] in FIRM and f["value"] == want:
                total += cf["feature_bonus"]
    return total
