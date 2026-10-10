"""python -m bench generate | run (docs/P2_TRIP_UNDERSTANDING.md §16)."""

import argparse
import os
import sys
from itertools import takewhile
from pathlib import Path

LIVE = "--live" in sys.argv
if not LIVE:
    for k in ("AGENT_API_KEY", "AGENT_BASE_URL", "AGENT_MODEL"):
        os.environ[k] = ""            # engines read these at creation / call time: empty = no model

from . import generate, load, quotas, run  # noqa: E402
from .hidden import TRIPS, save  # noqa: E402

OFFLINE_STYLES = ("tapper", "baseline", "brief")
LIVE_STYLES = ("chatter", "brief")


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m bench")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--seed", type=int, default=1)
    g.add_argument("--briefs", action="store_true", help="write a brief per trip with USER_SIM (needs --live)")
    g.add_argument("--live", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--styles", default="")
    r.add_argument("--only", default="")
    r.add_argument("--live", action="store_true")
    r.add_argument("--out", default="", help="write into this directory (default data/bench/<timestamp>)")
    r.add_argument("--resume", action="store_true", help="keep the rows already in --out, run only the missing ones")
    args = ap.parse_args()
    if args.cmd == "generate":
        if args.briefs:
            if not args.live:
                sys.exit("--briefs calls the USER_SIM model: add --live")
            from .live import brief, require
            require()
            trips = load()
            with TRIPS.open(encoding="utf-8") as f:
                header = "".join(takewhile(lambda line: line.startswith("#"), f))
            for i, t in enumerate(trips):
                if t.brief:
                    continue                                 # written by an earlier, interrupted run
                trips[i] = t.model_copy(update={"brief": brief(t)})
                save(trips, header=header)                   # after every brief: a failed call loses only one
                print(f"brief {t.id} ({i + 1}/{len(trips)})", flush=True)
            print(f"briefs: {sum(bool(t.brief) for t in trips)}/{len(trips)} trips")
            return 0
        trips = generate(args.seed)
        print(f"{len(trips)} trips -> config/bench_trips.yaml; quotas {quotas(trips)}")
        return 0
    if args.live:
        from .live import require
        require()
    allowed = LIVE_STYLES if args.live else OFFLINE_STYLES
    styles = [s for s in args.styles.split(",") if s] or list(allowed)
    bad = [s for s in styles if s not in allowed]
    if bad:
        sys.exit(f"{'live' if args.live else 'offline'} styles are {', '.join(allowed)}; not {', '.join(bad)}")
    only = {x for x in args.only.split(",") if x}
    trips = [t for t in load() if not only or t.id in only]
    out, _, _, summ = run(trips, styles, "live" if args.live else "offline", Path(args.out) if args.out else None,
                          args.resume)
    cols = ("style", "n", "skipped", "accuracy", "mean_turns_to_suggestion", "total_fields_invented",
            "total_safety_missed", "total_safety_unreachable", "total_hard_violations", "total_fields_unreachable",
            "mean_fields_inferred", "reached_plan_rate", "mean_unknown_hours_share")
    print("  ".join(cols))
    for row in summ:
        print("  ".join(str(row.get(c, "")) for c in cols))
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
