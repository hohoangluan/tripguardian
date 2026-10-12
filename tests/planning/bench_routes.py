"""Offline seven-day planning benchmark: python tests/planning/bench_routes.py --runs 3 [--baseline PATH]."""

import argparse
import hashlib
import json
import statistics
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--baseline", type=Path, help="Saved source root containing src/ and config/")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    root = args.baseline or Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "src"))
    from plan_fixtures import CFG, FakeLive, day_ctx, decision, fake_matrix, no_geocode, rec
    from planning.engine import Engine
    from planning.route import order_day
    from planning.session import Store

    reports = {}
    for stops in (4, 7):
        ids = [f"p{i}" for i in range(stops)]
        records = [rec(pid, 11.94 + i * .001, 108.45, visit=(20, 40, 60)) for i, pid in enumerate(ids)]
        contexts = []
        for i, weekday in enumerate(("mon", "tue", "wed", "thu", "fri", "sat", "sun")):
            ctx = day_ctx(records, weekday=weekday, start_node="h", end_node="h", extra_nodes=["h"])
            contexts.append(replace(ctx, day=replace(ctx.day, index=i)))
        samples = []
        signatures = set()
        for _ in range(args.runs):
            started = time.perf_counter()
            results = [order_day(ids, ctx) for ctx in contexts]
            samples.append(time.perf_counter() - started)
            signatures.add(hashlib.sha256(json.dumps([asdict(r) for r in results], sort_keys=True).encode()).hexdigest())
        reports[f"route_{stops}_per_day"] = {"median_s": round(statistics.median(samples), 4),
                                              "min_s": round(min(samples), 4), "max_s": round(max(samples), 4),
                                              "signatures": sorted(signatures),
                                              "violations": sum(len(r.violations) for r in results),
                                              "travel_min": sum(r.travel_min for r in results),
                                              "time_penalty": sum(r.time_penalty for r in results)}

        records = [rec(f"p{i:02}", 11.94 + i * .001, 108.45, visit=(20, 40, 60)) for i in range(7 * stops)]
        selected = [r["id"] for r in records]
        samples, signatures = [], set()
        for _ in range(args.runs):
            engine = Engine(records, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode,
                            matrix_fn=fake_matrix, sun_fn=lambda *a: None, lodging_fn=lambda *a: [],
                            route_fn=lambda *a: None, background=False)
            started = time.perf_counter()
            created = engine.create(decision(selected, days=7, leave_at="21:00"))
            samples.append(time.perf_counter() - started)
            base = engine._base[created["id"]]
            quality = {"ok": base.ok, "warnings": base.warnings, "diagnostics": base.back_to_decision,
                       "variants": [{"objective": v["objective"], "results": [asdict(r) for r in v["_results"]],
                                     "metrics": v["metrics"], "robustness": v["robustness"]}
                                    for v in base.variants]}
            signatures.add(hashlib.sha256(json.dumps(quality, sort_keys=True).encode()).hexdigest())
        reports[f"create_{7 * stops}_places"] = {"median_s": round(statistics.median(samples), 4),
                                                  "min_s": round(min(samples), 4), "max_s": round(max(samples), 4),
                                                  "signatures": sorted(signatures), "ok": base.ok,
                                                  "variants": len(base.variants)}
    print(json.dumps({"runs": args.runs, "days": 7, "network": False, "cases": reports}, indent=2))


if __name__ == "__main__":
    main()
