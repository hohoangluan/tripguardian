"""Lodging candidates from Maps' hotel list, through corpus.crawl's public API (RULE.md §2: no deep import).

Maps' date and price filters are UI controls this does not drive yet (needs a live dry run to pin the right
clicks): every card is read as Maps shows it by default, and a price over price_max is dropped here instead.
"""

import asyncio
import math

from corpus.crawl import maps_search, open_sessions

from ..cache import entries as cache_entries
from ..cache import get as cache_get
from ..cache import put as cache_put
from ..http import Unavailable
from ..settings import Settings

QUERY = "khách sạn"
ZOOM = 14  # the hotel list ignores the viewport (corpus.crawl.gmaps.search), so any reasonable zoom works


async def _fetch(center: tuple[float, float], limit: int) -> tuple[list[dict], bool]:
    async with open_sessions() as new_session:
        ctx = await new_session()
        try:
            rows, _end, is_lodging = await maps_search(ctx, QUERY, limit, (*center, ZOOM))
            return rows, is_lodging
        finally:
            await ctx.close()


def lodging_near(center: tuple[float, float], radius_km: float, check_in: str | None, check_out: str | None,
                 price_max: int | None, cfg: Settings) -> list[dict]:
    """[{"id", "name", "lat", "lng", "rating", "reviews", "price_vnd", "amenities", "source", "fetched_at"}].

    radius_km narrows nothing here (planning.lodging.candidates does the real distance cut); it only keeps a
    request for a different area from being wrongly served the cached one.
    """
    payload = {"center": [round(center[0], 4), round(center[1], 4)], "radius_km": radius_km,
              "check_in": check_in, "check_out": check_out}
    hit = cache_get("lodging", payload, cfg.ttl_s["lodging"])
    if hit is None:
        try:
            rows, is_lodging = asyncio.run(_fetch(center, cfg.lodging_query_limit))
            if not is_lodging:
                raise Unavailable("maps did not switch to its hotel list")
        except Exception as e:  # a dead browser, a login wall, a throttled page: none of these invent a value
            nearby = _seen_near(center, radius_km, price_max, cfg)
            if nearby:
                return nearby  # cards an earlier search saw, with their own fetched_at: older, never made up
            raise e if isinstance(e, Unavailable) else Unavailable(str(e)) from e
        hit = cache_put("lodging", payload, [{"id": r["fid"], "name": r["name"], "lat": r["lat"], "lng": r["lng"],
                                              "rating": r["rating"], "reviews": r["reviews"],
                                              "price_vnd": r["price_vnd"], "amenities": r["amenities"]}
                                             for r in rows if r["lat"] is not None], "gmaps")
    return [{**r, "source": hit["source"], "fetched_at": hit["fetched_at"]} for r in hit["value"]
            if price_max is None or r["price_vnd"] is None or r["price_vnd"] <= price_max]


def _seen_near(center: tuple[float, float], radius_km: float, price_max: int | None, cfg: Settings) -> list[dict]:
    """lodging_seen cards inside the radius (and under price_max when their price is known)."""
    def km(r: dict) -> float:
        dy, dx = (r["lat"] - center[0]) * 111.2, (r["lng"] - center[1]) * 111.2 * math.cos(math.radians(center[0]))
        return math.hypot(dy, dx)
    return [r for r in lodging_seen(cfg) if r.get("lat") is not None and r.get("lng") is not None
            and km(r) <= radius_km and (price_max is None or r.get("price_vnd") is None or r["price_vnd"] <= price_max)]


def lodging_seen(cfg: Settings) -> list[dict]:
    """Every lodging card any earlier search cached, newest first, one per id, with its source and fetched_at: what
    a name typed into the lodging box is matched against on the spot, without waiting for the network. Prices here
    may be stale; only name, point, rating are meant to be read."""
    out: dict[str, dict] = {}
    for e in sorted(cache_entries("lodging"), key=lambda e: e.get("fetched_at") or "", reverse=True):
        for r in e["value"] if isinstance(e["value"], list) else []:
            if isinstance(r, dict) and r.get("id") and r["id"] not in out:
                out[r["id"]] = {**r, "source": e.get("source"), "fetched_at": e.get("fetched_at")}
    return list(out.values())
