"""Shared selection utilities, protected choices and measurements for overload plans and edited schedules."""

import math
from collections import Counter
from statistics import median

from corpus.serving import feature
from requirements import applicable

from .objectives import metrics
from .traits import kind_group, preference, visit_minutes

def selection_utilities(trip) -> dict[str, float]:
    selected = {c["id"]: c for c in trip.decision.get("confirmed", [])}
    soft = trip.decision.get("trip_context", {}).get("soft_weights") or []
    result = {}
    for pid, c in selected.items():
        raw = c.get("utility")
        if isinstance(raw, (int, float)) and math.isfinite(raw):
            result[pid] = max(0.001, float(raw))
        elif pid in trip.by_place:
            result[pid] = 1.0 + preference(trip.by_place[pid], soft)
        else:
            result[pid] = 1.0
    return result


def utilities(trip) -> dict[str, float]:
    result = selection_utilities(trip)
    soft = trip.decision.get("trip_context", {}).get("soft_weights") or []
    for pid, p in trip.by_place.items():
        if pid not in result:
            result[pid] = 1.0 + preference(p, soft)
    return result


def must_places(trip) -> set[str]:
    tc = trip.decision["trip_context"]
    return {c["id"] for c in trip.decision["confirmed"] if c.get("role") in {"anchor", "locked"}} | \
        {a["place_id"] for a in tc.get("anchors") or [] if a.get("priority") == "must"}


def _wishes(trip, sched) -> dict:
    wishes = [w for w in trip.decision["trip_context"].get("soft_weights") or [] if w.get("weight", 0) > 0]
    seen = set()
    wishes = [w for w in wishes if not ((w["feature"], w["value"]) in seen
              or seen.add((w["feature"], w["value"])))]
    met, unmet, unknown = [], [], []
    visit_at = {it.place_id: (cx, result, it) for cx, result in zip(sched.ctxs, sched.results)
                for it in result.items if it.kind == "visit"}
    for wish in wishes:
        fid, matched, evidence, timing_unknown = wish["feature"], False, False, False
        for pid, p in trip.by_place.items():
            fact = feature(p.rec, fid)
            if not applicable(p.rec, wish, p.activity, p.kind) or not fact or fact.get("status") != "VERIFIED":
                continue
            evidence = True
            if fact.get("value") != wish["value"] or pid not in visit_at:
                continue
            cx, result, item = visit_at[pid]
            # The original wish, not the post-_unpin Place copy, defines whether timing is part of this wish.
            if fid not in p.pins:
                matched = True
                continue
            pin = cx.cfg.pins.get(fid)
            if pin is None:
                timing_unknown = True
                continue
            if pin["anchor"] == "clock":
                lo, hi = pin["from"], pin["to"]
            elif cx.sun is None:
                timing_unknown = True
                continue
            else:
                base = cx.sun[0] if pin["anchor"] == "sunrise" else cx.sun[1]
                lo, hi = base + pin["from_min"], base + pin["to_min"]
            if pid not in result.unpinned and lo <= item.start <= hi:
                matched = True
        entry = {"feature": fid, "value": wish["value"]}
        (met if matched else unknown if timing_unknown or not evidence else unmet).append(entry)
    return {"met": met, "unmet": unmet, "unknown": unknown, "total": len(wishes),
            "coverage": len(met) / len(wishes) if wishes else None}


def profile_metrics(trip, sched) -> dict:
    """Measurements on the actual timeline, also used after the user's edits."""
    m = metrics(sched.ctxs, sched.results)
    visits = [(cx, it) for cx, r in zip(sched.ctxs, sched.results) for it in r.items if it.kind == "visit"]
    kept = {it.place_id for _, it in visits}
    values = utilities(trip)
    sel_values = selection_utilities(trip)
    sel_total = sum(sel_values.values())
    retained_sel = sum(sel_values[pid] for pid in kept if pid in sel_values)
    value_share = retained_sel / sel_total if sel_total > 0 else 1.0
    visit_min = sum(it.end - it.start for _, it in visits)
    loss = sum(max(0, visit_minutes(cx.places[it.place_id], cx.cfg, cx.pace, cx.prefs) - (it.end - it.start))
               for cx, it in visits)
    counts = Counter()
    for pid in kept:
        p = trip.by_place.get(pid) or next((cx.places[pid] for cx in sched.ctxs if pid in cx.places), None)
        if p and kind_group(p):
            counts[kind_group(p)] += 1
    visited = set((trip.decision.get("trip_context", {}).get("novelty") or {}).get("visited") or [])
    novelty = (trip.decision.get("trip_context", {}).get("novelty") or {}).get("level")
    known_prices = {}
    for p in trip.by_place.values():
        if p.cost_vnd is not None:
            known_prices.setdefault(kind_group(p), []).append(p.cost_vnd)
    imputed, unestimated = 0, 0
    for pid in kept:
        p = trip.by_place.get(pid) or next((cx.places[pid] for cx in sched.ctxs if pid in cx.places), None)
        if p and p.cost_vnd is None:
            prices = known_prices.get(kind_group(p))
            if prices:
                imputed += median(prices)
            else:
                unestimated += 1
    mobility = trip.decision.get("trip_context", {}).get("context", {}).get("mobility")
    rate = trip.cfg.composer.get("transport_vnd_per_min", {}).get(mobility)
    transport = round(m["travel_min"] * rate) if isinstance(rate, (int, float)) and rate >= 0 else None
    wish = _wishes(trip, sched)
    duration = visit_min + m["travel_min"]
    m.update({"places": len(kept), "visit_min": visit_min, "duration_loss_min": loss,
              "visit_density": visit_min / duration if duration else 0,
              "categories_covered": len(counts), "diversity": len(counts) + sum(math.sqrt(n) for n in counts.values()),
              "novelty_share": len(kept - visited) / len(kept) if kept and novelty else None,
              "wish_coverage": wish["coverage"], "wishes": wish,
              "value_share": value_share,
              "utility": sum(values.get(pid, 1.0) for pid in kept),
              "utility_source": "decision_score" if kept <= set(sel_values) and all(c.get("utility") is not None for c in
                                                        trip.decision.get("confirmed", [])) else "selection_and_preferences",
              "transport_cost_vnd": transport,
              "estimated_cost_vnd": round(m["cost_vnd"] + imputed + (transport or 0)),
              "cost_unestimated": unestimated,
              "cost_basis": "partial" if m["cost_unknown"] or m['meal_cost_unknown'] or transport is None else "estimated",
              "meals_included": not m['meal_cost_unknown'] and all(cx.places[it.place_id].cost_vnd is not None
                                     for cx, it in visits if cx.places[it.place_id].kind == 'meal')})
    return m

