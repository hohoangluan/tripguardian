"""Controlled fault injection for pitch evidence; synthetic data, no network.

Run: python tests/planning/bench_pitch_validator.py --out <report.json>
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from plan_fixtures import all_days, day_ctx, rec
from planning.model import DayResult, Item
from planning.validate import validate


def measure():
    rows = []
    for offset in (0, 10, 20, 30, 40):
        start = 600 + offset
        price = {"min_vnd": 100000, "typical_vnd": 100000, "max_vnd": 100000}
        safe = rec("a", 11.94, 108.45, price=price, features={"steep_or_stairs": "absent"})
        other = rec("b", 11.941, 108.45)
        visit = Item("visit", start, start + 60, place_id="a", name="a")
        normal = day_ctx([safe, other], minutes=20)
        hard = [{"feature": "steep_or_stairs", "op": "ne", "value": "present", "unknown_policy": "exclude"}]
        cases = [
            ("overlap", normal, [visit, Item("visit", start + 50, start + 110, place_id="b")], [], None),
            ("hours", day_ctx([rec("a", 11.94, 108.45, hours=all_days("08:00", "09:00"))]), [visit], [], None),
            ("budget", normal, [visit], [], 99999),
            ("travel", normal, [Item("travel", start, start + 19, from_id="a", to_id="b")], [], None),
            ("hard_unknown", day_ctx([rec("a", 11.94, 108.45)]), [visit], hard, None),
            ("hard_forbidden", day_ctx([rec("a", 11.94, 108.45, features={"steep_or_stairs": "present"})]), [visit], hard, None),
        ]
        for kind, cx, items, filters, budget in cases:
            control_items = ([Item("travel", start, start + 20, from_id="a", to_id="b")]
                             if kind == "travel" else [visit])
            control = DayResult(tuple(control_items), (), (), 0, 0, control_items[-1].end)
            clean = validate([normal], [control], filters, set(), 100000 if budget else None, None)
            altered = DayResult(tuple(items), (), (), 0, 0, items[-1].end)
            violations = validate([cx], [altered], filters, set(), budget, None)
            expected = "hard" if kind.startswith("hard_") else kind
            rows.append({"case": kind, "offset_min": offset, "expected": expected,
                         "detected": expected in {v.kind for v in violations},
                         "violations": [v.kind for v in violations],
                         "control_violations": [v.kind for v in clean]})
    return {"at": datetime.now(timezone.utc).isoformat(), "synthetic": True,
            "cases": len(rows), "detected": sum(r["detected"] for r in rows),
            "controls": len(rows), "false_positives": sum(bool(r["control_violations"]) for r in rows),
            "rows": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = measure()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}))
    raise SystemExit(0 if report["detected"] == report["cases"] and not report["false_positives"] else 1)
