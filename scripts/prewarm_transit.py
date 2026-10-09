"""Fill the coach and flight caches once a day (cron), so a trip's transit question shows trips without waiting.

Flights: every airport in config/airports.yaml to its dest and back, for the next flight_days days; coaches: every
province in config/live.yaml vexere_regions to the city and back, for the next bus_days days (transit_prewarm). The
results live only in each module's own cache (data/live/flights/, data/live/vexere/); an entry fetched less than
REFRESH_S ago is kept, so a rerun after a crash resumes instead of starting over. A source that fails is logged and
skipped: nothing is written for it; FAIL_STREAK failures in a row (a captcha, a block) stop that source for the run.
Each source runs on its own pool of transit_prewarm.workers threads (a flight thread drives its own browser).

python scripts/prewarm_transit.py [--only flights|buses]
"""

import argparse
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

import live

ROOT = Path(__file__).resolve().parents[1]
REFRESH_S = 20 * 3600  # younger than this: kept (fresh from today's run); the cache's own TTL is 26 h
FAIL_STREAK = 8


def jobs(only: str | None, cfg: live.Settings, today) -> list[tuple]:
    plan = cfg.transit_prewarm or {}
    out = []
    if only in (None, "flights"):
        air = yaml.safe_load((ROOT / "config" / "airports.yaml").read_text(encoding="utf-8"))
        dest = air["dest"]["iata"]
        for k in range(1, plan.get("flight_days", 30) + 1):  # from tomorrow: today's flights have mostly left
            day = today + timedelta(days=k)
            for a in air["airports"]:
                out += [("flights", a["iata"], dest, day), ("flights", dest, a["iata"], day)]
    if only in (None, "buses"):
        for k in range(plan.get("bus_days", 14)):
            day = today + timedelta(days=k)
            for r in cfg.vexere_regions:
                out += [("buses", r["name"], "inbound", day), ("buses", r["name"], "outbound", day)]
    return out


def main(only: str | None) -> int:
    cfg = live.load_settings()
    today = (datetime.now(UTC) + timedelta(hours=cfg.tz_offset_h)).date()
    todo = jobs(only, cfg, today)
    plan = cfg.transit_prewarm or {}
    workers = plan.get("workers") or {}
    pause = plan.get("pause_s", 0)
    lock = threading.Lock()
    count = {"ok": 0, "failed": 0, "done": 0}
    streak: dict[str, int] = {}

    def run(job: tuple) -> None:
        kind, a, b, day = job
        with lock:
            if streak.get(kind, 0) >= FAIL_STREAK:
                return

        def fetch(network: bool):
            if kind == "flights":
                return live.flights(a, b, day, cfg, fetch=network, max_age_s=REFRESH_S)
            return live.buses(a, day, b, cfg, fetch=network, max_age_s=REFRESH_S)

        try:
            rows, note = fetch(False), " (cached)"
            if rows is None:
                rows, note = fetch(True), ""
                time.sleep(pause)
            line, failed = f"{len(rows)}{note}", False
        except live.Unavailable as e:
            line, failed = f"unavailable ({str(e).splitlines()[0]})", True
        with lock:
            count["done"] += 1
            count["failed" if failed else "ok"] += 1
            # a page that loaded with no flight that day is not a block
            streak[kind] = streak.get(kind, 0) + 1 if failed and "no flight could be read" not in line else 0
            print(f"[{count['done']}/{len(todo)}] {kind} {a} {b} {day}: {line}", flush=True)
            if streak[kind] == FAIL_STREAK:
                print(f"{kind}: {FAIL_STREAK} failures in a row, stopped for this run", flush=True)

    pools = [ThreadPoolExecutor(max_workers=workers.get(kind, 1), thread_name_prefix=kind) for kind in ("flights", "buses")]
    by_kind = dict(zip(("flights", "buses"), pools))
    for job in todo:
        by_kind[job[0]].submit(run, job)
    for pool in pools:
        pool.shutdown(wait=True)
    print(f"done: {count['ok']} ok, {count['failed']} unavailable"
          + "".join(f", {k} stopped" for k, n in streak.items() if n >= FAIL_STREAK), flush=True)
    return 0 if count["ok"] or not todo else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="prewarm_transit")
    parser.add_argument("--only", choices=["flights", "buses"])
    sys.exit(main(parser.parse_args().only))
