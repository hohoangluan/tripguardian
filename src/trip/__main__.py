"""python -m trip serve: the Trip Understanding API for the web (http://127.0.0.1:8766)."""

import argparse
import os
import sys

from dotenv import load_dotenv

from .agent import run_agent
from .catalog import Catalog
from .engine import Engine
from .server import run
from .sessions import SessionStore
from .settings import ROOT, load


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m trip")
    sub = ap.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="run the API the web /app/understand screen talks to")
    serve.add_argument("--port", type=int, default=8766)
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    missing = [k for k in ("AGENT_API_KEY", "AGENT_BASE_URL", "AGENT_MODEL") if not os.environ.get(k)]
    if missing:
        sys.exit(f"missing {', '.join(missing)} in .env (see .env.example, docs/LLM_PROVIDER.md)")
    cfg = load()
    data = ROOT / os.environ.get("DATA_DIR", "data")
    catalog = Catalog.load(data, cfg.n_min)
    engine = Engine(catalog, cfg, SessionStore(data / "trip" / "sessions"),
                    agent=lambda fields, on_say: run_agent(fields, on_say, cfg))
    print(f"Trip Understanding: http://127.0.0.1:{args.port} ({len(catalog.places)} places, model {os.environ['AGENT_MODEL']})")
    run(engine, args.port)


if __name__ == "__main__":
    main()
