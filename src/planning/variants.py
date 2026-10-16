"""The plan cards of a trip (spec section 7): one main plan, or -- when the days cannot hold every pick -- up to three
direction plans that each drop places by one criterion (overload.py), plus the overload card. One prepare() and one
travel matrix for all of them. A fitting plan that breaks a check is no plan: back to Place Decision with the places
that broke it. The command line (build_variants / build_lodging_variants) and the session engine read the same cards.
"""

import live
from trip import nights

from .details import plan_notes
from .recommendations import recommend
from .build import flag_warnings, prepare, render_text, schedule_trip, shared_output, with_home
from .lodging import candidates as lodging_candidates
from .objectives import add_lodging_cost
from .overload import plan_or_directions
from .settings import load as load_settings

WARNING_TEXT = {
    "weather_unknown": "Chưa biết thời tiết: chưa xét mưa khi xếp lịch và khi đo độ vững.",
    "lodging_unavailable": "Chưa tra được chỗ ở: mỗi phương án dùng điểm vào / nơi ở đã biết làm neo.",
}


def _warn(code: str, **kw) -> dict:
    return {"code": code, "text": WARNING_TEXT[code].format(**kw)}


def _comparison(variants: list[dict]) -> list[dict]:
    """The trade-off table: each card's measures, and how far it is from the best card on travel."""
    if not variants:
        return []
    best_travel = min(v["metrics"]["travel_min"] for v in variants)
    return [{"variant": v["id"], "objective": v["objective"], "label": v["label"],
             "travel_min": v["metrics"]["travel_min"], "travel_vs_best": v["metrics"]["travel_min"] - best_travel,
             "cost_vnd": v["metrics"]["cost_vnd"], "cost_unknown": v["metrics"]["cost_unknown"],
             "rain_exposed": v["metrics"]["rain_exposed"], "repeats": v["metrics"]["repeats"],
             "robustness": v["robustness"]["level"]} for v in variants]


def _hours(minutes: int) -> str:
    h = minutes / 60
    return f"{h:.0f}" if h >= 2 or h == int(h) else f"{h:.1f}".replace(".", ",")


def drop_metadata(trip, vid: str, dropped) -> list[dict]:
    """Legacy drop fields for both offered and selected cards, including a merged card's representative criterion."""
    return [{"place_id": d["place_id"], "name": d["name"], "reason": vid, "text": d["reason"],
             "saved_min": trip.by_place[d["place_id"]].visit[trip.cfg.visit_key[trip.pace]],
             "saved_vnd": trip.by_place[d["place_id"]].cost_vnd, "regret": None, "source": "plan"}
            for d in dropped]


def plan_cards(trip, *, protected=()) -> dict:
    """overload.plan_or_directions plus what its readers need around it:
    - back_to_decision names the places (place_id + name) no day had room for;
    - a fitting main plan that breaks a check (a must place with no data, a hazard, the budget) is no plan: no card,
      back to Place Decision with the places that broke it (the legacy fail-closed result);
    - fields the web still reads until the plan screen is rebuilt: each card's `dropped_by_plan`, the overload card's
      `text`, `selection_places`, `keep_all_valid` (always False: keeping every pick does not fit)."""
    out = plan_or_directions(trip, protected=protected)
    name = lambda pid: trip.by_place[pid].name if pid in trip.by_place else pid
    for v in out["variants"]:
        v["dropped_by_plan"] = drop_metadata(trip, v["id"], v["dropped"])
    ov = out["overload"]
    if ov is not None:
        available = sum(max(0, cx.day.end - cx.day.start) for cx in trip.ctxs)
        ov.update(level="overloaded", estimated=True, needed=available + ov["missing_min"], available=available,
                  binding=[], selection_places=ov["places"], keep_all_valid=False,
                  text=f"Không đủ thời gian cho cả {ov['places']} nơi: thiếu ~{_hours(ov['missing_min'])} giờ")
    back = out["back_to_decision"]
    violations: list = []
    if back is not None:
        back = {**back, "leftover": [{"place_id": pid, "name": name(pid)} for pid in back.get("leftover") or ()]}
    elif ov is None and not out["ok"]:
        main = out["variants"][0]
        violations = main["violations"]
        places = sorted({v["place_id"] for v in violations if v.get("place_id")})
        if not places:          # a violation with no place (a day past its end): name that day's places
            days = {v["day"] for v in violations if v.get("day") is not None}
            places = sorted({pid for k, r in enumerate(main["_results"]) if k in days for pid in r.order})
        back = {"reason": "no_valid_variant", "places": places, "leftover": []}
        out = {**out, "variants": []}
    return {**out, "back_to_decision": back, "violations": violations}


def _public(v: dict) -> dict:
    return {k: x for k, x in v.items() if not k.startswith("_")}


def _output(trip, cards: dict, decision: dict, weather: dict | None, lodging=None) -> dict:
    """The command line's Plan Output for a set of cards: each card with its notes and suggestions."""
    variants = []
    for v in cards["variants"]:
        notes = plan_notes(v["_ctxs"], v["_results"], decision, trip.weather, trip.by_place)
        variants.append({**_public(v), "warnings": [*v["warnings"], *notes["warnings"]], "checklist": notes["checklist"],
                         "recommendations": recommend(v["_ctxs"], v["_results"], decision, trip.by_id),
                         **({"lodging": lodging} if lodging is not None else {})})
    warnings = list(trip.warnings) + cards["warnings"]
    if any(cx.rain is None for cx in trip.ctxs):
        warnings.append(_warn("weather_unknown"))
    weather_src = sorted({(w.get("source"), w.get("fetched_at")) for w in (weather or {}).values()
                          if w and w.get("source")}, key=lambda t: (t[0], t[1] or ""))
    out = {**shared_output(trip), "ok": bool(variants) and cards["ok"], "variants": variants, "chosen": None,
           "comparison": _comparison(variants), "keep_all": None, "violations": cards["violations"], "overload": cards["overload"],
           "warnings": warnings + flag_warnings(decision), "back_to_decision": cards["back_to_decision"]}
    out["provenance"]["weather"] = [{"source": s, "fetched_at": f} for s, f in weather_src]
    return out


def build_variants(decision: dict, records: list[dict], cfg=None, live_cfg=None, geocode_fn=None, matrix_fn=None,
                   sun_fn=None, weather: dict | None = None, signals: dict | None = None) -> dict:
    trip = prepare(decision, records, cfg, live_cfg, geocode_fn, matrix_fn, sun_fn, weather, signals=signals)
    return _output(trip, plan_cards(trip), decision, weather)


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


def build_lodging_variants(decision: dict, records: list[dict], cfg=None, live_cfg=None, geocode_fn=None,
                           matrix_fn=None, sun_fn=None, weather: dict | None = None,
                           signals: dict | None = None) -> dict:
    """build_variants with one lodging (spec section 3: the plan is built with exactly one place to sleep). Every
    served candidate (plus the original base, as "no lodging") lays the main plan out on one shared travel matrix;
    the one whose days hold the most picks with the least travel (then the cheaper known price) anchors the cards.
    The `lodging` block compares every candidate on that main plan's travel."""
    cfg = cfg or load_settings()
    live_cfg = live_cfg or live.load_settings()
    base_trip = prepare(decision, records, cfg, live_cfg, geocode_fn, matrix_fn, sun_fn, weather, signals=signals)
    warnings = []
    cands = lodging_candidates(base_trip.by_place, decision, cfg, records)
    if not cands:
        warnings.append(_warn("lodging_unavailable"))
    trip = prepare(decision, records, cfg, live_cfg, geocode_fn, matrix_fn, sun_fn, weather, signals=signals,
                   extra_nodes={c["id"]: (c["lat"], c["lng"]) for c in cands})
    home0 = trip.ctxs[0].home if trip.ctxs else None
    slept = nights(decision["trip_context"]["context"])
    options = [{"id": None, "home": home0, "price": None, "name": None}] + \
        [{"id": c["id"], "home": c["id"], "price": c["price_vnd"], "name": c["name"]} for c in cands]
    tried = []
    for opt in options:
        t2 = trip if opt["home"] == home0 else with_home(trip, opt["home"])
        s = schedule_trip(t2)
        travel = sum(r.travel_min for r in s.results)
        rank = (len(s.leftover), len(s.violations), travel, opt["id"] is not None and opt["price"] is None,
                opt["price"] or 0, opt["id"] or "")
        tried.append((rank, opt, t2, travel))
    _, best, t_best, _ = min(tried, key=lambda x: x[0])
    cards = plan_cards(t_best)
    lodging = {"id": best["id"], "name": best["name"], "price_vnd": best["price"]}
    for v in cards["variants"]:
        if best["id"] is not None:
            v["metrics"] = add_lodging_cost(v["metrics"], best["price"], slept)
    out = _output(t_best, cards, decision, weather, lodging)
    baseline = next(travel for _, opt, _, travel in tried if opt["id"] is None)
    rows = [{"id": opt["id"], "name": opt["name"] or "Không chỗ ở", "price_vnd": opt["price"],
             "total_travel_min": travel, **({"minutes_vs_no_lodging": travel - baseline} if opt["id"] else {})}
            for _, opt, _, travel in tried]
    out["warnings"] = warnings + out["warnings"]
    out["lodging"] = {"candidates": rows, "chosen": None} if cards["variants"] else None
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
