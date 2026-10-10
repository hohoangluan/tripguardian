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

from .settings import Settings
from .settings import load as load_settings
from .travel import km

CITY = "dalat"          # config/cities.yaml: whose crawled lodging list (corpus.crawl.listed) names are matched against
CITY_SIDE = "Lâm Đồng"  # the city end of a coach route, as trip.domain.logistics.route names it
FAILED_TTL_S = 600      # a crawl that just failed is not retried by every poll; after this it may be tried again
LIMIT = 6
# Words that say what kind of lodging, or where relative to something, not which one: "homestay gần chợ Đà Lạt" is
# looked up as "chợ Đà Lạt", "Dalat Palace Heritage Hotel" as "dalat palace heritage". Phrases go before words.
GENERIC_PHRASES = ("cho o", "khach san", "nha nghi", "nha khach", "can ho", "guest house", "biet thu", "khu nghi duong")
GENERIC_WORDS = {"hotel", "homestay", "home", "stay", "resort", "villa", "villas", "hostel", "motel", "guesthouse",
                 "apartment", "apartments", "boutique", "gan", "near", "o", "tai", "quanh", "canh", "khu", "the", "and"}
CITY_WORDS = {"dalat"}  # matched like any word, but a match on it alone names nothing


def fold(text: str) -> str:
    t = unicodedata.normalize("NFD", (text or "").replace("đ", "d").replace("Đ", "D"))
    return " ".join("".join(c for c in t if unicodedata.category(c) != "Mn").casefold().split())


def matches(query: str, name: str) -> bool:
    """Every typed word starts a word of the name, accents and case aside ("ana man" -> "Ana Mandara Villas")."""
    words = fold(name).replace("-", " ").split()
    return all(any(w.startswith(q) for w in words) for q in fold(query).replace("-", " ").split())


def words(text: str) -> list[str]:
    """The words that tell one place from another: folded, "đà lạt" as one word, kind-of-lodging words dropped."""
    t = " " + " ".join(re.sub(r"[^a-z0-9]+", " ", fold(text)).split()) + " "
    t = t.replace(" da lat ", " dalat ")
    for ph in GENERIC_PHRASES:
        t = t.replace(f" {ph} ", " ")
    return [w for w in t.split() if w not in GENERIC_WORDS]


def name_score(query: str, name: str, prefix: bool = False) -> float:
    """How well a typed text names this place, 0 when it does not: at least half of the typed words are words of the
    name (the last one may be half typed when `prefix`), and one of them is more than the city's name. Higher when the
    name has few other words ("Dalat Palace" beats "Dalat Palace Golf Club" for "dalat palace hotel")."""
    q, n = words(query), words(name)
    if not q or not n:
        return 0.0
    hit = [w for k, w in enumerate(q)
           if any(x == w or (prefix and k == len(q) - 1 and x.startswith(w)) for x in n)]
    if len(hit) * 2 < len(q) or not set(hit) - CITY_WORDS:
        return 0.0
    used = sum(any(x == w or x.startswith(w) for w in hit) for x in n)
    return len(hit) / len(q) + 0.5 * used / len(n)


def _crawled_stays(city: str) -> list[dict]:
    """The city's lodging list the Maps crawl wrote (corpus.crawl.listed_stays; read only): lodging the user may name
    that the served corpus does not hold yet. [] before the crawl has run."""
    from corpus.crawl import listed_stays
    return [{"id": r["fid"], "name": r["name"], "lat": r["lat"], "lng": r["lng"], "rating": r.get("rating"),
             "reviews": r.get("reviews"), "address": r.get("address")}
            for r in listed_stays(city) if r.get("lat") is not None and r.get("lng") is not None
            and r.get("fid") and r.get("name")]


class Logistics:
    def __init__(self, records: list[dict], live_cfg, geosearch_fn=None, seen_fn=None, buses_fn=None,
                 flights_fn=None, background: bool = True, listed_fn=None, cfg: Settings | None = None):
        self.cfg = cfg or load_settings()
        located = [r for r in records if r["identity"].get("lat") is not None and r["identity"].get("lng") is not None]
        self.stays = [r for r in located if r["identity"].get("category_group") == "stay"]
        self.places = [r for r in located if r["identity"].get("category_group") != "stay"]
        self.listed_fn = listed_fn or (lambda: _crawled_stays(CITY))
        self._listed: list[dict] | None = None
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

    def crawled(self) -> list[dict]:
        if self._listed is None:
            try:
                self._listed = self.listed_fn()
            except Exception:   # a missing or half-written list file: our other rows still answer
                self._listed = []
        return self._listed

    def _own(self, q: str, prefix: bool) -> list[dict]:
        """Our own lodgings that the text names, best first inside each source: served `stay` records, the crawled
        lodging list, then live cards an earlier search cached. One row per id."""
        out, known = [], set()

        def take(kind: str, rows: list[dict]) -> None:
            scored = sorted(((name_score(q, r["text"], prefix), r) for r in rows if r["id"] not in known),
                            key=lambda x: (-x[0], -(x[1].get("reviews") or 0)))
            for s, r in scored:
                if s > 0:
                    known.add(r["id"])
                    out.append({"kind": kind, **{k: v for k, v in r.items() if k != "reviews"}})

        take("corpus", [{"id": r["id"], "text": r["identity"]["name"], "address": r["identity"].get("address"),
                         "rating": None, "lat": r["identity"]["lat"], "lng": r["identity"]["lng"]} for r in self.stays])
        take("live", [{"id": c["id"], "text": c["name"], "address": c.get("address"), "rating": c.get("rating"),
                       "reviews": c.get("reviews"), "lat": c["lat"], "lng": c["lng"]} for c in self.crawled()])
        take("live", [{"id": c["id"], "text": c["name"], "address": c.get("address"), "rating": c.get("rating"),
                       "lat": c["lat"], "lng": c["lng"]} for c in self.seen_fn()])
        return out

    def lodging_suggest(self, q: str) -> list[dict]:
        """Our own lodgings first (served `stay` records, the crawled lodging list, live cards an earlier search
        cached), matched by name on the spot; then addresses from geosearch. A failing geosearch still returns our
        own rows."""
        q = " ".join((q or "").split())
        if len(q) < 2:
            return []
        out = self._own(q, prefix=True)[:LIMIT]
        names = {fold(r["text"]) for r in out}
        for g in self.geo(q):
            if len(out) >= LIMIT:
                break
            if fold(g["text"]) not in names:
                names.add(fold(g["text"]))
                out.append({"kind": "address", "text": g["text"], "address": g.get("address"), "lat": g["lat"],
                            "lng": g["lng"], **({"geo_kind": g["kind"]} if g.get("kind") else {}),
                            **({"approx": True} if g.get("approx") else {})})
        return out

    def resolve(self, text: str) -> dict | None:
        """Where a lodging typed in full (not picked from the list) is, from our own data and without the network:
        {"lat", "lng", "label", "source", "fetched_at"} or None. A lodging the text names first; else a served place
        it names ("homestay gần chợ Đà Lạt" -> Chợ Đà Lạt). The caller falls back to geocoding."""
        own = self._own(text, prefix=False)
        if own:
            return {"lat": own[0]["lat"], "lng": own[0]["lng"], "label": own[0]["text"], "source": "lodging_list",
                    "fetched_at": None}
        near = max(((name_score(text, r["identity"].get("name") or ""), r) for r in self.places),
                   key=lambda x: x[0], default=(0.0, None))
        if near[0] > 0:
            ident = near[1]["identity"]
            return {"lat": ident["lat"], "lng": ident["lng"], "label": ident["name"], "source": "corpus",
                    "fetched_at": None}
        return None

    # ---------- /rentals ----------

    def rentals(self, params: dict) -> dict:
        """Motorbike rental points of the served corpus (category_group rental), nearest first to where the trip arrives:
        {"status": "ready" | "none", "hub": {text, lat, lng}, "points": [{id, name, address, lat, lng, km, near_hub,
        hours_known, maps_url}]}. params: mode bus | plane picks the station / airport; lat + lng measure from a point the
        user picked instead. Only shops the corpus holds are listed; none -> "none", never a made-up shop. A shop beyond
        `near_km` of the hub is listed with its distance (near_hub false): the airport is ~30 km from the city."""
        cfg = self.cfg.rental
        mode = params.get("mode")
        if mode not in cfg["hubs"]:
            raise ValueError("mode must be bus or plane")
        hub = dict(cfg["hubs"][mode])
        if params.get("lat") or params.get("lng"):
            try:
                hub = {"text": (params.get("text") or hub["text"])[:80], "lat": float(params["lat"]), "lng": float(params["lng"])}
            except (KeyError, TypeError, ValueError):
                raise ValueError("lat and lng must be numbers") from None
        here = (hub["lat"], hub["lng"])
        shops = sorted(((km(here, (r["identity"]["lat"], r["identity"]["lng"])), r) for r in self.places
                        if r["identity"].get("category_group") == "rental"), key=lambda x: (x[0], x[1]["id"]))
        points = [{"id": r["id"], "name": r["identity"]["name"], "address": r["identity"].get("address"),
                   "lat": r["identity"]["lat"], "lng": r["identity"]["lng"], "km": round(d, 1),
                   "near_hub": d <= cfg["near_km"], "hours_known": bool((r["operation"].get("hours") or {}).get("value")),
                   "maps_url": f"https://www.google.com/maps/search/?api=1&query={r['identity']['lat']},{r['identity']['lng']}"}
                  for d, r in shops[:cfg["limit"]]]
        return {"status": "ready" if points else "none", "hub": hub, "points": points}

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
