"""Lodging candidates for the trip (docs/PLANNING.md ⓐ): search area, sieve, rank by taste first, location after.

Candidates are served `stay` records only. User-provided lodging can enter as a booked or manual point.
Hard requirements retain their unknown policy; physical and suitability checks fail closed.
"""

from corpus.serving import feature
from corpus.ontology import load as load_ontology
from requirements import allowed, hard_result
from trip import group_budget, nights

from .places import Place
from .settings import Settings
from .travel import km

# who travels along -> the suitability a lodging should have (config/ontology.yaml stay_features)
COMPANION_FEATURE = {"kids": "kids", "parents": "elderly", "partner": "couples"}


def _own(decision: dict) -> dict | None:
    """Where the user sleeps with a point: picked at Lựa chọn (Decision Output `lodging`), else booked in Trip
    Understanding (lodging_booked = yes)."""
    if lod := decision.get("lodging"):
        return lod
    tc = decision["trip_context"]["context"]
    lod = tc.get("lodging") or {}
    if tc.get("lodging_booked") != "yes" or lod.get("lat") is None or lod.get("lng") is None:
        return None
    return lod


def booked(decision: dict) -> dict | None:
    """The user's own lodging as a lodging point ({"id", "lat", "lng", "text", "source", "fetched_at", "price_vnd",
    "place_id"}); then Planning anchors every day there and suggests no lodging. Its id is the trip's own home node:
    Planning treats it as the trip's base. place_id: the served `stay` record it is, when it is one."""
    lod = _own(decision)
    if lod is None:
        return None
    return {"id": "@home", "lat": float(lod["lat"]), "lng": float(lod["lng"]), "text": lod.get("text") or "",
            "source": "user", "fetched_at": None, "price_vnd": lod.get("price_vnd"),
            "place_id": (lod.get("id") or lod.get("place_id")) if lod.get("kind") == "corpus" else None}


def with_booked_base(decision: dict) -> dict:
    """The Decision Output with its base set to the user's lodging (a no-op without one)."""
    lod = _own(decision)
    if lod is None:
        return decision
    tc = decision["trip_context"]
    base = {"place_id": None, "text": lod.get("text") or "", "lat": float(lod["lat"]), "lng": float(lod["lng"])}
    return {**decision, "trip_context": {**tc, "context": {**tc["context"], "base": base}}}


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
    budget = group_budget(ctx)
    if budget is None or nights <= 0:
        return None
    return round(budget * cfg.lodging_share / nights)


def hard_requirements(hard_filters: list[dict], default: str = "exclude") -> list[dict]:
    """The trip's hard filters with their unknown policy settled: fit / effort / suitability filters always exclude a
    place whose value is unknown; any other keeps the filter's own policy, and a missing policy means `default`
    (exclude: a hard filter is never read as optional unless it says "flag"). The one place that rule lives, for
    lodging and for suggestions."""
    requirements = []
    ontology = load_ontology() if hard_filters else None
    for f in hard_filters:
        fid = f["feature"]
        feature_def = ontology.features.get(fid)
        protected = fid.startswith("fit.") or (feature_def and feature_def.group in {"effort", "suitability"})
        requirements.append({**f, "unknown_policy": "exclude" if protected else f.get("unknown_policy", default)})
    return requirements


def sieve(raw: list[dict], hard_filters: list[dict], min_reviews: int) -> list[dict]:
    """Apply accommodation requirements; flag unknown legacy nonphysical filters and exclude safety unknowns."""
    requirements = hard_requirements(hard_filters, default="flag")      # legacy lodging filters carry no policy
    out = []
    for c in raw:
        if (c.get("reviews") or 0) < min_reviews:
            continue
        results, rejected = {}, False
        for requirement in requirements:
            fid = requirement["feature"]
            results[fid], _ = hard_result(c["rec"], requirement, activity="accommodation")
            if not allowed(c["rec"], requirement, activity="accommodation"):
                rejected = True
        if rejected:
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
    # far cluster's places sit a bit past one centre's radius (split_min is about travel time, not raw distance)
    return any(km((c["lat"], c["lng"]), (ct["lat"], ct["lng"])) <= 2 * ct["radius_km"] for ct in centres)


def from_record(r: dict) -> dict:
    """A served stay with its reference night price; person prices cannot establish room/night cost."""
    night = r["operation"].get("price_per_night")
    prov = r.get("provenance") or {}
    trend = prov.get("rating_trend") or {}
    price = night["value"] if night else None
    return {"id": r["id"], "name": r["identity"]["name"], "lat": r["identity"]["lat"], "lng": r["identity"]["lng"],
            "address": r["identity"].get("address"), "rating": trend.get("recent_mean"),
            "reviews": prov.get("voices") or 0, "price_vnd": price, "price_at": night["as_of"] if night else None,
            "source": "corpus", "fetched_at": prov.get("as_of"), "rec": r}


def stays_in(records: list[dict], centres: list[dict]) -> list[dict]:
    return [r for r in records if r["identity"].get("category_group") == "stay" and r["identity"].get("lat") is not None
            and r["identity"].get("lng") is not None and _in_area({"lat": r["identity"]["lat"], "lng": r["identity"]["lng"]}, centres)]


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


def candidates(by_place: dict[str, Place], decision: dict, cfg: Settings, records: list[dict] = ()) -> list[dict]:
    """The pool to rank: the served stays in the search area that pass the hard filters and the trip's price cap,
    the lodging_pool that fit the trip's taste best (nearest first on a tie, so the travel matrix stays small).
    [] when there are no places to anchor a search on or no stay in the area."""
    tc = decision["trip_context"]["context"]
    centres = search_area(by_place, tc.get("mobility"), cfg)
    if not centres:
        return []
    cap = price_cap(tc, nights(tc), cfg)
    hard_filters = decision["trip_context"].get("hard_filters") or []
    pool = [c for c in sieve([from_record(r) for r in stays_in(list(records), centres)], hard_filters, cfg.min_reviews)
            if cap is None or c["price_vnd"] is None or c["price_vnd"] <= cap]
    near = shortlist(pool, centres, len(pool))
    return sorted(near, key=lambda c: -pref_fit(c, decision["trip_context"])[0])[:cfg.lodging_pool]


def anywhere(decision: dict, cfg: Settings, records: list[dict] = (), limit: int | None = -1) -> list[dict]:
    """The same pool as `candidates` before any place is chosen: no area to search, so every served stay that passes the
    hard filters and the price cap, best taste fit first (rating after, so the list is not arbitrary).
    limit: how many to keep (default lodging_pool; None keeps every one, for the full list of Lựa chọn)."""
    tc = decision["trip_context"]["context"]
    cap = price_cap(tc, nights(tc), cfg)
    hard_filters = decision["trip_context"].get("hard_filters") or []
    stays = [r for r in records if r["identity"].get("category_group") == "stay" and r["identity"].get("lat") is not None
             and r["identity"].get("lng") is not None]
    pool = [c for c in sieve([from_record(r) for r in stays], hard_filters, cfg.min_reviews)
            if cap is None or c["price_vnd"] is None or c["price_vnd"] <= cap]
    pool = sorted(pool, key=lambda c: (-pref_fit(c, decision["trip_context"])[0], -(c.get("rating") or 0)))
    return pool if limit is None else pool[:cfg.lodging_pool if limit == -1 else limit]


def rank(cands: list[dict], decision: dict, avg_min: dict, cfg: Settings, labels: dict | None = None,
         keep: int | None = None) -> list[dict]:
    """lodging_score = w_pref·pref_fit + w_loc·loc_fit + w_price·price_fit + w_rating·rating_fit, best first, the
    lodging_k best kept. avg_min: candidate id -> mean minutes to the chosen places (None when not routable). Each
    candidate gains `fit` (why it suits), `avg_min` and `score`; keep: how many to return (default lodging_k); a missing value adds 0, it never subtracts."""
    tc = decision["trip_context"]["context"]
    cap = price_cap(tc, nights(tc), cfg)
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
    return out[:keep or cfg.lodging_k]


def progress_event(cands: list[dict], baseline_travel_min: int | None) -> dict:
    """The one event P6's SSE server relays while lodging crawls in the background
    (docs/PLANNING.md §Chỗ ở không làm người dùng chờ). baseline_travel_min comes from the caller (the
    trip already scheduled once without lodging): this module never recomputes it.
    """
    return {"event": "progress", "stage": "lodging_scored",
            "candidates": [{"id": c["id"], "name": c["name"], "price_vnd": c["price_vnd"]} for c in cands],
            "baseline_travel_min": baseline_travel_min}
