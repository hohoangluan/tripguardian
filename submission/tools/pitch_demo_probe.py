"""Repeat the Decision -> overload -> confirm API path on real serving data.

This is an API rehearsal with a supplied SearchInput, not a browser or Agent demo.
Run: python submission/tools/pitch_demo_probe.py --runs 5 --out <report.json>
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from corpus.ontology import load as load_ontology
from corpus.serving import load as load_records
from decision import Data, Engine as DecisionEngine, Store, eval_search_input, load_settings
from planning import Engine as PlanningEngine
from trip import SearchInput


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    records = load_records()
    data = Data(records)
    si = eval_search_input({"hard": {}, "soft": {"nature": 1, "cozy_decor": 1}}, load_ontology().version)
    payload = si.model_dump(mode="json")
    payload["context"].update(budget_vnd=500000, frame={"days": [
        {"date": "2026-12-14", "start": "09:00", "end": "21:00"},
        {"date": "2026-12-15", "start": "08:00", "end": "18:00"}]})
    si = SearchInput.model_validate(payload)
    report = {"at": datetime.now(timezone.utc).isoformat(), "mode": "public_api_no_agent_no_browser",
              "input": si.model_dump(mode="json"), "runs": []}
    selected = None
    for index in range(args.runs):
        eng = DecisionEngine(data, load_settings(), Store(None))
        t0 = time.perf_counter()
        created = eng.create(si.model_dump(mode="json"))
        sid = created["id"]
        if selected is None:
            selected = [c for g in created["view"]["groups"] if g["id"] in {"nature", "cafe"}
                        for c in g["cards"][:5]]
            report["selection"] = [{"id": c["id"], "name": c["name"]} for c in selected]
        for card in selected:
            eng.act(sid, {"type": "select", "place_id": card["id"]})
        draft = eng.draft(sid, any_state=True)
        selected_s = time.perf_counter() - t0
        planner = PlanningEngine(records, background=False)
        t1 = time.perf_counter()
        plan = planner.create(draft)
        view = plan["view"]
        build_s = time.perf_counter() - t1
        row = {"run": index + 1, "selection_s": round(selected_s, 3), "planning_s": round(build_s, 3),
               "overload": view.get("overload"),
               "variants": [{"id": v["id"], "status": v.get("status"), "ok": v.get("ok"),
                             "dropped": v.get("dropped_by_plan"), "violations": v.get("violations")}
                            for v in view["variants"]], "confirmed": False}
        for variant in view["variants"]:
            if variant.get("status", "available") != "available":
                continue
            try:
                planner.act(plan["id"], {"type": "pick_variant", "id": variant["id"]})
                output = planner.confirm(plan["id"])
                row["confirmed"] = True
                row["chosen"] = variant["id"]
                row["output"] = output
                break
            except Exception as exc:
                row.setdefault("confirm_errors", []).append({"variant": variant["id"], "error": str(exc)})
        row["total_s"] = round(time.perf_counter() - t0, 3)
        report["runs"].append(row)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(index + 1, "overload", bool(row["overload"]), "confirmed", row["confirmed"], row["planning_s"], flush=True)


if __name__ == "__main__":
    main()
