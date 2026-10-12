"""Two or three checked variants, each best on a different objective (docs/PLANNING.md ⓖ).

One prepare() and one travel matrix for all of them. Each chosen objective lays the trip out with its own day-split
weights; a variant validate rejects is dropped, two variants with the same days in the same order are one. No variant
valid -> back to Place Decision with the places that broke it. Lodging joins the loop in P5.
"""

from dataclasses import asdict

import live
from trip import nights

from .backup import backups
from .details import plan_notes
from .timefit import describe as time_description
from .recommendations import recommend
from .build import ENTRY, EXIT, flag_warnings, itinerary, prepare, render_text, schedule_trip, shared_output, \
    travel_load, with_home
from .lodging import candidates as lodging_candidates
from .objectives import LABEL, add_lodging_cost, choose, metrics, score
from .robustness import robustness
from .settings import load as load_settings

WARNING_TEXT = {
    "weather_unknown": "Chưa biết thời tiết: chưa xét mưa khi xếp lịch và khi đo độ vững.",
    "variants_same": "Các mục tiêu cho cùng một lịch: chỉ có {n} phương án.",
    "variant_invalid": "{label}: không xếp được lịch hợp lệ, bỏ phương án này.",
    "lodging_unavailable": "Chưa tra được chỗ ở: mỗi phương án dùng điểm vào / nơi ở đã biết làm neo.",
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
                   sun_fn=None, weather: dict | None = None, signals: dict | None = None) -> dict:
    trip = prepare(decision, records, cfg, live_cfg, geocode_fn, matrix_fn, sun_fn, weather, signals=signals)
    from .composer import compose
    composed = compose(trip)
    if composed is not None:
        composed["variants"] = [{k: v for k, v in variant.items() if not k.startswith("_")}
                                 for variant in composed["variants"]]
        return {**shared_output(trip), **composed}
    cfg = trip.cfg
    objectives = choose(decision["trip_context"], [cx.wet for cx in trip.ctxs], trip.ctxs[0].prefs, cfg)
    tried = [(obj, schedule_trip(trip, cfg.objective_weights[obj])) for obj in objectives]
    warnings = list(trip.warnings)
    if any(cx.rain is None for cx in trip.ctxs):
        warnings.append(_warn("weather_unknown"))
    valid = [(obj, s) for obj, s in tried if not s.violations]
    if not valid:
        first = tried[0][1]
        places = sorted({v.place_id for _, s in tried for v in s.violations if v.place_id})
        if not places:
            places = sorted({i for _, s in tried for v in s.violations if v.day is not None
                             for i in s.per_day[v.day]})
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
        notes = plan_notes(s.ctxs, s.results, decision, trip.weather, trip.by_place)  # season, last entry, dark road; what to prepare
        variants.append({
            "id": f"v{len(variants) + 1}", "objective": obj, "label": LABEL[obj], "score": list(score(obj, m)),
            "metrics": m, "itinerary": itinerary(days, s.results),
            "travel_load": travel_load(days, s.results),
            "time_suitability": time_description(s.ctxs, s.results),
            "recommendations": recommend(s.ctxs, s.results, decision, trip.by_id),
            "robustness": robustness(s.ctxs, s.results, trip.travel.source),
            "backups": backups(s.ctxs, s.results, decision, trip.by_id), "warnings": [*s.warnings, *notes["warnings"]],
            "checklist": notes["checklist"]})
    if len(variants) < len(valid):
        warnings.append(_warn("variants_same", n=len(variants)))
    weather_src = sorted({(w.get("source"), w.get("fetched_at")) for w in (weather or {}).values()
                          if w and w.get("source")}, key=lambda t: (t[0], t[1] or ""))
    out = {"ok": True, "variants": variants, "chosen": None, "comparison": _comparison(variants), "violations": [],
           "warnings": warnings + flag_warnings(decision), "back_to_decision": None, **shared_output(trip)}
    out["provenance"]["weather"] = [{"source": s, "fetched_at": f} for s, f in weather_src]
    return out


def render_variants(out: dict) -> str:
    """The variants as plain lines, for the command line."""
    lines = []
    for n, v in enumerate(out["variants"], 1):
        rob = v["robustness"]
        lines.append(f'== Phương án {n} · {v["label"]} · {rob["label"]}')
        body = render_text({"itinerary": v["itinerary"], "warnings": v["warnings"], "violations": [], "ok": True})
        lines += body.splitlines()[:-1]                 # its last line is the verdict, said once at the end
        lines.append("  Độ vững: " + "; ".join(rob["reasons"]))
        for p in v["backups"]["places"]:
            alts = ", ".join(f'{a["name"]} (~{a["minutes_rough"]} phút)' for a in p["alternatives"])
            lines.append(f'  Dự phòng cho {p["name"]} ({p["text"]}): {alts or p["none_text"]}')
        for x in v["backups"]["on_delay"]:
            lines.append(f'  Nếu trễ ở ngày {x["day"]}: bỏ {x["name"]} trước.')
    if len(out["comparison"]) > 1:
        lines.append("So sánh:")
        for r in out["comparison"]:
            cost = f'{r["cost_vnd"]:,} VND/người'
            if r["cost_unknown"]:
                cost += f' (+{r["cost_unknown"]} nơi chưa có giá)'
            lines.append(f'  {r["label"]}: {r["travel_min"]} phút di chuyển (+{r["travel_vs_best"]}), {cost}')
    for w in out["warnings"]:
        lines.append("! " + w["text"])
    for x in out["violations"]:
        lines.append(f'X {x["kind"]} ngày {(x["day"] + 1) if x["day"] is not None else "-"}: {x["detail"]}'
                     + (" (physical)" if x["physical"] else ""))
    if out["back_to_decision"]:
        lines.append("Không dựng được phương án hợp lệ: quay lại chọn địa điểm ("
                     + ", ".join(out["back_to_decision"]["places"]) + ").")
    lines.append("Hợp lệ." if out["ok"] else "KHÔNG hợp lệ.")
    return "\n".join(lines)


def _nights(ctx: dict) -> int:
    return nights(ctx)


def build_lodging_variants(decision: dict, records: list[dict], cfg=None, live_cfg=None, geocode_fn=None,
                           matrix_fn=None, sun_fn=None, weather: dict | None = None, lodging_fn=None,
                           signals: dict | None = None) -> dict:
    """build_variants, with lodging candidates competing as each day's anchor (docs/PLANNING.md ⓐ ⓖ).

    Every candidate (plus the original base, as "no lodging") is tried under every chosen objective, sharing one
    travel matrix and one day-order cache keyed on where each day starts and ends. An objective keeps whichever
    candidate scores best for it; two objectives may end up with different lodging. The top-level lodging block
    compares every candidate on least_travel's schedule, since that objective is always tried.
    """
    cfg = cfg or load_settings()
    live_cfg = live_cfg or live.load_settings()
    lodging_fn = lodging_fn or live.lodging_near
    base_trip = prepare(decision, records, cfg, live_cfg, geocode_fn, matrix_fn, sun_fn, weather, signals=signals)
    warnings = []
    try:
        cands = lodging_candidates(base_trip.by_place, decision, cfg, lodging_fn, live_cfg)
    except live.Unavailable:
        cands = []
    if not cands:
        warnings.append(_warn("lodging_unavailable"))
    trip = prepare(decision, records, cfg, live_cfg, geocode_fn, matrix_fn, sun_fn, weather, signals=signals,
                   extra_nodes={c["id"]: (c["lat"], c["lng"]) for c in cands})
    home0 = trip.days[0].start_node if trip.days else None
    from .composer import compose, profile_metrics, profile_violations, render_profile
    composed = compose(trip)
    if composed is not None:
        slept = _nights(decision["trip_context"]["context"])
        options = [{"id": None, "home": home0, "price": None, "name": None}] + [
            {"id": c["id"], "home": c["id"], "price": c["price_vnd"], "name": c["name"], "candidate": c}
            for c in cands]
        chosen_rows, lodging_rows = [], []
        for variant in composed["variants"]:
            preset = variant["preset"]
            scored = []
            for opt in options:
                t2 = trip if opt["home"] in (None, home0) else with_home(trip, opt["id"])
                sched = schedule_trip(t2, cfg.objective_weights[preset], kept=variant["kept"],
                                      allow_shrink=preset != "diverse")
                rendered = render_profile(t2, sched, preset, baseline=composed["keep_all"]["metrics"])
                valid_plan = rendered["confirmable"]
                m = rendered["metrics"]
                if opt["price"] is not None:
                    m["lodging_cost_vnd"] = opt["price"] * slept if isinstance(opt["price"], (int, float)) else None
                    if m["lodging_cost_vnd"] is not None:
                        m["estimated_cost_vnd"] += m["lodging_cost_vnd"]
                    else:
                        m["cost_basis"] = "partial"
                if preset == "low_cost":
                    rank_key = (not valid_plan, m["estimated_cost_vnd"], m["travel_min"], -m["utility"],
                                opt["price"] is None and opt["id"] is not None, opt["id"] or "")
                elif preset == "diverse":
                    rank_key = (not valid_plan, -(m["wish_coverage"] or 0), -m["diversity"],
                                m["duration_loss_min"], m["travel_min"], opt["id"] or "")
                else:
                    rank_key = (not valid_plan, -m["places"], -m["visit_density"], -m["utility"],
                                m["travel_min"], opt["id"] or "")
                scored.append((rank_key, opt, sched, rendered))
                if preset == "least_travel":
                    card = opt.get("candidate")
                    if opt["id"] is None or card:
                        row = {"id": opt["id"], "name": opt["name"] or "Không chỗ ở", "price_vnd": opt["price"],
                               "amenities": card["amenities"] if card else [], "total_travel_min": m["travel_min"]}
                        if card:
                            row["minutes_vs_no_lodging"] = m["travel_min"] - next(
                                (r["total_travel_min"] for r in lodging_rows if r["id"] is None), m["travel_min"])
                        lodging_rows.append(row)
            _, opt, sched, rendered = min(scored, key=lambda x: x[0])
            profile = {**variant, **rendered, "id": variant["id"], "preset": preset,
                       "lodging": {"id": opt["id"], "name": opt["name"], "price_vnd": opt["price"]},
                       "travel_load": travel_load([cx.day for cx in sched.ctxs], sched.results),
                       "robustness": robustness(sched.ctxs, sched.results, trip.travel.source),
                       "time_suitability": time_description(sched.ctxs, sched.results),
                       "backups": backups(sched.ctxs, sched.results, decision, trip.by_id),
                       "_results": sched.results, "_ctxs": sched.ctxs, "_home": opt["home"]}
            chosen_rows.append(profile)
        composed["variants"] = [{k: v for k, v in variant.items() if not k.startswith("_")}
                                 for variant in chosen_rows]
        composed["comparison"] = [{"variant": v["id"], "objective": v["preset"], "label": v["label"],
                                    **v["metrics"], "delta_vs_selection": v["delta_vs_selection"],
                                    "robustness": v["robustness"]["level"]} for v in chosen_rows]
        return {**shared_output(trip), **composed,
                "lodging": {"candidates": lodging_rows, "chosen": None}}
    options = [{"id": None, "home": home0, "price": None, "name": None}] + \
        [{"id": c["id"], "home": c["id"], "price": c["price_vnd"], "name": c["name"]} for c in cands]
    slept = _nights(decision["trip_context"]["context"])
    objectives = choose(decision["trip_context"], [cx.wet for cx in trip.ctxs], trip.ctxs[0].prefs, cfg)

    rows = {obj: [] for obj in objectives}
    for opt in options:
        t2 = trip if opt["home"] == home0 else with_home(trip, opt["home"])
        for obj in objectives:
            s = schedule_trip(t2, cfg.objective_weights[obj])
            m = metrics(s.ctxs, s.results) if not s.violations else None
            if m is not None and opt["id"] is not None:    # "no lodging" adds no cost, known or unknown
                m = add_lodging_cost(m, opt["price"], slept)
            rows[obj].append({**opt, "sched": s, "metrics": m})

    warnings += list(trip.warnings)
    if any(cx.rain is None for cx in trip.ctxs):
        warnings.append(_warn("weather_unknown"))

    best = {obj: min((r for r in rs if r["metrics"] is not None), key=lambda r: score(obj, r["metrics"]),
                     default=None) for obj, rs in rows.items()}
    best = {obj: r for obj, r in best.items() if r is not None}
    if not best:
        first = rows[objectives[0]][0]["sched"]
        places = sorted({v.place_id for rs in rows.values() for r in rs for v in r["sched"].violations if v.place_id})
        if not places:          # a violation with no place_id (e.g. a day-window overflow): name the day's places
            places = sorted({i for rs in rows.values() for r in rs for v in r["sched"].violations
                             if v.day is not None for i in r["sched"].per_day[v.day]})
        return {"ok": False, "variants": [], "chosen": None, "comparison": [], "lodging": None,
                "violations": [asdict(v) for v in first.violations],
                "warnings": warnings + first.warnings + flag_warnings(decision),
                "back_to_decision": {"reason": "no_valid_variant", "places": places}, **shared_output(trip)}
    warnings += [_warn("variant_invalid", label=LABEL[obj]) for obj in objectives if obj not in best]

    seen, variants = set(), []
    for obj, r in best.items():
        key = (r["home"], tuple(x.order for x in r["sched"].results))
        if key in seen:
            continue
        seen.add(key)
        s, m = r["sched"], r["metrics"]
        days = [cx.day for cx in s.ctxs]        # schedule_trip may pull a later day's start earlier (early_start)
        notes = plan_notes(s.ctxs, s.results, decision, trip.weather, trip.by_place)
        variants.append({
            "id": f"v{len(variants) + 1}", "objective": obj, "label": LABEL[obj], "score": list(score(obj, m)),
            "metrics": m, "itinerary": itinerary(days, s.results), "travel_load": travel_load(days, s.results),
            "time_suitability": time_description(s.ctxs, s.results),
            "recommendations": recommend(s.ctxs, s.results, decision, trip.by_id),
            "robustness": robustness(s.ctxs, s.results, trip.travel.source),
            "backups": backups(s.ctxs, s.results, decision, trip.by_id), "warnings": [*s.warnings, *notes["warnings"]],
            "checklist": notes["checklist"],
            "lodging": {"id": r["id"], "name": r["name"], "price_vnd": r["price"]}})
    if len(variants) < len(best):
        warnings.append(_warn("variants_same", n=len(variants)))

    least = rows.get("least_travel") or next(iter(rows.values()))
    baseline = next((r["metrics"]["travel_min"] for r in least if r["id"] is None and r["metrics"]), None)
    lodging_rows = []
    for r in least:
        if r["metrics"] is None:
            continue
        cand = next((c for c in cands if c["id"] == r["id"]), None)
        row = {"id": r["id"], "name": r["name"] or "Không chỗ ở", "price_vnd": r["price"],
              "amenities": cand["amenities"] if cand else [], "total_travel_min": r["metrics"]["travel_min"]}
        if baseline is not None and r["id"] is not None:
            row["minutes_vs_no_lodging"] = r["metrics"]["travel_min"] - baseline
        lodging_rows.append(row)

    weather_src = sorted({(w.get("source"), w.get("fetched_at")) for w in (weather or {}).values()
                          if w and w.get("source")}, key=lambda t: (t[0], t[1] or ""))
    out = {"ok": True, "variants": variants, "chosen": None, "comparison": _comparison(variants),
          "lodging": {"candidates": lodging_rows, "chosen": None}, "violations": [],
          "warnings": warnings + flag_warnings(decision), "back_to_decision": None, **shared_output(trip)}
    out["provenance"]["weather"] = [{"source": s_, "fetched_at": f} for s_, f in weather_src]
    return out


def render_lodging_variants(out: dict) -> str:
    """render_variants with a "Chỗ ở:" block comparing every candidate on least_travel's own measure."""
    lines = render_variants(out).splitlines()
    verdict = lines.pop()
    if out["lodging"]:
        lines.append("Chỗ ở:")
        for r in out["lodging"]["candidates"]:
            cost = f'{r["price_vnd"]:,} VND/đêm' if r["price_vnd"] is not None else "chưa có giá"
            delta = r.get("minutes_vs_no_lodging")
            tail = f' ({delta:+d} phút cả chuyến so với không chỗ ở)' if delta is not None and r["id"] else ""
            lines.append(f'  {r["name"]}: {cost}, tổng {r["total_travel_min"]} phút di chuyển cả chuyến{tail}')
    lines.append(verdict)
    return "\n".join(lines)
