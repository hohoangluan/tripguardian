"""Areas, near-duplicate groups and MMR picking over serving records (docs/P3_PLACE_DECISION.md §7, §9). Pure functions.

Area: places within area_km of a dense leader share one area id, a coarse "khu vực" for context fit.
Near duplicate: same category group, same roles, and Jaccard of their evidenced experience / environment
(feature, value) pairs that say what kind of place it is (NOT_KIND left out) >= the threshold, measured against
the group's leader. MMR: next pick = max of λ·score − (1−λ)·max similarity to the picks so far.
"""

import math
from collections.abc import Callable

from .record import config

GROUP_ASPECTS = ("experience", "environment")
# what kind of place it is, not how good: quality, crowd, cleanliness or parking make no two places alike
NOT_KIND = {"food_quality", "drink_quality", "crowd", "cleanliness", "parking", "weather_exposed", "toilet",
            "mosquitoes"}


def km(a: dict, b: dict) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lng"], b["lat"], b["lng"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def _leaders(items: list, linked: Callable[[object, object], bool]) -> list[list]:
    """Leader clustering: in the given order, an item joins the first leader it is linked to, else leads a new
    cluster. Unlike single linkage it never chains A~B~C into one cluster when A and C are unlike."""
    clusters: list[list] = []
    for x in items:
        home = next((c for c in clusters if linked(c[0], x)), None)
        if home is None:
            clusters.append([x])
        else:
            home.append(x)
    return clusters


def areas(records: list[dict], radius_km: float | None = None) -> dict[str, str]:
    """record id -> area id ("area-<n>", largest first): leaders are the places with the most neighbours within
    radius_km, so an area is a disc of that radius around a dense spot. Places without a location get none."""
    radius = radius_km if radius_km is not None else config()["area_km"]
    pts = [(r["id"], float(r["identity"]["lat"]), float(r["identity"]["lng"])) for r in records
           if r["identity"].get("lat") is not None and r["identity"].get("lng") is not None]
    cell = radius / 111  # degrees; a neighbour is at most one cell away
    grid: dict[tuple, list] = {}
    for p in pts:
        grid.setdefault((int(p[1] // cell), int(p[2] // cell)), []).append(p)

    def near(p):
        cx, cy = int(p[1] // cell), int(p[2] // cell)
        return [q for dx in (-1, 0, 1) for dy in (-1, 0, 1) for q in grid.get((cx + dx, cy + dy), ())
                if km({"lat": p[1], "lng": p[2]}, {"lat": q[1], "lng": q[2]}) <= radius]

    density = {p[0]: len(near(p)) for p in pts}
    order = sorted(pts, key=lambda p: (-density[p[0]], p[0]))
    clusters = _leaders(order, lambda a, b: km({"lat": a[1], "lng": a[2]}, {"lat": b[1], "lng": b[2]}) <= radius)
    clusters.sort(key=lambda c: (-len(c), c[0][0]))
    return {p[0]: f"area-{n}" for n, c in enumerate(clusters, 1) for p in c}


def signature(record: dict) -> frozenset:
    """Kind features many of the place's reviewers name: one passing mention does not make a place a "cafe with
    animals"."""
    min_n, min_rate = config()["experience_min_n"], config()["experience_min_mention_rate"]
    return frozenset((fid, f["value"]) for g in GROUP_ASPECTS for fid, f in record.get(g, {}).items()
                     if f["n"] >= min_n and (f["mention_rate"] or 0) >= min_rate and fid not in NOT_KIND)


def similarity(a: dict, b: dict, sigs: dict | None = None) -> float:
    """sigs: record id -> signature, precomputed for many pairs."""
    if a["identity"].get("category_group") != b["identity"].get("category_group") or set(a["usable_as"]) != set(b["usable_as"]):
        return 0.0
    sa, sb = (sigs[a["id"]], sigs[b["id"]]) if sigs else (signature(a), signature(b))
    if min(len(sa), len(sb)) < config()["near_duplicate"]["min_features"]:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def near_duplicate_groups(records: list[dict], threshold: float | None = None) -> list[list[str]]:
    """Groups (record ids, leader first) of two or more near duplicates; a place in no group is distinct. Leaders
    are the places with the most evidenced kind features, so a group gathers places like its best-described one."""
    t = threshold if threshold is not None else config()["near_duplicate"]["jaccard"]
    sigs = {r["id"]: signature(r) for r in records}
    buckets: dict[tuple, list[dict]] = {}
    for r in records:  # only places of one category group and the same roles can be alike
        buckets.setdefault((r["identity"].get("category_group"), tuple(sorted(r["usable_as"]))), []).append(r)
    out = []
    for bucket in buckets.values():
        order = sorted(bucket, key=lambda r: (-len(sigs[r["id"]]), r["id"]))
        out += [[r["id"] for r in c] for c in _leaders(order, lambda a, b: similarity(a, b, sigs) >= t) if len(c) > 1]
    return sorted(out, key=lambda ids: (-len(ids), ids[0]))


def mmr(records: list[dict], scores: dict[str, float], k: int, lam: float | None = None) -> list[str]:
    """Up to k record ids: high score, but each unlike the ones picked before."""
    lam = lam if lam is not None else config()["mmr_lambda"]
    pool, picked = {r["id"]: r for r in records}, []
    sigs = {r["id"]: signature(r) for r in records}
    while pool and len(picked) < k:
        def gain(rid):
            sim = max((similarity(pool[rid], p, sigs) for p in picked), default=0.0)
            return lam * scores.get(rid, 0.0) - (1 - lam) * sim
        best = max(sorted(pool), key=gain)
        picked.append(pool.pop(best))
    return [p["id"] for p in picked]
