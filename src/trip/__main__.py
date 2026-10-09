"""python -m trip serve: the Trip Understanding API for the web (http://127.0.0.1:8766)."""

import argparse
import os

from dotenv import load_dotenv

from .agent import openai_chat
from .api.engine import Engine
from .api.server import run
from .infrastructure.catalog import Catalog
from .infrastructure.clef import Judge, route
from .infrastructure.profile import ProfileStore
from .infrastructure.sessions import SessionStore
from .infrastructure.settings import ROOT, load


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m trip")
    sub = ap.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="run the API the web /app/understand screen talks to")
    serve.add_argument("--port", type=int, default=8766)
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    cfg = load()
    data = ROOT / os.environ.get("DATA_DIR", "data")
    catalog = Catalog.load(data, cfg.n_min)
    engine = Engine(catalog, cfg, SessionStore(data / "trip" / "sessions"),
                    chat=openai_chat(cfg), route=lambda text, card: route(text, cfg, card),
                    judge=Judge(cfg),
                    profiles=ProfileStore(ROOT / cfg.patterns.dir, cfg.patterns) if cfg.patterns.enabled else None)
    agent = os.environ.get("AGENT_MODEL", "policy fallback")
    print(f"Trip Understanding: http://127.0.0.1:{args.port} ({len(catalog.places)} places, model {agent})")
    run(engine, args.port)


if __name__ == "__main__":
    main()
