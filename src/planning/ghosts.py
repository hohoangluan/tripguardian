"""Faded suggestions (spec §6): every empty meal slot and every long free time shows one real place, open then,
near the stops around it, that fits the trip's taste; "xem thêm" opens the next two. Not on the timeline until the
user taps it (then it is an add_from_backup of that id).

Hard rules (a place failing one is never shown): the trip's hard filters, open during the slot, within
suggest_radius_min (meal_detour_max for a meal) of a stop next to the slot. Soft rules (they only rank): taste
(`traits.preference`), a role that fits the meal, no dish or place already suggested in the trip. Price never enters
the score; the card only shows it.
"""

import math
from bisect import bisect_left, bisect_right

from requirements import allowed, hard_result

from .lodging import booked, hard_requirements
from .places import build_places, windows_on
from .roles import _text
from .traits import preference
from .travel import km, rough_minutes

SLOT_ROLES = {"breakfast": {"breakfast"}, "lunch": {"main", "breakfast"}, "dinner": {"main", "night_meal"},
              "free": {"light", None}}
MEAL_SLOTS = ("breakfast", "lunch", "dinner")
OPEN_FOR_MIN = 30                       # a place must stay open this long after the slot starts
SHAKY_HOURS = ("UNCERTAIN", "OUTDATED")
WANTED_DISH_BONUS = 2.0                 # a wanted dish outweighs a taste fit of two soft weights, or a whole radius of detour


class Pool(list):
    """The places a trip's suggestions may come from, plus what `fill` needs to know about them."""
    unverified: dict                    # place id -> hard filters (flag policy) whose value is unknown for it
    wanted: list                        # (dish, place ids) the user asked for that no chosen place serves

    def __init__(self, places=(), unverified=None, wanted=None):
        super().__init__(places)
        self.unverified = unverified or {}
        self.wanted = wanted or []

    def __deepcopy__(self, memo):
        # Never changed after pool() builds it: a trial copy of the engine's base (preview_act, make_room) shares it
        # instead of copying hundreds of places and their records.
        return self


def _anchors(records_by_id: dict, chosen: set, decision: dict) -> list[tuple[float, float]]:
    """The stops a suggestion may sit next to: every chosen place and the lodging."""
    pts = [(records_by_id[i]["identity"]["lat"], records_by_id[i]["identity"]["lng"]) for i in sorted(chosen)
           if i in records_by_id and records_by_id[i]["identity"].get("lat") is not None
           and records_by_id[i]["identity"].get("lng") is not None]
    home = booked(decision)
    base = decision["trip_context"]["context"].get("base") or {}
    for lat, lng in ((home["lat"], home["lng"]) if home else (None, None), (base.get("lat"), base.get("lng"))):
        if lat is not None and lng is not None and (lat, lng) not in pts:
            pts.append((lat, lng))
    return pts


def _wanted(decision: dict, by_id: dict, chosen: set) -> list:
    """The dishes the user asked for that no chosen place serves: (casefolded dish, place ids)."""
    dishes = ((decision["trip_context"].get("wishes") or {}).get("dishes")) or []
    out = []
    for w in dishes:
        dish = (w.get("dish") or "").casefold()
        ids = set(w.get("place_ids") or ())
        if not dish or ids & chosen or any(dish in _text(by_id[i]) for i in chosen if i in by_id):
            continue
        out.append((dish, ids))
    return out


def pool(records: list[dict], decision: dict, cfg) -> Pool:
    """Places the suggestions may come from: the eating places and sights within suggest_radius_min of a chosen stop
    or the lodging (at most suggest_pool_max nearest each), that the hard filters allow. Records are not lodging
    candidates, so `lodging.sieve` (candidate dicts judged as "accommodation") does not fit: each place is judged by
    its own activity and kind instead, as the validator does, with the one unknown-policy rule `hard_requirements`."""
    rl = cfg.realistic
    ctx = decision["trip_context"]["context"]
    chosen = {c["id"] for c in decision["confirmed"]}
    hard = hard_requirements(decision["trip_context"].get("hard_filters") or [])
    by_id = {r["id"]: r for r in records}
    usable = [r for r in records if r["id"] not in chosen and r["identity"].get("category_group") != "stay"
              and (r.get("usable_as") or []) and r["identity"].get("lat") is not None
              and r["identity"].get("lng") is not None]
    mobility = ctx.get("mobility")
    radius_km = rl["suggest_radius_min"] / 60 * cfg.rough_speed_kmh[mobility or "motorbike"] / cfg.road_factor
    box = radius_km * 1.05 / 111.0 + 0.001               # degrees of latitude, a little generous
    usable.sort(key=lambda r: r["identity"]["lat"])
    lats = [r["identity"]["lat"] for r in usable]
    near: dict = {}
    for a in _anchors(by_id, chosen, decision):
        scored = []
        lng_box = box / max(0.2, math.cos(math.radians(a[0])))
        # only the latitude band around the anchor is scanned (the corpus has thousands of places)
        for r in usable[bisect_left(lats, a[0] - box):bisect_right(lats, a[0] + box)]:
            lat, lng = r["identity"]["lat"], r["identity"]["lng"]
            if abs(lng - a[1]) > lng_box:
                continue
            m = rough_minutes(km(a, (lat, lng)), mobility, cfg)
            if m <= rl["suggest_radius_min"]:
                scored.append((m, r["id"], r))
        scored.sort(key=lambda x: (x[0], x[1]))
        for _, rid, r in scored[: rl["suggest_pool_max"]]:
            near[rid] = r
    picked = [near[i] for i in sorted(near)]
    places, _ = build_places({"confirmed": [{"id": r["id"]} for r in picked], "trip_context": decision["trip_context"]},
                             {r["id"]: r for r in picked}, cfg)
    kept, unverified = [], {}
    for p in places:
        if not all(allowed(p.rec, hf, p.activity, p.kind) for hf in hard):
            continue
        kept.append(p)
        open_ones = [hf["feature"] for hf in hard
                     if hard_result(p.rec, hf, p.activity, p.kind)[0] == "unknown"]
        if open_ones:
            unverified[p.id] = open_ones
    return Pool(kept, unverified, _wanted(decision, by_id, chosen))


def _where(cx, node, points: dict):
    if node is None:
        return None
    p = cx.places.get(node)
    if p:
        return (p.lat, p.lng)
    pt = points.get(node)
    return (pt.lat, pt.lng) if pt else None


_READ: dict = {}        # id(place) -> (place, cfg, text, dishes): a pool's places are frozen and read every edit


def _read(p, cfg) -> tuple[str, set]:
    """(_text, _dishes) of a place, worked out once per place: fill reads every pool place for every empty slot of
    every edit, and casefolding its menu each time was most of a faded-suggestion pass."""
    hit = _READ.get(id(p))
    if hit is not None and hit[0] is p and hit[1] is cfg:
        return hit[2], hit[3]
    if len(_READ) >= 8192:
        _READ.clear()
    text, dishes = _text(p.rec), _dishes(p, cfg)
    _READ[id(p)] = (p, cfg, text, dishes)
    return text, dishes


def _dishes(p, cfg) -> set:
    """The dishes a place is known for: its menu's dish names and the breakfast dishes in its name."""
    menu = {(d.get("name") or "").casefold() for d in (p.rec.get("menu") or {}).get("dishes") or []} - {""}
    text = _text(p.rec)
    return menu | {d for d in cfg.realistic["breakfast_dishes"] if d in text}


def fill(ctxs, results, places: list, taken: set, dismissed: set, soft: list, points: dict,
         wanted: list | None = None) -> list[dict]:
    """One entry per empty meal slot and per long free time: the best three places for it, the first shown faded.
    `wanted` = (dish, place ids) the user asked for and no chosen place serves; default = the pool's own."""
    wanted = getattr(places, "wanted", []) if wanted is None else wanted
    unverified = getattr(places, "unverified", {})
    out = []
    shown: set = set()       # the first suggestion of every slot so far, over the whole trip
    shown_dishes: set = set()
    for cx, r in zip(ctxs, results):
        rl = cx.cfg.realistic
        radius = rl["suggest_radius_min"]
        used = set(taken)    # places already on a timeline or shown today
        items = list(r.items)
        for k, it in enumerate(items):
            if it.kind == "meal_free" and it.name in MEAL_SLOTS:
                kind = it.name
            elif it.kind == "free" and it.end - it.start >= rl["fill_min_gap"]:
                kind = "free"
            else:
                continue
            prev = next((i.place_id or i.to_id for i in reversed(items[:k]) if i.place_id or i.to_id), cx.day.start_node)
            nxt = next((i.place_id or i.to_id for i in items[k + 1:] if i.place_id or i.to_id), cx.day.end_node)
            before, after = _where(cx, prev, points), _where(cx, nxt, points)
            rough = lambda a, b: rough_minutes(km(a, b), cx.mobility, cx.cfg)
            direct = rough(before, after) if before and after else 0
            ranked = []
            for p in places if (before or after) else ():     # no stop to measure from: no ghost
                if p.id in used or p.id in dismissed or p.meal_kind not in SLOT_ROLES[kind]:
                    continue
                spans = windows_on(p.hours, cx.day.weekday)
                if spans is not None and not any(o <= it.start and it.start + OPEN_FOR_MIN <= c for o, c in spans):
                    continue
                at = (p.lat, p.lng)
                legs = [rough(q, at) for q in (before, after) if q]
                if min(legs) > radius:
                    continue
                detour = max(0, sum(legs) - direct) if len(legs) == 2 else legs[0]
                if kind != "free" and detour > rl["meal_detour_max"]:
                    continue
                text, dishes = _read(p, cx.cfg)
                repeat = p.id in shown or bool(dishes & shown_dishes)
                want = any(p.id in ids or dish in text for dish, ids in wanted)
                ranked.append((-preference(p, soft) + detour / radius + (1.0 if repeat else 0.0)
                               - (WANTED_DISH_BONUS if want else 0.0), detour, p))
            ranked.sort(key=lambda x: (x[0], x[2].id))
            top = []
            for _, d, p in ranked[:3]:
                item = {"place_id": p.id, "name": p.name, "price_vnd": p.cost_vnd, "detour_min": d}
                if unverified.get(p.id):
                    item["unverified"] = list(unverified[p.id])
                if spans_unknown(p, cx.day.weekday):
                    item["hours_unknown"] = True
                top.append(item)
            if ranked:
                first = ranked[0][2]
                used.add(first.id)
                shown.add(first.id)
                shown_dishes |= _read(first, cx.cfg)[1]
            out.append({"day": cx.day.index, "kind": kind, "start": it.start, "end": it.end, "items": top})
    return out


def spans_unknown(p, weekday) -> bool:
    """Whether the place's opening time is not known for sure: no hours for that day, or hours the record calls shaky."""
    return windows_on(p.hours, weekday) is None or p.hours_status in SHAKY_HOURS
