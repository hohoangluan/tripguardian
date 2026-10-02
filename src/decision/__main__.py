"""python -m decision serve (http://127.0.0.1:8767) | python -m decision evaluate (data/decision/eval.json)."""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .agent import run_agent
from .engine import Engine
from .pipeline import Data
from .server import run
from .session import Store
from .settings import ROOT, default


def data_root() -> Path:
    d = Path(os.environ.get("DATA_DIR", "data"))
    return d if d.is_absolute() else ROOT / d


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m decision")
    sub = ap.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="run the API the web shortlist / feasibility screens talk to")
    serve.add_argument("--port", type=int, default=8767)
    sub.add_parser("evaluate", help="offline Place Decision check on the serving records")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    cfg = default()
    if args.cmd == "evaluate":
        from .evaluate import run as evaluate
        evaluate()
        return
    try:
        data = Data.load()
    except FileNotFoundError:
        sys.exit("no data/serving/places.json: run python -m corpus serving first")
    missing = [k for k in ("AGENT_API_KEY", "AGENT_BASE_URL", "AGENT_MODEL") if not os.environ.get(k)]
    agent = None
    if missing:
        print(f"warning: {', '.join(missing)} missing in .env: typed messages use the keyword fallback", file=sys.stderr)
    else:
        agent = lambda fields, on_say: run_agent(fields, on_say, cfg)  # noqa: E731
    engine = Engine(data, cfg, Store(data_root() / "decision" / "sessions"), agent)
    print(f"Place Decision: http://127.0.0.1:{args.port} ({len(data.records)} places, "
          f"agent {os.environ.get('AGENT_MODEL') if agent else 'off'})")
    run(engine, args.port)


if __name__ == "__main__":
    main()
