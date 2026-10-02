"""python -m planning build <decision_output.json> [--out plan.json]"""

import argparse
import json
import sys
from pathlib import Path

from corpus.serving import load as load_records

from . import build_plan, render_text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="planning")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="print the itinerary of a Decision Output")
    b.add_argument("decision_output", type=Path)
    b.add_argument("--out", type=Path, help="also write the full Plan Output as json")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    decision = json.loads(args.decision_output.read_text(encoding="utf-8"))
    plan = build_plan(decision, load_records())
    if args.out:
        args.out.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(render_text(plan))
    return 0 if plan["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
