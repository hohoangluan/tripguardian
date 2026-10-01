"""python -m corpus {login <source> | <source> <phase> | review | aggregate} --city <key> [--headed]

Phases per source, each reading only earlier phases' files: tiktok search -> list -> filter -> crawl, then per Maps
place place_search -> place_filter -> place_crawl -> asr -> asr_check -> asr_alt -> (asr_check again) -> place_verify; gmaps search ->
filter -> counts -> list -> crawl -> relevant -> qc -> observe; `all` runs them in order.
"""

import argparse
import asyncio

from .crawl.common import browser
from .aggregate import run as aggregate_run
from .review import server as review_server
from .crawl.gmaps import counts as gmaps_counts, crawl as gmaps_crawl, filter as gmaps_filter, listing as gmaps_list, qc as gmaps_qc, relevant as gmaps_relevant, search as gmaps_search
from .observe import gmaps as gmaps_observe
from .crawl.tiktok import (asr as tiktok_asr, asr_alt as tiktok_asr_alt, asr_check as tiktok_asr_check, crawl as tiktok_crawl,
                           filter as tiktok_filter, listing as tiktok_list, place_verify as tiktok_place_verify,
                           place_crawl as tiktok_place_crawl, place_filter as tiktok_place_filter,
                           place_search as tiktok_place_search, search as tiktok_search)

PHASES = {  # source -> phase -> (run, needs a browser)
    "tiktok": {"search": (tiktok_search.run, True), "list": (tiktok_list.run, False), "filter": (tiktok_filter.run, False),
               "crawl": (tiktok_crawl.run, True), "place_search": (tiktok_place_search.run, True),
               "place_filter": (tiktok_place_filter.run, False), "place_crawl": (tiktok_place_crawl.run, True),
               "asr": (tiktok_asr.run, False), "asr_check": (tiktok_asr_check.run, False),
               "asr_alt": (tiktok_asr_alt.run, False),
               "place_verify": (tiktok_place_verify.run, False)},
    "gmaps": {"search": (gmaps_search.run, True), "filter": (gmaps_filter.run, False), "counts": (gmaps_counts.run, True),
              "list": (gmaps_list.run, False),
              "crawl": (gmaps_crawl.run, True), "relevant": (gmaps_relevant.run, True), "qc": (gmaps_qc.run, False),
              "observe": (gmaps_observe.run, False)},
}


def run(source: str, phase: str, city: str, headed: bool, limit: int | None = None) -> None:
    for p in PHASES[source] if phase == "all" else (phase,):
        fn, browser_phase = PHASES[source][p]
        out = fn(city, headed) if browser_phase else fn(city, limit=limit) if p == "observe" else fn(city)
        if asyncio.iscoroutine(out):
            asyncio.run(out)


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m corpus")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login").add_argument("source", choices=list(browser.LOGIN_URL))
    rp = sub.add_parser("review", help="local page for the items that need a person")
    rp.add_argument("--city", default="dalat")
    rp.add_argument("--port", type=int, default=8765)
    sub.add_parser("aggregate", help="every source's observations -> data/intel/places/").add_argument("--city", default="dalat")
    for source, phases in PHASES.items():
        sp = sub.add_parser(source)
        sp.add_argument("phase", choices=[*phases, "all"])
        sp.add_argument("--city", default="dalat")
        sp.add_argument("--headed", action="store_true")
        sp.add_argument("--limit", type=int, help="observe: only the first N places")
    args = ap.parse_args()
    try:
        if args.cmd == "login":
            asyncio.run(browser.login(args.source))
        elif args.cmd == "review":
            review_server.run(args.city, args.port)
        elif args.cmd == "aggregate":
            aggregate_run(args.city)
        else:
            run(args.cmd, args.phase, args.city, args.headed, args.limit)
    except browser.LoginRequired as e:
        raise SystemExit(str(e))


if __name__ == "__main__":
    main()
