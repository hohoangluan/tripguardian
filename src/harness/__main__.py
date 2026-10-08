"""python -m harness serve: one journey API for the online modules."""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from decision import Tools as DecisionTools, create_engine as decision_engine
from planning import Tools as PlanningTools, create_engine as planning_engine
from trip import Tools as TripTools, create_engine as trip_engine

from . import Harness, Store
from .server import run


def main():
    parser = argparse.ArgumentParser(prog="python -m harness")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8769)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env")
    data = Path(os.environ.get("DATA_DIR", "data"))
    if not data.is_absolute():
        data = root / data
    harness = Harness(TripTools(trip_engine(data)), DecisionTools(decision_engine(data)),
        PlanningTools(planning_engine(data)), Store(data / "harness" / "sessions"))
    print(f"Journey harness: http://127.0.0.1:{args.port}")
    run(harness, args.port)


if __name__ == "__main__":
    main()
