"""Two or three checked variants, each best on a different objective (docs/specs/PLANNING_SPEC.md ⓖ).

One prepare() and one travel matrix for all of them. Each chosen objective lays the trip out with its own day-split
weights; a variant validate rejects is dropped, two variants with the same days in the same order are one. No variant
valid -> back to Place Decision with the places that broke it. Lodging joins the loop in P5.
"""

from dataclasses import asdict

from .backup import backups
from .build import flag_warnings, itinerary, prepare, schedule_trip, shared_output, travel_load
from .objectives import LABEL, choose, metrics, score
from .robustness import robustness

WARNING_TEXT = {
    "weather_unknown": "Chưa biết thời tiết: chưa xét mưa khi xếp lịch và khi đo độ vững.",
    "variants_same": "Các mục tiêu cho cùng một lịch: chỉ có {n} phương án.",
    "variant_invalid": "{label}: không xếp được lịch hợp lệ, bỏ phương án này.",
}


def _warn(code: str, **kw) -> dict:
    return {"code": code, "text": WARNING_TEXT[code].format(**kw)}


def _comparison(variants: list[dict]) -> list[dict]:
    """The trade-off table: each variant's measures, and how far it is from the best variant on travel."""
    best_travel = min(v["metrics"]["travel_min"] for v in variants)
    return [{"variant": v["id"], "objective": v["objective"], "label": v["label"],
             "travel_min": v["metrics"]["travel_min"], "travel_vs_best": v["metrics"]["travel_min"] - best_travel,
             "cost_vnd": v["metrics"]["cost_vnd"], "cost_unknown": v["metrics"]["cost_unknown"],
             "rain_exposed": v["metrics"]["rain_exposed"], "repeats": v["metrics"]["repeats"],
             "robustness": v["robustness"]["level"]} for v in variants]


def build_variants(decision: dict, records: list[dict], cfg=None, live_cfg=None, geocode_fn=None, matrix_fn=None,
                   sun_fn=None, weather: dict | None = None) -> dict:
    trip = prepare(decision, records, cfg, live_cfg, geocode_fn, matrix_fn, sun_fn, weather)
    cfg = trip.cfg
    objectives = choose(decision["trip_context"], [cx.rain for cx in trip.ctxs], trip.ctxs[0].prefs, cfg)
    tried = [(obj, schedule_trip(trip, cfg.objective_weights[obj])) for obj in objectives]
    warnings = list(trip.warnings)
    if not any(cx.rain is not None for cx in trip.ctxs):
        warnings.append(_warn("weather_unknown"))
    valid = [(obj, s) for obj, s in tried if not s.violations]
    if not valid:
        first = tried[0][1]
        places = sorted({v.place_id for _, s in tried for v in s.violations if v.place_id})
        return {"ok": False, "variants": [], "chosen": None, "comparison": [],
                "violations": [asdict(v) for v in first.violations],
                "warnings": warnings + first.warnings + flag_warnings(decision),
                "back_to_decision": {"reason": "no_valid_variant", "places": places}, **shared_output(trip)}
    warnings += [_warn("variant_invalid", label=LABEL[obj]) for obj, s in tried if s.violations]
    seen, variants = set(), []
    for obj, s in valid:
        orders = tuple(r.order for r in s.results)
        if orders in seen:
            continue
        seen.add(orders)
        m = metrics(s.ctxs, s.results)
        days = [cx.day for cx in s.ctxs]        # schedule_trip may pull a later day's start earlier (early_start)
        variants.append({
            "id": f"v{len(variants) + 1}", "objective": obj, "label": LABEL[obj], "score": list(score(obj, m)),
            "metrics": m, "itinerary": itinerary(days, s.results),
            "travel_load": travel_load(days, s.results),
            "robustness": robustness(s.ctxs, s.results, trip.travel.source),
            "backups": backups(s.ctxs, s.results, decision, trip.by_id), "warnings": s.warnings})
    if len(variants) < len(valid):
        warnings.append(_warn("variants_same", n=len(variants)))
    weather_src = sorted({(w.get("source"), w.get("fetched_at")) for w in (weather or {}).values()
                          if w.get("source")})
    out = {"ok": True, "variants": variants, "chosen": None, "comparison": _comparison(variants), "violations": [],
           "warnings": warnings + flag_warnings(decision), "back_to_decision": None, **shared_output(trip)}
    out["provenance"]["weather"] = [{"source": s, "fetched_at": f} for s, f in weather_src]
    return out
