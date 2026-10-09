"""python -m db migrate | bootstrap: schema migrations and first-time roles for the project Postgres."""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from . import bootstrap, database_url, migrate


def main():
    parser = argparse.ArgumentParser(prog="python -m db")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="apply new files in migrations/ (DATABASE_URL)")
    sub.add_parser("bootstrap", help="create roles tg_app / tg_analytics and the database (POSTGRES_PASSWORD, port 5433)")
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    if args.command == "bootstrap":
        admin = f"postgresql://postgres:{os.environ['POSTGRES_PASSWORD']}@127.0.0.1:{os.environ.get('PG_PORT', '5433')}/postgres"
        bootstrap(admin, database_url(), database_url(readonly=True))
        print("roles and database ready")
    else:
        applied = migrate(database_url())
        print("applied: " + (", ".join(applied) if applied else "nothing new"))


if __name__ == "__main__":
    main()
