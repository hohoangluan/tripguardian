"""Offline synthetic edit benchmark: python tests/planning/bench_edits.py [--runs 10]."""

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--baseline", type=Path, help="A saved pre-change planning package, imported in a fresh process")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    if args.baseline:
        sys.path.insert(0, str(args.baseline / "src"))
    from plan_fixtures import CFG, FakeLive, decision, fake_matrix, no_geocode, rec
    from planning.engine import Engine
    from planning.objectives import metrics
    from planning.session import Store
    import planning.schedule as schedule
    import planning.route as route
    import planning.repair as repair
    import planning.robustness as robustness
    import planning.recommendations as recommendations
    count = [0]
    original = schedule.simulate
    def counted(*a, **kw):
        count[0] += 1
        return original(*a, **kw)
    for module in (schedule, route, repair, robustness, recommendations):
        module.simulate = counted
    records = [rec(pid, 11.94 + i * .001, 108.45, price={"typical_vnd": 50000})
               for i, pid in enumerate(("a", "b", "c"))]
    records.append(rec("coffee", 11.941, 108.451, group="cafe", price={"typical_vnd": 30000}))
    d = decision(["a", "b", "c"], days=1)
    d["backup_pool"] = [{"id": "coffee", "for": "a"}]
    d["trip_context"]["activities"] = {"coffee": "coffee"}
    samples = {k: [] for k in ("bootstrap", "cold_edit", "warm_edit", "load", "cold_suggestions_ready", "warm_suggestions_ready")}
    calls = {k: [] for k in ("cold_edit", "warm_edit", "load")}
    quality = []
    last_timings = {}
    for _ in range(args.runs):
        e = Engine(records, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode,
                   matrix_fn=fake_matrix, sun_fn=lambda *a: None, lodging_fn=lambda *a: [],
                   route_fn=lambda *a: None, background=True)
        started = time.perf_counter()
        sid = e.create(d)["id"]
        e.act(sid, {"type": "pick_variant", "id": "v1"})
        samples["bootstrap"].append((time.perf_counter() - started) * 1000)
        def wait_suggestions():
            if hasattr(e, "suggestions"):
                deadline = time.monotonic() + 5
                while e.suggestions(sid)["status"] == "pending":
                    if time.monotonic() > deadline:
                        raise RuntimeError("suggestions did not finish")
                    time.sleep(.001)
        wait_suggestions()
        for phase in ("cold_edit", "warm_edit"):
            started, before = time.perf_counter(), count[0]
            e.act(sid, {"type": "add_from_backup", "place": "coffee", "day": 0})
            samples[phase].append((time.perf_counter() - started) * 1000)
            calls[phase].append(count[0] - before)
            wait_suggestions()
            samples[phase.replace("_edit", "_suggestions_ready")].append((time.perf_counter() - started) * 1000)
            s, base = e.store.get(sid), e._base[sid]
            results = e._turn_current(s, base)
            _, ctxs = e._ctxs_for(base.trip, e._places_for(s, base), e._home_for(s, base), s.state, results)
            from planning.validate import validate
            m = metrics(ctxs, results)
            quality.append({"travel_min": m["travel_min"], "time_penalty": m["time_penalty"],
                            "violations": len(validate(ctxs, results, [], set(), None, None))})
            e.act(sid, {"type": "drop_place", "place": "coffee"})
            wait_suggestions()
        started, before = time.perf_counter(), count[0]
        e.load(sid)
        samples["load"].append((time.perf_counter() - started) * 1000)
        calls["load"].append(count[0] - before)
        last_timings = getattr(e, "timings", {}).get(sid, {})
    def summary(values):
        return {"p50_ms": round(statistics.median(values), 3),
                "p95_ms": round(sorted(values)[math.ceil(len(values) * .95) - 1], 3)}
    print(json.dumps({"runs": args.runs, "latency": {k: summary(v) for k, v in samples.items()},
                      "simulate_calls": {k: {"min": min(v), "max": max(v)} for k, v in calls.items()},
                      "quality": {"travel_min": sorted({x["travel_min"] for x in quality}),
                                  "time_penalty": sorted({x["time_penalty"] for x in quality}),
                                  "max_violations": max(x["violations"] for x in quality)},
                      "last_timings": last_timings}, indent=2))


if __name__ == "__main__":
    main()
