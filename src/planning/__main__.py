"""python -m planning build <decision_output.json> [--out plan.json]
python -m planning variants <decision_output.json> [--weather forecast.json] [--out plan.json]"""

import argparse
import json
import sys
from pathlib import Path

from corpus.serving import load as load_records

from . import build_plan, build_variants, render_text, render_variants


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="planning")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="print the itinerary of a Decision Output")
    b.add_argument("decision_output", type=Path)
    b.add_argument("--out", type=Path, help="also write the full Plan Output as json")
    v = sub.add_parser("variants", help="print 2-3 checked variants with robustness and backups")
    v.add_argument("decision_output", type=Path)
    v.add_argument("--weather", type=Path, help='{"YYYY-MM-DD": {"rain_prob": 0..1, "source", "fetched_at"}}')
    v.add_argument("--out", type=Path, help="also write the full Plan Output as json")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    decision = json.loads(args.decision_output.read_text(encoding="utf-8"))
    if args.cmd == "build":
        plan = build_plan(decision, load_records())
        text = render_text(plan)
    else:
        weather = json.loads(args.weather.read_text(encoding="utf-8")) if args.weather else None
        plan = build_variants(decision, load_records(), weather=weather)
        text = render_variants(plan)
    if args.out:
        args.out.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(text)
    return 0 if plan["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
