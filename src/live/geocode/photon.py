"""Photon (OSM data, built for search-as-you-type): text -> up to `limit` places in Việt Nam. Nominatim answers when
Photon does not. Cached under data/live/geocode/ like the single-point geocode."""

import urllib.parse

from ..cache import get as cache_get
from ..cache import put as cache_put
from ..http import Unavailable, get_json
from ..settings import Settings
from .nominatim import search_many

VN_BBOX = "102.1,8.2,109.6,23.4"  # minLon,minLat,maxLon,maxLat


def _row(p: dict, lng: float, lat: float) -> dict:
    name = p.get("name") or " ".join(x for x in (p.get("housenumber"), p.get("street")) if x)
    address = ", ".join(dict.fromkeys(x for x in (" ".join(y for y in (p.get("housenumber"), p.get("street")) if y) if p.get("name") else None,
                                                   p.get("district"), p.get("city")) if x))
    return {"text": name or p.get("city") or p.get("state") or "", "address": address,
            "province": p.get("state") or p.get("city"), "lat": lat, "lng": lng}


def _photon(q: str, limit: int, cfg: Settings) -> list[dict]:
    query = urllib.parse.urlencode({"q": q, "limit": limit, "bbox": VN_BBOX})
    body = get_json(f"{cfg.photon_url}?{query}", cfg.user_agent, cfg.timeout_s)
    if not isinstance(body, dict) or not isinstance(body.get("features"), list):
        raise Unavailable("photon: the body is not a feature collection")
    out = []
    for f in body["features"]:
        try:
            lng, lat = f["geometry"]["coordinates"][:2]
            row = _row(f.get("properties") or {}, float(lng), float(lat))
        except (KeyError, TypeError, ValueError):
            continue
        if row["text"] and (row["text"], row["address"]) not in {(r["text"], r["address"]) for r in out}:
            out.append(row)
    return out


def geosearch(text: str, cfg: Settings, limit: int = 6) -> list[dict]:
    """[{"text", "address", "province", "lat", "lng", "source", "fetched_at"}], best first; [] when nothing matches.
    Raises Unavailable when neither source answers."""
    q = " ".join(text.split())
    if len(q) < 2:
        return []
    payload = {"search": q.casefold(), "limit": limit}
    hit = cache_get("geocode", payload, cfg.ttl_s["geocode"])
    if hit is None:
        try:
            rows, label = _photon(q, limit, cfg), "photon"
        except Unavailable:
            rows, label = search_many(q, limit, cfg), "nominatim"
        hit = cache_put("geocode", payload, rows, label)
    return [{**r, "source": hit["source"], "fetched_at": hit["fetched_at"]} for r in hit["value"]]
