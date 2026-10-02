"""Lodging candidates from Maps' hotel list, through corpus.crawl's public API (RULE.md §2: no deep import).

Maps' date and price filters are UI controls this does not drive yet (needs a live dry run to pin the right
clicks): every card is read as Maps shows it by default, and a price over price_max is dropped here instead.
"""

import asyncio

from corpus.crawl import maps_search, open_sessions

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
        except Exception as e:  # a dead browser, a login wall, a throttled page: none of these invent a value
            raise Unavailable(str(e)) from e
        if not is_lodging:
            raise Unavailable("maps did not switch to its hotel list")
        hit = cache_put("lodging", payload, [{"id": r["fid"], "name": r["name"], "lat": r["lat"], "lng": r["lng"],
                                              "rating": r["rating"], "reviews": r["reviews"],
                                              "price_vnd": r["price_vnd"], "amenities": r["amenities"]}
                                             for r in rows if r["lat"] is not None], "gmaps")
    return [{**r, "source": hit["source"], "fetched_at": hit["fetched_at"]} for r in hit["value"]
            if price_max is None or r["price_vnd"] is None or r["price_vnd"] <= price_max]
