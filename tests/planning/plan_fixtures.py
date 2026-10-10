"""Synthetic serving records, Decision Outputs and travel matrices that need no network, for the planning tests.

Helpers that need a module a later task creates import it inside the function, so this file works from task 2 on.
"""

from functools import cache

from planning import settings

from corpus.ontology import load as _load_ontology

load_ontology = cache(_load_ontology)       # rec() runs once per place, so the ontology file is read once
CFG = settings.load(settings.PATH)
DAYS7 = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def all_days(a="08:00", b="21:00"):
    return {d: [[a, b]] for d in DAYS7}


def rec(pid, lat, lng, *, area="area-1", usable=("experience", "backup"), hours="open", visit=(30, 60, 90),
        features=None, price=None, dup=None, name=None, status="VERIFIED", group="x"):
    """A serving record. hours: "open" = 08:00-21:00 every day, None = no hours, or a {weekday: [[open, close]]} dict.
    features: {feature id: value}, filed under the feature's group."""
    ontology = load_ontology()
    groups: dict = {}
    for fid, value in (features or {}).items():
        groups.setdefault(ontology.features[fid].group, {})[fid] = {
            "value": value, "distribution": {value: 3}, "status": "VERIFIED", "n": 3}
    h = all_days() if hours == "open" else hours
    return {"id": pid, "status": "VERIFIED", "status_reason": None,
            "identity": {"name": name or pid, "kind": "POI", "category": "x", "category_group": group, "lat": lat,
                         "lng": lng, "address": None, "area": area},
            "operation": {"hours": None if h is None else {"value": h, "status": status, "as_of": "2026-09-30"},
                          "price_per_person": None, "entry_fee": price,
                          "visit_minutes": {"short": visit[0], "typical": visit[1], "long": visit[2],
                                            "source": "category_default", "n": 0, "kind": "estimate"},
                          "booking": None, "crowd_by_time": None},
            "experience": groups.get("experience", {}), "environment": groups.get("environment", {}),
            "service": groups.get("service", {}), "effort": groups.get("effort", {}),
            "suitability": groups.get("suitability", {}), "usable_as": list(usable),
            "near_duplicate_group": dup}


def decision(ids, *, roles=None, days=2, start_date="2026-12-12", pace="normal", mobility="motorbike", base=None,
             entry=None, exit=None, hard=(), budget=None, max_leg=None, relaxed=None, checkin_at=None, checkout_at=None,
             flags=None, log=(), nights=None):
    """A Decision Output (docs/P3_PLACE_DECISION.md §15) as the JSON a session would write."""
    roles = roles or {}
    out = {
        "confirmed": [{"id": i, "name": i, "role": roles.get(i, "selected"), "visit": None,
                       "flags": (flags or {}).get(i, []), "relaxed": (relaxed or {}).get(i, [])} for i in ids],
        "backup_pool": [], "wishlist": [], "decision_log": list(log), "feasibility": {},
        "trip_context": {
            "context": {"start_date": start_date, "month": None, "days": days, "base": base, "entry_point": entry,
                        "exit_point": exit, "mobility": mobility, "companions": [], "people": 2,
                        "checkin_at": checkin_at, "checkout_at": checkout_at, "day_end": None, "budget_vnd": budget},
            "hard_filters": list(hard),
            "anchors": [{"place_id": i, "priority": "must"} for i in roles if roles[i] == "anchor"],
            "soft_weights": [], "pace": {"level": pace, "max_leg_min": max_leg, "crowd_tolerance": None},
            "novelty": {"level": None, "visited": []}, "unknowns": [], "unmapped": []},
    }
    if nights is not None:
        out["trip_context"]["context"]["nights"] = nights
    return out


def fake_matrix(points, mode, cfg):
    """Straight line x 1.4 at 25 km/h: what live.travel_matrix would answer, with no OSRM."""
    from planning.travel import km
    n = len(points)
    return {"minutes": [[0 if i == j else max(1, round(km(points[i], points[j]) * 1.4 / 25 * 60)) for j in range(n)]
                        for i in range(n)], "source": "osrm", "fetched_at": "2026-10-02T00:00:00+00:00"}


def no_geocode(text):
    return None


def fixed_sun(d, lat, lng, tz):
    return (6 * 60, 17 * 60 + 30)


def flat_travel(ids, minutes=10, **pairs):
    """Every pair `minutes` apart, except the pairs given as a_b=minutes (either direction)."""
    from planning.travel import Travel

    def m(a, b):
        return pairs.get(f"{a}_{b}", pairs.get(f"{b}_{a}", minutes))

    return Travel(list(ids), [[(0, "none") if a == b else (m(a, b), "motorbike") for b in ids] for a in ids],
                  "osrm", "t")


def line_travel(positions: dict, scale=5):
    """Nodes on a line: |difference of positions| x scale minutes, so every distance is easy to read."""
    from planning.travel import Travel
    ids = list(positions)
    return Travel(ids, [[(0, "none") if a == b else (max(1, round(abs(positions[a] - positions[b]) * scale)),
                                                      "motorbike") for b in ids] for a in ids], "osrm", "t")


def day_ctx(recs, *, minutes=10, pace="normal", weekday="mon", start=480, end=1260, start_node=None, end_node=None,
            sun=None, roles=None, travel=None, hard=(), extra_nodes=(), rain=None, prefs=None):
    """A DayCtx over the given rec(...) places with a flat travel matrix."""
    from planning.model import Day
    from planning.places import build_places
    from planning.schedule import DayCtx
    d = decision([r["id"] for r in recs], roles=roles, hard=hard)
    places, unplaced = build_places(d, {r["id"]: r for r in recs}, CFG)
    assert not unplaced, unplaced
    by_id = {p.id: p for p in places}
    day = Day(0, None, weekday, start, end, start_node, end_node)
    return DayCtx(day, by_id, travel or flat_travel([*by_id, *extra_nodes], minutes), CFG, pace, sun, rain, prefs)


CENTRE = (11.9404, 108.4583)
SOUTH = (11.9029, 108.4482)     # about 4 km from the centre


class FakeLive:
    """The one live setting build.prepare reads."""
    tz_offset_h = 7


def spot(pid, anchor, i, **kw):
    """A place i steps (about 300 m each) from one of the two centres; the area follows the centre."""
    return rec(pid, anchor[0] + i * 0.002, anchor[1] + i * 0.002, area="area-1" if anchor == CENTRE else "area-2", **kw)


def sample_trip(**kw):
    """Four places in the centre, three out south and a restaurant: the two-day trip the P4 tests share."""
    recs = [spot("c1", CENTRE, 0), spot("c2", CENTRE, 1), spot("c3", CENTRE, 2), spot("c4", CENTRE, 3),
            spot("s1", SOUTH, 0), spot("s2", SOUTH, 1), spot("s3", SOUTH, 2),
            spot("r1", CENTRE, 4, usable=("meal", "backup"))]
    return decision([r["id"] for r in recs], **kw), recs


def prepared(d, recs, weather=None, matrix=fake_matrix, extra_nodes=None):
    """build.prepare with every outside source replaced."""
    from planning.build import prepare
    return prepare(d, recs, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=matrix, sun_fn=fixed_sun,
                   weather=weather, extra_nodes=extra_nodes)


def small_trip(**kw):
    """Three places on a line, one day enough for all of them: small enough for move/reorder/lock tests to read."""
    recs = [spot("a", CENTRE, 0), spot("b", CENTRE, 1), spot("c", CENTRE, 2)]
    return decision([r["id"] for r in recs], days=1, **kw), recs


def fake_lodging(center, radius_km, check_in, check_out, price_max, live_cfg):
    cands = [{"id": "h1", "name": "Homestay 1", "lat": CENTRE[0] + 0.001, "lng": CENTRE[1], "rating": 4.5,
             "reviews": 20, "price_vnd": 300000, "amenities": ["wifi"]},
            {"id": "h2", "name": "Homestay 2", "lat": CENTRE[0] - 0.001, "lng": CENTRE[1], "rating": 4.2,
             "reviews": 15, "price_vnd": 900000, "amenities": []}]
    return [c for c in cands if price_max is None or c["price_vnd"] <= price_max]
