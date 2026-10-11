"""Lodging candidates for the trip (docs/PLANNING.md ⓐ): search area, sieve, rank by taste first, location after.

Where they come from depends on the data at hand: the served `stay` records (observed reviews, so taste can be
compared) once at least stay_min of them sit in the search area; otherwise Maps' hotel list crawled live (no
observed reviews: taste is unknown, the rank falls to location, price, rating). Live candidates never become Place
Intelligence: they live only in this call's result, each carrying source and fetched_at. A hard filter with no
evidence keeps the candidate (unknown, not rejected); it never drops one it cannot check.
"""

from datetime import date, timedelta

from corpus.serving import check, feature
from live import Unavailable

from .places import Place
from .settings import Settings
from .travel import km

# who travels along -> the suitability a lodging should have (config/ontology.yaml stay_features)
COMPANION_FEATURE = {"kids": "kids", "parents": "elderly", "partner": "couples"}


def booked(decision: dict) -> dict | None:
    """The lodging the user already booked, as a lodging point ({"id", "lat", "lng", "text", "source", "fetched_at"}),
    when Trip Understanding has it with a point; then Planning anchors every day there and suggests no lodging. Its
    id is the trip's own home node: Planning treats a booked lodging as the trip's base."""
    tc = decision["trip_context"]["context"]
    lod = tc.get("lodging") or {}
    if tc.get("lodging_booked") != "yes" or lod.get("lat") is None or lod.get("lng") is None:
        return None
    return {"id": "@home", "lat": float(lod["lat"]), "lng": float(lod["lng"]), "text": lod.get("text") or "",
            "source": "user", "fetched_at": None}


def with_booked_base(decision: dict) -> dict:
    """The Decision Output with its base set to the booked lodging (a no-op without one)."""
    if not booked(decision):
        return decision
    tc = decision["trip_context"]
    return {**decision, "trip_context": {**tc, "context": {**tc["context"], "base": tc["context"]["lodging"]}}}


def search_area(by_place: dict[str, Place], mobility: str | None, cfg: Settings) -> list[dict]:
    """One centre weighted by typical visit length, or two when the places span wider than split_min of real
    travel (approximated here by straight-line distance at a city driving speed; the real matrix comes later)."""
    places = list(by_place.values())
    if not places:
        return []
    radius = cfg.radius_km.get(mobility or "motorbike", 3.0)

    def centroid(ps: list) -> dict:
        w = [p.visit.get("typical") or 1 for p in ps]
        return {"lat": sum(p.lat * x for p, x in zip(ps, w)) / sum(w),
               "lng": sum(p.lng * x for p, x in zip(ps, w)) / sum(w), "radius_km": radius}

    if len(places) < 2:
        return [centroid(places)]
    pairs = [(a, b) for a in places for b in places]
    a, b = max(pairs, key=lambda ab: km((ab[0].lat, ab[0].lng), (ab[1].lat, ab[1].lng)))
    if km((a.lat, a.lng), (b.lat, b.lng)) * 60 / 25 <= cfg.split_min:
        return [centroid(places)]
    near_a = [p for p in places if km((p.lat, p.lng), (a.lat, a.lng)) <= km((p.lat, p.lng), (b.lat, b.lng))]
    near_b = [p for p in places if p.id not in {x.id for x in near_a}]
    return [centroid(g) for g in (near_a, near_b) if g]


def price_cap(ctx: dict, nights: int, cfg: Settings) -> int | None:
    """lodging_share of the whole trip's budget, spread over the nights; unknown when the budget is unknown."""
    budget = ctx.get("budget_vnd")
    if budget is None or nights <= 0:
        return None
    return round(budget * cfg.lodging_share / nights)


def _evidence(cand: dict, fid: str, value: str) -> str:
    """fail | pass | unknown for "fid != value": a served record answers from its observed reviews, a live card
    only from the amenities Maps lists (an amenity it does not list is unknown, not absent)."""
    if cand.get("rec"):
        return check(cand["rec"], fid, value)
    return "fail" if value == "present" and fid in (cand.get("amenities") or []) else "unknown"


def sieve(raw: list[dict], hard_filters: list[dict], min_reviews: int) -> list[dict]:
    """A hard filter only rejects a candidate that has the evidence against it, never one with no evidence either
    way (that one is kept, its feature listed in `unverified`)."""
    out = []
    for c in raw:
        if (c.get("reviews") or 0) < min_reviews:
            continue
        results = {f["feature"]: _evidence(c, f["feature"], f["value"]) for f in hard_filters if f["op"] == "ne"}
        if "fail" in results.values():
            continue
        out.append({**c, "unverified": [f for f, r in results.items() if r == "unknown"]})
    return out


def shortlist(cands: list[dict], centres: list[dict], k: int) -> list[dict]:
    """The k candidates closest (straight line) to whichever search centre is nearest them."""
    def dist(c: dict) -> float:
        return min(km((c["lat"], c["lng"]), (ct["lat"], ct["lng"])) for ct in centres)

    return sorted(cands, key=dist)[:k]


def _in_area(c: dict, centres: list[dict]) -> bool:
    # a generous multiple of radius_km, not radius_km itself: search_area may not split into two centres even when a
    # far cluster's places sit a bit past one centre's radius (split_min is about travel time, not raw distance) --
    # this only needs to catch Maps padding a short list with another city entirely.
    return any(km((c["lat"], c["lng"]), (ct["lat"], ct["lng"])) <= 2 * ct["radius_km"] for ct in centres)


def from_record(r: dict) -> dict:
    """A served `stay` record as a candidate: its price is the reference the reviews give, not a date's price."""
    p = r["operation"].get("price_per_person")
    prov = r.get("provenance") or {}
    trend = prov.get("rating_trend") or {}
    return {"id": r["id"], "name": r["identity"]["name"], "lat": r["identity"]["lat"], "lng": r["identity"]["lng"],
            "address": r["identity"].get("address"), "rating": trend.get("recent_mean"),
            "reviews": prov.get("voices") or 0, "price_vnd": (p["value"] or {}).get("min_vnd") if p else None,
            "amenities": [], "source": "corpus", "fetched_at": prov.get("as_of"), "rec": r}


def stays_in(records: list[dict], centres: list[dict]) -> list[dict]:
    return [r for r in records if r["identity"].get("category_group") == "stay" and r["identity"].get("lat") is not None
            and r["identity"].get("lng") is not None and _in_area({"lat": r["identity"]["lat"], "lng": r["identity"]["lng"]}, centres)]


def _dates(tc: dict) -> tuple[str | None, str | None]:
    start = tc.get("start_date")
    check_out = ((date.fromisoformat(start) + timedelta(days=(tc.get("days") or 1) - 1)).isoformat()
                if start and tc.get("days") else None)
    return start, check_out


def live_cards(centres: list[dict], tc: dict, cap: int | None, lodging_fn, live_cfg) -> list[dict]:
    """Maps' hotel list around every centre, one card per id, inside the area; a centre whose source is down adds
    nothing."""
    start, check_out = _dates(tc)
    raw, seen = [], set()
    for ct in centres:
        try:
            found = lodging_fn((ct["lat"], ct["lng"]), ct["radius_km"], start, check_out, cap, live_cfg)
        except Unavailable:
            continue
        for c in found:
            if c["id"] not in seen and _in_area(c, centres):
                seen.add(c["id"])
                raw.append({**c, "source": "live", "price_source": c.get("source"), "price_at": c.get("fetched_at")})
    return raw


def pref_fit(c: dict, trip_context: dict, labels: dict | None = None) -> tuple[float, list[dict]]:
    """(fit, why): the trip's soft wishes (love +1, avoid -1) and who travels along (`<who>=suitable`, +1) that the
    lodging's observed reviews confirm (VERIFIED), over the number of wishes. A feature with no evidence adds 0, never
    a penalty (docs/PLACE_DECISION.md §8). `why` lists the loved ones it has, each with how many reviews said so."""
    wishes = [(w["feature"], w["value"], 1 if w["weight"] > 0 else -1)
              for w in trip_context.get("soft_weights") or [] if w.get("weight")]
    wishes += [(f, "suitable", 1) for who, f in COMPANION_FEATURE.items()
               if who in (trip_context["context"].get("companions") or [])]
    if not wishes or not c.get("rec"):
        return 0.0, []
    total, why = 0, []
    for fid, value, sign in wishes:
        f = feature(c["rec"], fid)
        if f and f["status"] == "VERIFIED" and f["value"] == value:
            total += sign
            if sign > 0:
                why.append({"text": phrase(fid, value, labels or {}), "mentions": f.get("n"), "quote": None, "feature": fid})
    return total / len(wishes), why


def phrase(fid: str, value: str, labels: dict) -> str:
    """The words Place Decision's cards use (config/decision.yaml labels)."""
    name = (labels.get("feature") or {}).get(fid, fid.replace("_", " "))
    return name if value in ("present", "suitable") else f"{name}: {(labels.get('value') or {}).get(value, value)}"


def candidates(by_place: dict[str, Place], decision: dict, cfg: Settings, lodging_fn, live_cfg,
               records: list[dict] = ()) -> list[dict]:
    """The pool to rank: served stays when the area has at least stay_min of them (the lodging_pool that fit the
    trip's taste best, nearest first on a tie, so the travel matrix stays small), else the live hotel list's
    lodging_k nearest. [] on no places to anchor a search on, or when every centre's source was unavailable — never a
    reason to fail the whole plan: the "no lodging" option always stays alongside whatever this returns (ⓐ.5)."""
    tc = decision["trip_context"]["context"]
    centres = search_area(by_place, tc.get("mobility"), cfg)
    if not centres:
        return []
    nights = max((tc.get("days") or 1) - 1, 0)
    cap = price_cap(tc, nights, cfg)
    hard_filters = decision["trip_context"].get("hard_filters") or []
    stays = stays_in(list(records), centres)
    if len(stays) >= cfg.stay_min:
        pool = [c for c in sieve([from_record(r) for r in stays], hard_filters, cfg.min_reviews)
                if cap is None or c["price_vnd"] is None or c["price_vnd"] <= cap]
        near = shortlist(pool, centres, len(pool))
        return sorted(near, key=lambda c: -pref_fit(c, decision["trip_context"])[0])[:cfg.lodging_pool]
    raw = live_cards(centres, tc, cap, lodging_fn, live_cfg)
    return shortlist(sieve(raw, hard_filters, cfg.min_reviews), centres, cfg.lodging_k)


def rank(cands: list[dict], decision: dict, avg_min: dict, cfg: Settings, labels: dict | None = None) -> list[dict]:
    """lodging_score = w_pref·pref_fit + w_loc·loc_fit + w_price·price_fit + w_rating·rating_fit, best first, the
    lodging_k best kept. avg_min: candidate id -> mean minutes to the chosen places (None when not routable). Each
    candidate gains `fit` (why it suits), `avg_min` and `score`; a missing value adds 0, it never subtracts."""
    tc = decision["trip_context"]["context"]
    cap = price_cap(tc, max((tc.get("days") or 1) - 1, 0), cfg)
    w = cfg.lodging_weights
    out = []
    for c in cands:
        pref, why = pref_fit(c, decision["trip_context"], labels)
        m = avg_min.get(c["id"])
        loc = max(0.0, 1 - m / cfg.loc_ref_min) if m is not None else 0.0
        price = c.get("price_vnd")
        price_fit = (1 - 0.5 * price / cap) if price is not None and cap and price <= cap else 0.0
        rating_fit = min(max((c["rating"] - 3.5) / 1.5, 0.0), 1.0) if c.get("rating") else 0.0
        score = w["pref"] * pref + w["loc"] * loc + w["price"] * price_fit + w["rating"] * rating_fit
        out.append({**c, "fit": why, "avg_min": round(m) if m is not None else None, "score": round(score, 4)})
    out.sort(key=lambda c: (-c["score"], c["avg_min"] if c["avg_min"] is not None else 1e9))
    return out[:cfg.lodging_k]


def refresh_prices(shown: list[dict], cards: list[dict], cap: int | None, top: int = 5) -> list[dict]:
    """A date's live price for the first `top` served stays on screen (matched by the Maps id both share). The order
    stays as shown; a price over the trip's cap marks the candidate `over_cap` so it is no longer offered."""
    live = {c["id"]: c for c in cards if c.get("price_vnd") is not None}
    out = []
    for i, c in enumerate(shown):
        hit = live.get(c["id"]) if i < top and c.get("source") == "corpus" else None
        if hit:
            c = {**c, "price_vnd": hit["price_vnd"], "price_source": hit.get("price_source"),
                 "price_at": hit.get("price_at"), "over_cap": cap is not None and hit["price_vnd"] > cap}
        out.append(c)
    return out


def progress_event(cands: list[dict], baseline_travel_min: int | None) -> dict:
    """The one event P6's SSE server relays while lodging crawls in the background
    (docs/PLANNING.md §Chỗ ở không làm người dùng chờ). baseline_travel_min comes from the caller (the
    trip already scheduled once without lodging): this module never recomputes it.
    """
    return {"event": "progress", "stage": "lodging_scored",
            "candidates": [{"id": c["id"], "name": c["name"], "price_vnd": c["price_vnd"]} for c in cands],
            "baseline_travel_min": baseline_travel_min}
