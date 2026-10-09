"""Nominatim: text -> one point. At most one request a second, which is the service's usage policy.

A text that matches nothing is cached as a miss, so asking twice does not hit the service twice.
The city is appended first; when that finds nothing (the airport is in Hiệp Thạnh, not Đà Lạt) the bare text is
retried inside a box around Đà Lạt, Lạc Dương, Đơn Dương and Đức Trọng, so it cannot land elsewhere in Vietnam.
"""

import time
import urllib.parse

from ..cache import get as cache_get
from ..cache import put as cache_put
from ..http import Unavailable, get_json
from ..settings import Settings

_last_call = 0.0
_AREA_BOX = "107.9,12.3,108.8,11.6"  # viewbox x1,y1,x2,y2 = lng,lat of two opposite corners


def _throttle(min_interval_s: float, clock, sleep) -> None:
    global _last_call
    wait = min_interval_s - (clock() - _last_call)
    if wait > 0:
        sleep(wait)
    _last_call = clock()


def _search(q: str, extra: dict, cfg: Settings, clock, sleep) -> list:
    _throttle(cfg.nominatim_min_interval_s, clock, sleep)
    query = urllib.parse.urlencode({"q": q, "format": "jsonv2", "limit": 1, "countrycodes": "vn", **extra})
    rows = get_json(f"{cfg.nominatim_url}?{query}", cfg.user_agent, cfg.timeout_s)
    if not isinstance(rows, list):
        raise Unavailable("nominatim: the body is not a list of results")
    return rows


def search_many(q: str, limit: int, cfg: Settings, clock=time.monotonic, sleep=time.sleep) -> list[dict]:
    """Up to `limit` rows in Việt Nam in geosearch's shape (photon.py falls back to this)."""
    _throttle(cfg.nominatim_min_interval_s, clock, sleep)
    query = urllib.parse.urlencode({"q": q, "format": "jsonv2", "limit": limit, "countrycodes": "vn", "addressdetails": 1})
    rows = get_json(f"{cfg.nominatim_url}?{query}", cfg.user_agent, cfg.timeout_s)
    if not isinstance(rows, list):
        raise Unavailable("nominatim: the body is not a list of results")
    out = []
    for r in rows:
        a = r.get("address") or {}
        out.append({"text": r.get("name") or r.get("display_name", "").split(",")[0], "address": r.get("display_name", ""),
                    "province": a.get("state") or a.get("city"), "lat": float(r["lat"]), "lng": float(r["lon"])})
    return out


def geocode(text: str, cfg: Settings, city: str = "Đà Lạt, Việt Nam", clock=time.monotonic,
            sleep=time.sleep) -> dict | None:
    """{"lat", "lng", "label", "source", "fetched_at"}, or None when nothing matches. Never guesses a point."""
    q = text.strip()
    if not q:
        raise ValueError("geocode needs text")
    if city.split(",")[0].casefold() not in q.casefold():
        q = f"{q}, {city}"
    payload = {"q": q}
    hit = cache_get("geocode", payload, cfg.ttl_s["geocode"])
    if hit is None:
        rows = _search(q, {}, cfg, clock, sleep)
        if not rows:
            rows = _search(text.strip(), {"viewbox": _AREA_BOX, "bounded": 1}, cfg, clock, sleep)
        hit = cache_put("geocode", payload, rows[0] if rows else None, "nominatim")
    row = hit["value"]
    if row is None:
        return None
    return {"lat": float(row["lat"]), "lng": float(row["lon"]), "label": row.get("display_name") or q,
            "source": hit["source"], "fetched_at": hit["fetched_at"]}
