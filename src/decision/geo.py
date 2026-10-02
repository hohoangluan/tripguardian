"""Rough distances and times: straight line × road factor at a city speed. Never a real route (that is Planning)."""

import math


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def minutes(d_km: float, mobility: str | None, cfg) -> int:
    return max(1, round(d_km * cfg.road_factor / cfg.speed_kmh[mobility or "motorbike"] * 60))


def to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def fmt(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def point(rec: dict) -> tuple[float, float] | None:
    lat, lng = rec["identity"].get("lat"), rec["identity"].get("lng")
    return None if lat is None or lng is None else (float(lat), float(lng))
