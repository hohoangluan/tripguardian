"""python -m planning build <decision_output.json> [--out plan.json]
python -m planning variants <decision_output.json> [--weather forecast.json] [--out plan.json]
python -m planning lodging <decision_output.json> [--weather forecast.json] [--out plan.json]"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

import live
from corpus.serving import load as load_records

from . import (Engine, build_lodging_variants, build_plan, build_variants, render_lodging_variants, render_text,
              render_variants, run_server)
from .agent import run_agent
from .conditions import fetch_live
from .session import Store
from .settings import ROOT


def data_root() -> Path:
    d = Path(os.environ.get("DATA_DIR", "data"))
    return d if d.is_absolute() else ROOT / d


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
    l = sub.add_parser("lodging", help="print 2-3 checked variants with lodging competing as each day's anchor")
    l.add_argument("decision_output", type=Path)
    l.add_argument("--weather", type=Path, help='{"YYYY-MM-DD": {"rain_prob": 0..1, "source", "fetched_at"}}')
    l.add_argument("--out", type=Path, help="also write the full Plan Output as json")
    sv = sub.add_parser("serve", help="run the HTTP + SSE server")
    sv.add_argument("--port", type=int, default=8768)
    sub.add_parser("evaluate", help="offline Planning check: 30 hidden trips through Decision and Planning")
    args = ap.parse_args(argv)
    if args.cmd == "evaluate":
        from .evaluate import run as run_evaluate
        run_evaluate()
        return 0
    if args.cmd == "serve":
        load_dotenv(ROOT / ".env")
        store = Store(data_root() / "planning" / "sessions")
        missing = [k for k in ("AGENT_API_KEY", "AGENT_BASE_URL", "AGENT_MODEL") if not os.environ.get(k)]
        agent = None
        if missing:
            print(f"warning: {', '.join(missing)} missing in .env: typed turns use the keyword fallback",
                  file=sys.stderr)
        else:
            from .settings import load as load_settings
            agent = lambda fields, on_say: run_agent(fields, on_say, load_settings())  # noqa: E731
        engine = Engine(load_records(), store=store, agent=agent, conditions_fn=fetch_live(live.load_settings()))
        print(f"Planning: http://127.0.0.1:{args.port} (agent {os.environ.get('AGENT_MODEL') if agent else 'off'})")
        run_server(engine, port=args.port)
        return 0
    sys.stdout.reconfigure(encoding="utf-8")
    decision = json.loads(args.decision_output.read_text(encoding="utf-8"))
    if args.cmd == "build":
        plan = build_plan(decision, load_records())
        text = render_text(plan)
    elif args.cmd == "variants":
        weather = json.loads(args.weather.read_text(encoding="utf-8")) if args.weather else None
        plan = build_variants(decision, load_records(), weather=weather)
        text = render_variants(plan)
    else:
        weather = json.loads(args.weather.read_text(encoding="utf-8")) if args.weather else None
        plan = build_lodging_variants(decision, load_records(), weather=weather)
        text = render_lodging_variants(plan)
    if args.out:
        args.out.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(text)
    return 0 if plan["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
