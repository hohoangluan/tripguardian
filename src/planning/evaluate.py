"""Offline check of Planning on the serving records (docs/specs/PLANNING_SPEC.md §Đo).

python -m planning evaluate  ->  data/planning/eval.json

Each hidden trip of config/eval_trips.yaml (the same file src/decision/evaluate.py reads) becomes a Search Input,
run through Place Decision in process -- decision.Engine's own public create/act/confirm, no HTTP, no second
server -- into a Decision Output, then through Planning: create, pick the first ok variant, confirm.
"""

import json
import os
import time
from functools import cache
from pathlib import Path

import yaml

from corpus.ontology import load as load_ontology
from decision import Data as DecisionData, Engine as DecisionEngine, Store as DecisionStore
from decision import load_settings as decision_default
from trip import SearchInput

from .engine import Engine
from .session import Store
from .settings import ROOT

TRIPS = ROOT / "config" / "eval_trips.yaml"


@cache
def trips() -> list[dict]:
    """The named hidden trips of config/eval_trips.yaml -- not the `cross` combinations that file also builds
    (those exist for Decision's own feature-pass coverage; the 10 named trips already vary enough in hard/soft/role
    for Planning's purposes)."""
    raw = yaml.safe_load(TRIPS.read_text(encoding="utf-8"))
    return list(raw["trips"])


def search_input(trip: dict, version: int, days: int = 3) -> SearchInput:
    """Mirrors decision.evaluate's own (non-public) search_input() -- duplicated, not imported, since
    decision.evaluate is not part of decision's public API (decision/__init__.py)."""
    ont = load_ontology()
    return SearchInput.model_validate({
        "ontology_version": version,
        "context": {"start_date": "2026-12-14", "month": None, "days": days, "base": None, "mobility": "motorbike",
                    "companions": [], "people": 2, "arrive_at": "09:00", "leave_at": "15:00", "day_end": None,
                    "budget_vnd": 3_000_000, "experience": None},
        "hard_filters": [{"feature": f, "op": "ne", "value": v, "unknown_policy": "exclude"}
                         for f, v in trip["hard"].items()],
        "anchors": [],
        "soft_weights": [{"feature": f, "value": ont.features[f].values[0], "context": None, "weight": 1,
                          "source": "user"} for f in trip["soft"]],
        "pace": {"level": "normal", "max_leg_min": None, "crowd_tolerance": None},
        "novelty": {"level": None, "visited": []}, "unknowns": [], "unmapped": []})


def decision_outputs(records: list[dict], cfg=None) -> list[tuple[str, dict]]:
    """(trip id, Decision Output) for every hidden trip Place Decision can actually confirm -- a trip whose
    pipeline shortlist cannot fill its role, or whose feasibility is "partial"/"infeasible", is skipped (not an
    error: it means Place Decision itself found nothing fit, which Planning has nothing to schedule)."""
    cfg = cfg or decision_default()
    data = DecisionData(records)
    version = load_ontology().version
    out = []
    for trip in trips():
        eng = DecisionEngine(data, cfg, DecisionStore(None))  # a fresh Engine per trip: no session state to leak
        si = search_input(trip, version)
        created = eng.create(si.model_dump(mode="json"))
        sid = created["id"]
        picked = [c["id"] for g in created["view"]["groups"] if g["id"] != "anchors" for c in g["cards"]
                 if c["role"] == trip["role"]]
        for pid in picked:
            eng.act(sid, {"type": "select", "place_id": pid})
        try:
            confirmed = eng.confirm(sid)
        except Exception:  # decision.NotConfirmable is not part of decision's public API; catch broadly on purpose
            continue
        out.append((trip["id"], confirmed))
    return out


def plan_results(decision_output: dict, records: list[dict], planning_cfg=None, live_cfg=None, geocode_fn=None,
                 matrix_fn=None, sun_fn=None, lodging_fn=None, route_fn=None) -> dict:
    """One hidden trip's Decision Output, laid out and measured. background=False: the lodging crawl (itself
    offline/fixture-driven in tests, real in run()) finishes before create() returns, so ms_total below already
    includes it -- matching docs/specs/PLANNING_SPEC.md §Đo's "Độ trễ: dựng 21 phương án · crawl chỗ ở"."""
    if not decision_output["confirmed"]:  # Planning would call an empty trip ok with 0 minutes: not a feasible itinerary
        return {"ok": False, "ms_variants": 0, "reason": "no_confirmed_places"}
    eng = Engine(records, cfg=planning_cfg, live_cfg=live_cfg, store=Store(None), geocode_fn=geocode_fn,
                 matrix_fn=matrix_fn, sun_fn=sun_fn, lodging_fn=lodging_fn, route_fn=route_fn, background=False)
    t0 = time.perf_counter()
    created = eng.create(decision_output)
    ms_variants = round((time.perf_counter() - t0) * 1000)
    view = created["view"]
    if not view["ok"]:
        return {"ok": False, "ms_variants": ms_variants, "reason": (view["back_to_decision"] or {}).get("reason")}
    sid = created["id"]
    variant = view["variants"][0]
    if not any(i["kind"] == "visit" for d in variant["itinerary"] for i in d["items"]):  # ok with nothing scheduled
        return {"ok": False, "ms_variants": ms_variants, "reason": "no_visits"}
    travel_no_lodging = variant["metrics"]["travel_min"]
    eng.act(sid, {"type": "pick_variant", "id": variant["id"]})
    # Try every candidate, remember the best one's id -- `pick_lodging` on the next candidate overwrites the
    # previous pick, so the loop itself never leaves the session on the best choice; that happens explicitly after.
    best_travel, best_id = travel_no_lodging, None
    for c in eng.lodging(sid)["candidates"]:
        eng.act(sid, {"type": "pick_lodging", "id": c["id"]})
        total = sum(d["travel_min"] for d in eng.load(sid)["view"]["travel_load"])
        if total < best_travel:
            best_travel, best_id = total, c["id"]
    if best_id is not None:
        eng.act(sid, {"type": "pick_lodging", "id": best_id})
    else:
        eng.act(sid, {"type": "clear_lodging"})
    ms_total = round((time.perf_counter() - t0) * 1000)
    baseline = eng.baseline_travel_min(sid)
    try:
        out = eng.confirm(sid)
    except Exception as e:
        return {"ok": False, "ms_variants": ms_variants, "ms_total": ms_total, "reason": str(e)}
    nights = max((decision_output["trip_context"]["context"].get("days") or 1) - 1, 0)
    saved_per_day = (travel_no_lodging - best_travel) / max(nights, 1)
    return {"ok": True, "ms_variants": ms_variants, "ms_total": ms_total, "travel_min": travel_no_lodging,
            "travel_with_lodging_min": best_travel, "baseline_travel_min": baseline,
            "lodging_saved_min_per_day": round(saved_per_day, 1),
            "robustness": out["robustness"]["level"]}


ROBUSTNESS_LEVELS = ("solid", "feasible", "fragile")  # src/planning/robustness.py


def evaluate(records: list[dict] | None = None, decision_cfg=None, planning_cfg=None, live_cfg=None,
             geocode_fn=None, matrix_fn=None, sun_fn=None, lodging_fn=None, route_fn=None) -> dict:
    from corpus.serving import load as load_serving
    records = records if records is not None else load_serving()
    rows = []
    for trip_id, decision_output in decision_outputs(records, decision_cfg):
        row = plan_results(decision_output, records, planning_cfg, live_cfg, geocode_fn, matrix_fn, sun_fn,
                           lodging_fn, route_fn)
        rows.append({"trip": trip_id, **row})
    ok_rows = [r for r in rows if r["ok"]]
    n = len(rows)

    def pct_saved(r):
        return 0.0 if r["baseline_travel_min"] == 0 else 100 * (1 - r["travel_min"] / r["baseline_travel_min"])

    summary = {
        "trips": n, "ok": len(ok_rows),
        "feasible_itinerary_rate": round(len(ok_rows) / n, 3) if n else 0.0,
        "avg_saved_vs_baseline_pct": round(sum(pct_saved(r) for r in ok_rows) / len(ok_rows), 1) if ok_rows else 0.0,
        "avg_lodging_saved_min_per_day": round(sum(r["lodging_saved_min_per_day"] for r in ok_rows) / len(ok_rows), 1)
                                        if ok_rows else 0.0,
        "robustness": {lv: sum(1 for r in ok_rows if r["robustness"] == lv) for lv in ROBUSTNESS_LEVELS},
        "ms_total_max": max((r.get("ms_total", 0) for r in rows), default=0),
        "not_ok_trips": [{"trip": r["trip"], "reason": r["reason"]} for r in rows if not r["ok"]],
    }
    return {"summary": summary, "trips": rows}


def run() -> dict:
    import live
    res = evaluate(live_cfg=live.load_settings())
    d = Path(os.environ.get("DATA_DIR", "data"))
    out = (d if d.is_absolute() else ROOT / d) / "planning" / "eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"evaluate: {json.dumps(res['summary'], ensure_ascii=False)}")
    return res
