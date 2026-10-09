"""python -m analytics serve [--port 8770]: Admin numbers on 127.0.0.1 with the read-only role (DATABASE_URL_READONLY).
python -m analytics cluster: this week's groups of what users wrote (Extractor role; cron once a week)."""

import argparse
from pathlib import Path

from dotenv import load_dotenv

from db import database_url, pool

from .server import run


def main():
    parser = argparse.ArgumentParser(prog="python -m analytics")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8770)
    sub.add_parser("cluster")
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    if args.command == "cluster":
        from .cluster import run as cluster
        print(f"stored {cluster(pool(database_url()))} groups")
        return
    print(f"Analytics (private): http://127.0.0.1:{args.port}")
    run(pool(database_url(readonly=True)), args.port)


if __name__ == "__main__":
    main()
