"""python -m corpus {login <source> | <source> <phase> | review} --city <key> [--headed]

Phases per source, each reading only earlier phases' files: tiktok search -> list -> filter -> crawl; gmaps search ->
filter -> counts -> list -> crawl -> qc; `all` runs them in order.
"""

import argparse
import asyncio

from .crawl.common import browser
from .review import server as review_server
from .crawl.gmaps import counts as gmaps_counts, crawl as gmaps_crawl, filter as gmaps_filter, listing as gmaps_list, qc as gmaps_qc, search as gmaps_search
from .crawl.tiktok import crawl as tiktok_crawl, filter as tiktok_filter, listing as tiktok_list, search as tiktok_search

PHASES = {  # source -> phase -> (run, needs a browser)
    "tiktok": {"search": (tiktok_search.run, True), "list": (tiktok_list.run, False), "filter": (tiktok_filter.run, False),
               "crawl": (tiktok_crawl.run, True)},
    "gmaps": {"search": (gmaps_search.run, True), "filter": (gmaps_filter.run, False), "counts": (gmaps_counts.run, True),
              "list": (gmaps_list.run, False),
              "crawl": (gmaps_crawl.run, True), "qc": (gmaps_qc.run, False)},
}


def run(source: str, phase: str, city: str, headed: bool) -> None:
    for p in PHASES[source] if phase == "all" else (phase,):
        fn, browser_phase = PHASES[source][p]
        out = fn(city, headed) if browser_phase else fn(city)
        if asyncio.iscoroutine(out):
            asyncio.run(out)


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m corpus")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login").add_argument("source", choices=list(browser.LOGIN_URL))
    rp = sub.add_parser("review", help="local page for the items that need a person")
    rp.add_argument("--city", default="dalat")
    rp.add_argument("--port", type=int, default=8765)
    for source, phases in PHASES.items():
        sp = sub.add_parser(source)
        sp.add_argument("phase", choices=[*phases, "all"])
        sp.add_argument("--city", default="dalat")
        sp.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    try:
        if args.cmd == "login":
            asyncio.run(browser.login(args.source))
        elif args.cmd == "review":
            review_server.run(args.city, args.port)
        else:
            run(args.cmd, args.phase, args.city, args.headed)
    except browser.LoginRequired as e:
        raise SystemExit(str(e))


if __name__ == "__main__":
    main()
