"""Coaches between a province and the city from Vexere's route page (config/live.yaml vexere_regions).

The page is server-rendered: its trips sit in __NEXT_DATA__ props.initialState.routeReducer.trips, so one plain GET
is enough (no browser). Only what the page shows is returned; a page that cannot be read raises Unavailable.
"""

import json
import math
import re
import unicodedata
from datetime import date

from ..cache import get as cache_get
from ..cache import put as cache_put
from ..http import Unavailable, get_text
from ..settings import Settings

URL = "https://vexere.com/vi-VN/ve-xe-khach-tu-x-di-y-{a}t{b}1.html?date={d:%d-%m-%Y}"
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
CLOCK = re.compile(r"\d{4}-\d{2}-\d{2}T([01]\d|2[0-3]):[0-5]\d")
# Province names a geosearch row may carry (after the 2025 merger, or spelled out) -> the Vexere region name.
ALIASES = {"ho chi minh": "Sài Gòn", "thanh pho ho chi minh": "Sài Gòn", "tp ho chi minh": "Sài Gòn",
           "tp hcm": "Sài Gòn", "hcm": "Sài Gòn", "sai gon": "Sài Gòn", "hue": "Thừa Thiên Huế",
           "vung tau": "Bà Rịa-Vũng Tàu", "ba ria vung tau": "Bà Rịa-Vũng Tàu", "da lat": "Lâm Đồng"}


def _fold(text: str) -> str:
    t = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").casefold()
    t = re.sub(r"^(tinh|thanh pho|tp\.?)\s+", "", re.sub(r"[-,.]", " ", t).strip())
    return " ".join(t.split())


def region(origin: tuple[float, float] | str, cfg: Settings) -> dict:
    """The Vexere region a trip starting at `origin` takes the coach from: the nearest one to a point, or the one a
    province name names. Unavailable when a name matches none (no coach is guessed)."""
    if not cfg.vexere_regions:
        raise Unavailable("vexere: no regions configured")
    if isinstance(origin, tuple):
        lat, lng = origin
        return min(cfg.vexere_regions,
                   key=lambda r: (r["lat"] - lat) ** 2 + ((r["lng"] - lng) * math.cos(math.radians(lat))) ** 2)
    name = _fold(origin)
    name = _fold(ALIASES.get(name, name))
    for r in cfg.vexere_regions:
        if _fold(r["name"]) == name:
            return r
    raise Unavailable(f"vexere: no coach region named {origin!r}")


def _codes(r: dict, way: str, cfg: Settings) -> tuple[str, str]:
    province, city = f"1{r['id']}", str(cfg.vexere_dalat)  # 2399 = area (2) 399
    return (province, city) if way == "inbound" else (city, province)


def url(origin: tuple[float, float] | str, day: date, way: str, cfg: Settings) -> str:
    """The route page for that day, also the page the user books on when nothing could be read."""
    a, b = _codes(region(origin, cfg), way, cfg)
    return URL.format(a=a, b=b, d=day)


def _point(name: str | None, address: str | None) -> str:
    name, address = (name or "").strip(), (address or "").strip()
    if not address or name in address:
        return address or name
    return f"{name}, {address}" if name else address


def parse(html: str, day: date) -> list[dict]:
    """[{"mode", "carrier", "depart_at", "arrive_at", "from_point", "to_point", "price_vnd"}] leaving on `day`,
    earliest first. Unavailable when the page carries no trip list at all (a changed or blocked page)."""
    m = NEXT_DATA.search(html)
    try:
        trips = json.loads(m.group(1))["props"]["initialState"]["routeReducer"]["trips"]
    except (AttributeError, ValueError, KeyError, TypeError) as e:
        raise Unavailable(f"vexere: no trip list on the page ({e})") from e
    if not isinstance(trips, list):
        raise Unavailable("vexere: the trip list is not a list")
    out, seen = [], set()
    for t in trips:
        try:
            s = t["route"]["schedules"][0]
            depart, arrive = s["pickup_date"][:16], s["arrival_time"][:16]
            carrier = t["busName"].strip()
        except (KeyError, IndexError, TypeError, AttributeError):
            continue
        if not (CLOCK.fullmatch(depart) and CLOCK.fullmatch(arrive)) or depart[:10] != day.isoformat() or not carrier:
            continue
        fare = t.get("fareLarge")
        row = {"mode": "bus", "carrier": carrier, "depart_at": depart, "arrive_at": arrive,
               "from_point": _point(t.get("fromName"), t.get("fromAddress")),
               "to_point": _point(t.get("toName"), t.get("toAddress")),
               "price_vnd": int(fare) if isinstance(fare, (int, float)) and fare > 0 else None}
        if (row["carrier"], row["depart_at"], row["from_point"]) not in seen:
            seen.add((row["carrier"], row["depart_at"], row["from_point"]))
            out.append(row)
    return sorted(out, key=lambda r: r["depart_at"])


def buses(origin: tuple[float, float] | str, day: date, way: str, cfg: Settings, fetch: bool = True,
          max_age_s: int | None = None) -> list[dict] | None:
    """Coaches on `day`: way = inbound (province -> city) | outbound (city -> province). Each carries source and
    fetched_at. fetch=False reads the cache only and returns None on a miss; max_age_s (the daily prewarm) treats an
    entry older than that as a miss. Raises Unavailable on a failed read."""
    if way not in ("inbound", "outbound"):
        raise ValueError(f"way must be inbound or outbound, not {way!r}")
    a, b = _codes(region(origin, cfg), way, cfg)
    payload = {"from": a, "to": b, "date": day.isoformat()}
    hit = cache_get("vexere", payload, min(cfg.ttl_s["transit"], max_age_s or cfg.ttl_s["transit"]))
    if hit is None:
        if not fetch:
            return None
        hit = cache_put("vexere", payload, parse(get_text(URL.format(a=a, b=b, d=day), cfg.user_agent,
                                                          cfg.timeout_s), day), "vexere")
    return [{**r, "source": hit["source"], "fetched_at": hit["fetched_at"]} for r in hit["value"]]
