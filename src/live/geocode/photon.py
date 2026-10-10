"""Photon (OSM data, built for search-as-you-type): text -> up to `limit` places in Việt Nam. Nominatim answers when
Photon does not. Cached under data/live/geocode/ like the single-point geocode."""

import urllib.parse

from ..cache import get as cache_get
from ..cache import put as cache_put
from ..http import Unavailable, get_json
from ..settings import Settings
from .nominatim import search_many

VN_BBOX = "102.1,8.2,109.6,23.4"  # minLon,minLat,maxLon,maxLat: also covers south China, Laos, Cambodia, Thailand
OVERFETCH = 3  # rows asked per row kept: the box's rows outside Việt Nam are dropped


# Photon also indexes what nobody types a trip's start or a lodging as: highway segments, building sites, plots, rail lines.
NOT_PLACES = {"motorway", "motorway_link", "construction", "proposed", "plot", "subway", "rail", "light_rail", "tram",
              "track", "path", "footway", "cycleway", "steps", "bus_guideway", "abandoned", "disused"}
STAYS = {"hotel", "hostel", "guest_house", "motel", "apartment", "resort", "chalet", "homestay"}
STATIONS = {"aerodrome", "station", "bus_station", "halt", "terminal", "ferry_terminal"}


def _kind(p: dict) -> str:
    key, value = p.get("osm_key"), p.get("osm_value")
    if value in STAYS:
        return "stay"
    if key in ("aeroway", "railway", "public_transport") or value in STATIONS:
        return "transport"
    if key == "highway":
        return "street"
    if key in ("place", "boundary"):
        return "area"
    return "place"


def _row(p: dict, lng: float, lat: float) -> dict:
    name = p.get("name") or " ".join(x for x in (p.get("housenumber"), p.get("street")) if x)
    address = ", ".join(dict.fromkeys(x for x in (" ".join(y for y in (p.get("housenumber"), p.get("street")) if y) if p.get("name") else None,
                                                   p.get("district"), p.get("city")) if x))
    return {"text": name or p.get("city") or p.get("state") or "", "address": address,
            "province": p.get("state") or p.get("city"), "lat": lat, "lng": lng, "kind": _kind(p)}


def _photon(q: str, limit: int, cfg: Settings) -> list[dict]:
    query = urllib.parse.urlencode({"q": q, "limit": limit * OVERFETCH, "bbox": VN_BBOX})
    body = get_json(f"{cfg.photon_url}?{query}", cfg.user_agent, cfg.suggest_timeout_s)
    if not isinstance(body, dict) or not isinstance(body.get("features"), list):
        raise Unavailable("photon: the body is not a feature collection")
    out = []
    for f in body["features"]:
        props = f.get("properties") or {}
        if props.get("countrycode") != "VN":  # Nam Ninh, Hải Nam, Thái Lan share the box
            continue
        if props.get("osm_value") in NOT_PLACES or props.get("osm_key") == "landuse":
            continue
        try:
            lng, lat = f["geometry"]["coordinates"][:2]
            row = _row(f.get("properties") or {}, float(lng), float(lat))
        except (KeyError, TypeError, ValueError):
            continue
        if row["text"] and (row["text"], row["address"]) not in {(r["text"], r["address"]) for r in out}:
            out.append(row)
    return out[:limit]


def geosearch(text: str, cfg: Settings, limit: int = 6) -> list[dict]:
    """[{"text", "address", "province", "lat", "lng", "source", "fetched_at"}], best first; [] when nothing matches.
    Raises Unavailable when neither source answers."""
    q = " ".join(text.split())
    if len(q) < 2:
        return []
    payload = {"search": q.casefold(), "limit": limit, "country": "vn"}  # "country": entries cached before the filter are not read
    hit = cache_get("geocode", payload, cfg.ttl_s["geocode"])
    if hit is None:
        try:
            rows, label = _photon(q, limit, cfg), "photon"
        except Unavailable:
            rows, label = search_many(q, limit, cfg), "nominatim"
        hit = cache_put("geocode", payload, rows, label)
    return [{**r, "source": hit["source"], "fetched_at": hit["fetched_at"]} for r in hit["value"]]
