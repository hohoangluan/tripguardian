"""python -m harness serve | import-files: one journey API for the online modules, journeys in Postgres."""

import argparse
import hashlib
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv

from accounts import Accounts, GoogleClient, Library
from agents import ChatSafety
from companion import Calendar, Companion
from corpus.serving import load as serving_records
from corpus.releases import Binding, bind
from corpus.retrieval import RetrievalEngine
from db import pool
from notify import Notify
from decision import Tools as DecisionTools, create_engine as decision_engine
from planning import Tools as PlanningTools, create_engine as planning_engine
from social import Social
from trip import Tools as TripTools, create_engine as trip_engine

from . import Harness, PgStore, import_files
from .events import EventLog
from .server import run


def app_version(root: Path) -> str:
    """Short git commit + hash of config/*.yaml, stamped on journeys and events so numbers compare across versions.
    A dirty working tree still gets one stamp per distinct config."""
    try:
        sha = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                             timeout=5).stdout.strip() or "nogit"
    except OSError:
        sha = "nogit"
    digest = hashlib.sha256()
    for path in sorted((root / "config").glob("*.yaml")):
        digest.update(path.name.encode() + path.read_bytes())
    return f"{sha}-{digest.hexdigest()[:8]}"


def main():
    parser = argparse.ArgumentParser(prog="python -m harness")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8769)
    imp = sub.add_parser("import-files", help="load data/harness/sessions + feedback.jsonl into Postgres (once)")
    imp.add_argument("sessions", type=Path)
    imp.add_argument("feedback", type=Path, nargs="?")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env")
    if args.command == "import-files":
        journeys, feedback = import_files(pool(), args.sessions, args.feedback)
        print(f"imported {journeys} journeys, {feedback} feedback rows")
        return
    data = Path(os.environ.get("DATA_DIR", "data"))
    if not data.is_absolute():
        data = root / data
    version = app_version(root)
    accounts = Accounts(pool(), GoogleClient.from_env(), data / "accounts" / "avatars", os.environ.get("TOKEN_ENC_KEY"))
    binding = bind(data)

    def tools_for_binding(pinned: Binding | None):
        # A saved legacy journey keeps the standalone artifacts; it never adopts today's active release.
        selected = pinned if pinned is not None else bind(data, legacy=True)
        retrieval = RetrievalEngine.open(data_root=data, binding=selected)
        tools = {"trip": TripTools(trip_engine(data, binding=selected, retrieval=retrieval)),
                 "decision": DecisionTools(decision_engine(data, binding=selected, retrieval=retrieval)),
                 "planning": PlanningTools(planning_engine(data, binding=selected, retrieval=retrieval))}
        if pinned is None:
            for tool in tools.values():
                tool.engine.corpus_binding = None
        return tools

    tools = tools_for_binding(binding)
    companion = Companion(pool(), tools["planning"].engine.records)
    harness = Harness(tools["trip"], tools["decision"], tools["planning"], PgStore(pool(), version), EventLog(pool(), version), companion,
        Calendar(pool(), accounts, companion.records, os.environ.get("APP_BASE_URL", "")),
        Notify(pool(), companion.records), safety=ChatSafety(), corpus_binding=binding, tools_for_binding=tools_for_binding)
    test_login = os.environ.get("TG_TEST_LOGIN") == "1"  # walk-throughs only; refused when APP_BASE_URL is https
    print(f"Journey harness: http://127.0.0.1:{args.port} (app {version})")
    run(harness, accounts, args.port, os.environ.get("APP_BASE_URL", ""), test_login, Social(pool()), Library(pool()))


if __name__ == "__main__":
    main()
