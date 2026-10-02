"""Nominatim: text -> one point. At most one request a second, which is the service's usage policy.

A text that matches nothing is cached as a miss, so asking twice does not hit the service twice.
"""

import time
import urllib.parse

from ..cache import get as cache_get
from ..cache import put as cache_put
from ..http import Unavailable, get_json
from ..settings import Settings

_last_call = 0.0


def _throttle(min_interval_s: float, clock, sleep) -> None:
    global _last_call
    wait = min_interval_s - (clock() - _last_call)
    if wait > 0:
        sleep(wait)
    _last_call = clock()


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
        _throttle(cfg.nominatim_min_interval_s, clock, sleep)
        query = urllib.parse.urlencode({"q": q, "format": "jsonv2", "limit": 1, "countrycodes": "vn"})
        rows = get_json(f"{cfg.nominatim_url}?{query}", cfg.user_agent, cfg.timeout_s)
        if not isinstance(rows, list):
            raise Unavailable("nominatim: the body is not a list of results")
        hit = cache_put("geocode", payload, rows[0] if rows else None, "nominatim")
    row = hit["value"]
    if row is None:
        return None
    return {"lat": float(row["lat"]), "lng": float(row["lon"]), "label": row.get("display_name") or q,
            "source": hit["source"], "fetched_at": hit["fetched_at"]}
