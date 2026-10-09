"""Logistics lookups the user web makes while Trip Understanding asks its logistics questions, before any Planning
session exists (docs/AGENT_HARNESS.md): a place to start from, a lodging by name, the coach / flight of a day.
Planning owns Live Context, so the harness reaches live only through here.

Nothing here writes anything but live's own cache, and nothing is made up: a source that fails gives fewer rows,
or a transit status of "unavailable" with the booking page to open instead.
"""

import re
import threading
import time
import unicodedata
from datetime import date

import live

CITY_SIDE = "Lâm Đồng"  # the city end of a coach route, as trip.domain.logistics.route names it
FAILED_TTL_S = 600      # a crawl that just failed is not retried by every poll; after this it may be tried again
LIMIT = 6


def fold(text: str) -> str:
    t = unicodedata.normalize("NFD", (text or "").replace("đ", "d").replace("Đ", "D"))
    return " ".join("".join(c for c in t if unicodedata.category(c) != "Mn").casefold().split())


def matches(query: str, name: str) -> bool:
    """Every typed word starts a word of the name, accents and case aside ("ana man" -> "Ana Mandara Villas")."""
    words = fold(name).replace("-", " ").split()
    return all(any(w.startswith(q) for w in words) for q in fold(query).replace("-", " ").split())


class Logistics:
    def __init__(self, records: list[dict], live_cfg, geosearch_fn=None, seen_fn=None, buses_fn=None,
                 flights_fn=None, background: bool = True):
        self.stays = [r for r in records if r["identity"].get("category_group") == "stay"
                      and r["identity"].get("lat") is not None and r["identity"].get("lng") is not None]
        self.live_cfg = live_cfg
        self.geosearch_fn = geosearch_fn or (lambda q: live.geosearch(q, live_cfg, LIMIT))
        self.seen_fn = seen_fn or (lambda: live.lodging_seen(live_cfg))
        self.buses_fn = buses_fn or (lambda origin, day, way, fetch: live.buses(origin, day, way, live_cfg, fetch))
        self.flights_fn = flights_fn or (lambda a, b, day, fetch: live.flights(a, b, day, live_cfg, fetch))
        self.background = background
        self._lock = threading.Lock()
        self._running: set[tuple] = set()
        self._failed: dict[tuple, float] = {}

    # ---------- /geo ----------

    def geo(self, q: str) -> list[dict]:
        """Up to six places for a search box; [] when the sources do not answer (the box says nothing was found)."""
        try:
            return self.geosearch_fn(q)[:LIMIT]
        except live.Unavailable:
            return []

    # ---------- /lodging/suggest ----------

    def lodging_suggest(self, q: str) -> list[dict]:
        """Our own lodgings first (served `stay` records, then live cards an earlier search cached), matched by name
        on the spot; then addresses from geosearch. A failing geosearch still returns our own rows."""
        q = " ".join((q or "").split())
        if len(q) < 2:
            return []
        out = [{"kind": "corpus", "id": r["id"], "text": r["identity"]["name"], "address": r["identity"].get("address"),
                "rating": None, "lat": r["identity"]["lat"], "lng": r["identity"]["lng"]}
               for r in self.stays if matches(q, r["identity"].get("name") or "")]
        known = {r["id"] for r in out}
        out += [{"kind": "live", "id": c["id"], "text": c["name"], "address": c.get("address"), "rating": c.get("rating"),
                 "lat": c["lat"], "lng": c["lng"]}
                for c in self.seen_fn() if c["id"] not in known and matches(q, c.get("name") or "")]
        out = out[:LIMIT]
        names = {fold(r["text"]) for r in out}
        for g in self.geo(q):
            if len(out) >= LIMIT:
                break
            if fold(g["text"]) not in names:
                names.add(fold(g["text"]))
                out.append({"kind": "address", "text": g["text"], "address": g.get("address"), "lat": g["lat"],
                            "lng": g["lng"]})
        return out

    # ---------- /transit ----------

    @staticmethod
    def _query(params: dict) -> tuple:
        """(mode, from, to, day, origin, way) from the transit card's params; ValueError on anything malformed."""
        mode, src, dst = params.get("mode"), (params.get("from") or "").strip(), (params.get("to") or "").strip()
        if mode not in ("plane", "bus"):
            raise ValueError("mode must be plane or bus")
        if not src or not dst or len(src) > 80 or len(dst) > 80:
            raise ValueError("from and to are required")
        try:
            day = date.fromisoformat(params.get("date") or "")
        except ValueError:
            raise ValueError("date must be YYYY-MM-DD") from None
        if mode == "plane":
            if not (re.fullmatch(r"[A-Za-z]{3}", src) and re.fullmatch(r"[A-Za-z]{3}", dst)):
                raise ValueError("a flight goes between IATA codes")
            return mode, src.upper(), dst.upper(), day, None, None
        way = "inbound" if fold(dst) == fold(CITY_SIDE) else "outbound"
        province = src if way == "inbound" else dst
        try:  # the origin's own point picks the nearest coach region; the province name is the fallback
            origin = (float(params["lat"]), float(params["lng"]))
        except (KeyError, TypeError, ValueError):
            origin = province
        return mode, src, dst, day, origin, way

    def book_url(self, params: dict) -> str | None:
        mode, src, dst, day, origin, way = self._query(params)
        if mode == "plane":
            return live.flights_url(src, dst, day)
        try:
            return live.buses_url(origin, day, way, self.live_cfg)
        except live.Unavailable:
            return None

    def _read(self, mode, src, dst, day, origin, way, fetch: bool):
        if mode == "plane":
            return self.flights_fn(src, dst, day, fetch)
        return self.buses_fn(origin, day, way, fetch)

    def _crawl(self, key: tuple, q: tuple) -> list | None:
        try:
            return self._read(*q, fetch=True)
        except Exception:  # Unavailable, or a dead browser: the next poll says "unavailable"
            with self._lock:
                self._failed[key] = time.monotonic()
            return None
        finally:
            with self._lock:
                self._running.discard(key)

    def transit(self, params: dict) -> dict:
        """{"status": "ready"|"pending"|"unavailable", "trips", "book_url"}. The cache answers at once; a miss starts
        one crawl in the background (one per route and day, however many polls ask) and says "pending"; a crawl that
        failed says "unavailable" for a while. The booking page is always there to open instead."""
        q = self._query(params)
        key = (q[0], q[1], q[2], q[3].isoformat(), q[4])
        book = self.book_url(params)
        try:
            trips = self._read(*q, fetch=False)
        except live.Unavailable:  # no coach region for that province: nothing to crawl
            return {"status": "unavailable", "trips": [], "book_url": book}
        if trips is not None:
            return {"status": "ready", "trips": trips, "book_url": book}
        with self._lock:
            failed = self._failed.get(key)
            if failed is not None and time.monotonic() - failed < FAILED_TTL_S:
                return {"status": "unavailable", "trips": [], "book_url": book}
            start = key not in self._running
            if start:
                self._failed.pop(key, None)
                self._running.add(key)
        if start and not self.background:
            trips = self._crawl(key, q)
            return {"status": "unavailable" if trips is None else "ready", "trips": trips or [], "book_url": book}
        if start:
            threading.Thread(target=self._crawl, args=(key, q), daemon=True).start()
        return {"status": "pending", "trips": [], "book_url": book}
