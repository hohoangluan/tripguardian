"""Lodging candidates for the trip (docs/PLANNING.md ⓐ): search area, sieve, shortlist to K.

Candidates never become Place Intelligence: they live only in this call's result, each carrying source and
fetched_at. A sieve step with no amenity evidence keeps the candidate (unknown, not rejected); it never drops one
it cannot check.
"""

from datetime import date, timedelta

from live import Unavailable

from .places import Place
from .settings import Settings
from .travel import km


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


def _evidence(cand: dict, feature: str) -> str | None:
    return "present" if feature in (cand.get("amenities") or []) else None


def sieve(raw: list[dict], hard_filters: list[dict], min_reviews: int) -> list[dict]:
    """A hard filter only rejects a candidate that has the evidence against it, never one with no evidence either
    way (that one is kept, unverified)."""
    out = []
    for c in raw:
        if (c.get("reviews") or 0) < min_reviews:
            continue
        if any(f["op"] == "ne" and _evidence(c, f["feature"]) == f["value"] for f in hard_filters):
            continue
        out.append(c)
    return out


def shortlist(cands: list[dict], centres: list[dict], k: int) -> list[dict]:
    """The k candidates closest (straight line) to whichever search centre is nearest them."""
    def dist(c: dict) -> float:
        return min(km((c["lat"], c["lng"]), (ct["lat"], ct["lng"])) for ct in centres)

    return sorted(cands, key=dist)[:k]


def candidates(by_place: dict[str, Place], decision: dict, cfg: Settings, lodging_fn, live_cfg) -> list[dict]:
    """[] on no places to anchor a search on, or when every centre's source was unavailable — never a reason to
    fail the whole plan: the "no lodging" option always stays alongside whatever this returns (ⓐ.5)."""
    tc = decision["trip_context"]["context"]
    centres = search_area(by_place, tc.get("mobility"), cfg)
    if not centres:
        return []
    nights = max((tc.get("days") or 1) - 1, 0)
    cap = price_cap(tc, nights, cfg)
    start = tc.get("start_date")
    check_out = ((date.fromisoformat(start) + timedelta(days=(tc.get("days") or 1) - 1)).isoformat()
                if start and tc.get("days") else None)
    hard_filters = decision["trip_context"].get("hard_filters") or []
    raw, seen = [], set()
    for ct in centres:
        try:
            found = lodging_fn((ct["lat"], ct["lng"]), ct["radius_km"], start, check_out, cap, live_cfg)
        except Unavailable:
            continue
        for c in found:
            # a generous multiple of radius_km, not radius_km itself: search_area may not split into two centres
            # even when a far cluster's places sit a bit past one centre's radius (split_min is about travel time,
            # not raw distance) -- this only needs to catch Maps padding a short list with another city entirely.
            if c["id"] not in seen and any(km((c["lat"], c["lng"]), (ct["lat"], ct["lng"])) <= 2 * ct["radius_km"]
                                           for ct in centres):
                seen.add(c["id"])
                raw.append(c)
    return shortlist(sieve(raw, hard_filters, cfg.min_reviews), centres, cfg.lodging_k)


def progress_event(cands: list[dict], baseline_travel_min: int | None) -> dict:
    """The one event P6's SSE server relays while lodging crawls in the background
    (docs/PLANNING.md §Chỗ ở không làm người dùng chờ). baseline_travel_min comes from the caller (the
    trip already scheduled once without lodging): this module never recomputes it.
    """
    return {"event": "progress", "stage": "lodging_scored",
            "candidates": [{"id": c["id"], "name": c["name"], "price_vnd": c["price_vnd"]} for c in cands],
            "baseline_travel_min": baseline_travel_min}
