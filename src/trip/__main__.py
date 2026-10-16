"""python -m trip serve: the Trip Understanding API for the web (http://127.0.0.1:8766).
python -m trip drills: score the photo cards offline (config/trip.yaml drills) so the harness starts with them."""

import argparse
import os

from corpus.releases import resolve
from corpus.snapshot import shared
from dotenv import load_dotenv

from .agent import langchain_chat
from .api.engine import Engine
from .api.server import run
from .api.tools import senses
from .infrastructure.catalog import Catalog
from .infrastructure.clef import Judge
from .infrastructure.profile import ProfileStore
from .infrastructure.sessions import SessionStore
from .infrastructure.settings import ROOT, load


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m trip")
    sub = ap.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="run the API the web /app/understand screen talks to")
    serve.add_argument("--port", type=int, default=8766)
    sub.add_parser("drills", help="score every photo-card variant on the active corpus and save it")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    if args.cmd == "drills":
        from .api.tools import create_engine, write_drill_scores
        engine = create_engine(ROOT / os.environ.get("DATA_DIR", "data"))
        print(f"saved {write_drill_scores(engine)}")
        return
    cfg = load()
    data = ROOT / os.environ.get("DATA_DIR", "data")
    data_root = resolve(data)
    catalog = Catalog.from_snapshot(shared(data_root / "snapshot").region(), cfg.n_min)
    engine = Engine(catalog, cfg, SessionStore(data / "trip" / "sessions"),
                    chat=langchain_chat(cfg), judge=Judge(cfg),
                    profiles=ProfileStore(ROOT / cfg.patterns.dir, cfg.patterns) if cfg.patterns.enabled else None,
                    **senses(cfg, catalog, data_root=data_root))
    agent = os.environ.get("AGENT_MODEL", "policy fallback")
    print(f"Trip Understanding: http://127.0.0.1:{args.port} ({len(catalog.places)} places, model {agent})")
    run(engine, args.port)


if __name__ == "__main__":
    main()
