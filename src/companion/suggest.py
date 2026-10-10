"""What to show after "Đã đến", from serving records only (docs/P5_COMPANION.md §Gợi ý). Pure functions: no I/O.

Every place is a serving record id; every feature is a record value with its status. Nothing missing is filled in:
a place with no hours is "chưa xác nhận", a crowd level without Google's table is not shown.
"""

import math
import unicodedata
from datetime import datetime

from corpus.serving import feature
from decision import hard_check, preference_fit
from live import sun_times

FIRM = ("VERIFIED", "OUTDATED")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
BUCKETS = (("morning", 6, 11), ("noon", 11, 14), ("afternoon", 14, 18), ("evening", 18, 24))


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def point(rec: dict) -> tuple[float, float] | None:
    ident = rec.get("identity") or {}
    return (ident["lat"], ident["lng"]) if ident.get("lat") is not None and ident.get("lng") is not None else None


def travel_min(a, b, mobility: str | None, cfg: dict) -> int:
    speed = cfg["rough_speed_kmh"].get(mobility or "motorbike", 25)
    return max(1, round(km(a, b) * cfg["road_factor"] / speed * 60))


def _clock(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def open_at(rec: dict, when: datetime) -> bool | None:
    """True / False from VERIFIED or OUTDATED hours; None when the hours are unknown or unsure."""
    hours = (rec.get("operation") or {}).get("hours")
    if not hours or hours.get("status") not in FIRM or not hours.get("value"):
        return None
    spans = hours["value"].get(DAYS[when.weekday()]) or []
    t = when.hour * 60 + when.minute
    return any(_clock(a) <= t < (_clock(b) if _clock(b) > _clock(a) else 24 * 60) for a, b in spans)


def play(rec: dict, soft: list[dict], count: int) -> list[dict]:
    """Experience values the sources agree on, the ones this trip asked for first."""
    wanted = {(w["feature"], w["value"]) for w in soft if w.get("weight", 0) > 0}
    out = []
    for fid, f in (rec.get("experience") or {}).items():
        if f.get("status") in FIRM and f.get("value") and f.get("evidence"):
            out.append({"feature": fid, "value": f["value"], "status": f["status"], "n": f.get("n", 0),
                        "wanted": (fid, f["value"]) in wanted})
    out.sort(key=lambda x: (not x["wanted"], -x["n"]))
    return out[:count]


def practical(rec: dict, ids: list[str]) -> list[dict]:
    out = []
    for fid in ids:
        f = feature(rec, fid)
        if f and f.get("value") and f.get("status") in (*FIRM, "UNCERTAIN"):
            out.append({"feature": fid, "value": f["value"], "status": f["status"]})
    return out


def timely(rec: dict, when: datetime, sun_features: list[str]) -> dict:
    out: dict = {}
    p = point(rec)
    if p and any((feature(rec, fid) or {}).get("status") in FIRM and (feature(rec, fid) or {}).get("value") == "present"
                 for fid in sun_features):
        times = sun_times(when.date(), *p)
        if times:
            out["sunrise"], out["sunset"] = (f"{m // 60:02d}:{m % 60:02d}" for m in times)
            out["date"] = when.date().isoformat()
    table = (rec.get("operation") or {}).get("crowd_by_time")
    if table:  # Google's popular times: a measured table, shown as it is
        day_type = "weekend" if when.weekday() >= 5 else "weekday"
        bucket = next((b for b, lo, hi in BUCKETS if lo <= when.hour < hi), None)
        pct = (table.get(day_type) or {}).get(bucket) if bucket else None
        if pct is not None:
            out["crowd"] = {"pct": pct, "bucket": bucket, "day_type": day_type, "source": "google"}
    return out


def _core(name: str | None) -> str:
    """A name without case, accents or punctuation, to tell two records of one site apart from neighbours."""
    s = unicodedata.normalize("NFD", (name or "").lower().replace("đ", "d"))
    s = "".join(c if c.isalnum() else " " for c in s if not unicodedata.combining(c))
    return " ".join(s.split())


def same_site(a: dict, b: dict) -> bool:
    """One name holds the other (e.g. "Viewpoint Săn mây Đồi Đa Phú" on "Đồi Đa Phú"): another spot of the place the
    user is standing on, not somewhere else to go. Single-word names are too common to judge."""
    x, y = sorted((_core((a.get("identity") or {}).get("name")), _core((b.get("identity") or {}).get("name"))), key=len)
    return len(x.split()) >= 2 and f" {x} " in f" {y} "


def _in(window: list[str] | None, when: datetime) -> bool:
    t = when.hour * 60 + when.minute
    return bool(window) and _clock(window[0]) <= t < _clock(window[1])


def nearby(here: dict, records: dict[str, dict], *, when: datetime, budget_min: int | None, mobility: str | None,
           soft: list[dict], hard: list[dict], skip: set[str], cfg: dict, same_group: bool = False) -> list[dict]:
    """Places a short ride away that are open (or not known to be closed), pass the trip's hard filters (fail-closed:
    unknown is left out unless the filter only flags), fit before the next stop, and are not in the plan, disliked,
    or another spot of the place itself. Ranked by Decision's soft-preference fit counting only the wishes that suit
    this hour (feature_hours: no cloud hunting at noon), then distance. Outside the similar list: during a meal
    window places to eat come first, and at most max_per_group of one kind are shown while other kinds remain."""
    origin = point(here)
    if origin is None:
        return []
    group = (here.get("identity") or {}).get("category_group")
    hours = cfg.get("feature_hours") or {}
    soft = [w for w in soft if w["feature"] not in hours or _in(hours[w["feature"]], when)]
    meal = not same_group and any(_in(w, when) for w in (cfg.get("meal_windows") or {}).values())
    out = []
    for pid, rec in records.items():
        if pid in skip or pid == here["id"] or same_site(here, rec):
            continue
        if same_group and (rec.get("identity") or {}).get("category_group") != group:
            continue
        p = point(rec)
        if p is None:
            continue
        minutes = travel_min(origin, p, mobility, cfg)
        if minutes > cfg["nearby_max_min"]:
            continue
        visit = (((rec.get("operation") or {}).get("visit_minutes") or {}).get("short")) or 30
        if budget_min is not None and 2 * minutes + visit > budget_min:
            continue
        is_open = open_at(rec, when)
        if is_open is False:
            continue
        checks = [(h, hard_check(rec, h)) for h in hard]
        if any(r == "fail" or (r == "unknown" and h.get("unknown_policy", "exclude") == "exclude") for h, r in checks):
            continue
        fit, matches = preference_fit(rec, soft)
        out.append({"place_id": pid, "name": (rec.get("identity") or {}).get("name"), "travel_min": minutes,
                    "estimate": True, "open": is_open, "fit": round(fit, 3), "matches": [m[0] for m in matches],
                    "flags": [h["feature"] for h, r in checks if r == "unknown"],
                    "meal": "meal" in (rec.get("usable_as") or []),
                    "group": (rec.get("identity") or {}).get("category_group")})
    out.sort(key=lambda x: (meal and not x["meal"], -x["fit"], x["travel_min"]))
    if same_group:
        return out[:cfg["nearby_count"]]
    picked, rest, per = [], [], {}
    for x in out:  # diverse kinds first, the rest only to fill the list
        if per.get(x["group"], 0) < cfg.get("max_per_group", 2):
            per[x["group"]] = per.get(x["group"], 0) + 1
            picked.append(x)
        else:
            rest.append(x)
    return (picked + rest)[:cfg["nearby_count"]]
