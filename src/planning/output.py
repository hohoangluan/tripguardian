"""Plan Output (docs/PLANNING.md §Plan Output): the chosen variant, finalized at confirm().

route and cost are the two parts no variant dict already carries (route needs a fresh OSRM call per day; cost needs
the chosen lodging's price). Everything else here is reshaping what build.py / variants.py already computed.
"""

import live
from trip import nights

from .build import chunk_view, flag_warnings, shared_output
from .details import plan_notes
from .settings import fmt


def route_of_day(day, result, coords: dict, live_cfg, mobility, route_fn=None) -> dict | None:
    """The shape of one day's path (OSRM /route), or None when it cannot be drawn: fewer than two stops with known
    coordinates, or the source is unavailable. Never a reason to fail confirm -- a plan with no drawable route is
    still valid, just without a line on the map."""
    route_fn = route_fn or live.route_shape
    nodes = [day.start_node] + [i.place_id for i in result.items if i.kind == "visit"] + [day.end_node]
    points = [coords[n] for n in nodes if n is not None and n in coords]
    if len(points) < 2:
        return None
    try:
        return route_fn(points, mobility, live_cfg)
    except live.Unavailable:
        return None


def cost(metrics: dict, lodging_price_vnd: int | None, nights: int) -> dict:
    """known_vnd: tickets / drinks already summed in metrics, plus the lodging's total price when it is known.
    unknown_items: places with no known price, plus the lodging itself when it is chosen but priceless."""
    lodging_total = lodging_price_vnd * nights if lodging_price_vnd is not None else None
    lodging_known = lodging_price_vnd is not None or nights <= 0
    return {"known_vnd": metrics["cost_vnd"] + (lodging_total or 0),
           "unknown_items": metrics["cost_unknown"] + (0 if lodging_known else 1),
           "lodging_known": lodging_known}


def time_budget(days: list, slept: int) -> dict:
    """The usable time of the trip: "3 ngày 2 đêm" is three days of which the first opens at arrival and the last
    closes at departure, so the sum is less than 3 full days. Minutes are the day windows the schedule worked in."""
    per_day = [{"day": d.index + 1, "from": fmt(d.start), "to": fmt(d.end), "minutes": max(d.end - d.start, 0)}
               for d in days]
    return {"days": len(per_day), "nights": slept, "per_day": per_day,
            "total_minutes": sum(p["minutes"] for p in per_day)}


def build(trip, variants: list[dict], chosen: dict, chosen_results: list, decision: dict, coords: dict, live_cfg,
         route_fn=None) -> dict:
    """chosen: one of variants.build_lodging_variants' per-variant dicts (itinerary already rendered to text).
    chosen_results: the DayResult objects behind it (Schedule.results for the day order route_of_day needs)."""
    mobility = decision["trip_context"]["context"].get("mobility")
    days = [cx.day for cx in trip.ctxs][: len(chosen_results)] or trip.days[: len(chosen_results)]
    slept = nights(decision["trip_context"]["context"])
    lodging = chosen.get("lodging") or {}
    shared = shared_output(trip)
    # a variant already carries its notes (variants.py); a chosen dict without them is read here
    notes = ({"warnings": [], "checklist": chosen["checklist"]} if "checklist" in chosen else
             plan_notes(list(trip.ctxs)[: len(chosen_results)], chosen_results, decision, trip.weather, trip.by_place))
    return {
        "variants": [{"id": v["id"], "objective": v["objective"], "label": v["label"], "score": v["score"]}
                     for v in variants],
        "chosen": chosen["id"],
        "itinerary": chosen["itinerary"],
        **(chunk_view(chosen["itinerary"], trip.cfg.chunk_days) if len(days) > trip.cfg.chunk_days else {}),
        "route": [route_of_day(d, r, coords, live_cfg, mobility, route_fn) for d, r in zip(days, chosen_results)],
        "time_budget": time_budget(trip.days, slept),
        "lodging": {"chosen": lodging, "candidates": []},
        "cost": cost(chosen["metrics"], lodging.get("price_vnd"), slept),
        "travel_load": chosen["travel_load"],
        "reasons": shared["reasons"],
        "tradeoffs": shared["tradeoffs"],
        "warnings": trip.warnings + chosen["warnings"] + flag_warnings(decision) + notes["warnings"],
        "checklist": notes["checklist"],
        "uncertainty": shared["uncertainty"],
        "robustness": chosen["robustness"],
        "backups": chosen["backups"],
        "time_suitability": chosen.get("time_suitability") or [],
        "recommendations": chosen.get("recommendations") or [],
        "provenance": shared["provenance"],
        **{k: shared[k] for k in ("day_conditions", "crowd_tips") if k in shared},      # only when the days had any
    }
