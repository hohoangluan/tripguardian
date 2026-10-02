"""Plan Output (docs/specs/PLANNING_SPEC.md §Plan Output): the chosen variant, finalized at confirm().

route and cost are the two parts no variant dict already carries (route needs a fresh OSRM call per day; cost needs
the chosen lodging's price). Everything else here is reshaping what build.py / variants.py already computed.
"""

import live

from .build import flag_warnings, shared_output


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


def build(trip, variants: list[dict], chosen: dict, chosen_results: list, decision: dict, coords: dict, live_cfg,
         route_fn=None) -> dict:
    """chosen: one of variants.build_lodging_variants' per-variant dicts (itinerary already rendered to text).
    chosen_results: the DayResult objects behind it (Schedule.results for the day order route_of_day needs)."""
    mobility = decision["trip_context"]["context"].get("mobility")
    days = [cx.day for cx in trip.ctxs][: len(chosen_results)] or trip.days[: len(chosen_results)]
    nights = max((decision["trip_context"]["context"].get("days") or 1) - 1, 0)
    lodging = chosen.get("lodging") or {}
    shared = shared_output(trip)
    return {
        "variants": [{"id": v["id"], "objective": v["objective"], "label": v["label"], "score": v["score"]}
                     for v in variants],
        "chosen": chosen["id"],
        "itinerary": chosen["itinerary"],
        "route": [route_of_day(d, r, coords, live_cfg, mobility, route_fn) for d, r in zip(days, chosen_results)],
        "lodging": {"chosen": lodging, "candidates": []},
        "cost": cost(chosen["metrics"], lodging.get("price_vnd"), nights),
        "travel_load": chosen["travel_load"],
        "reasons": shared["reasons"],
        "tradeoffs": shared["tradeoffs"],
        "warnings": trip.warnings + chosen["warnings"] + flag_warnings(decision),
        "uncertainty": shared["uncertainty"],
        "robustness": chosen["robustness"],
        "backups": chosen["backups"],
        "provenance": shared["provenance"],
    }
