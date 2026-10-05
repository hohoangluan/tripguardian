"""python -m corpus {login <source> | <source> <phase> | judge <phase> | review | aggregate | serving} --city <key>

Phases per source, each reading only earlier phases' files: tiktok search -> list -> filter -> crawl, then per Maps
place place_search -> place_filter -> place_crawl -> asr -> asr_check -> asr_alt -> (asr_check again) -> place_verify
-> comments_crawl (comments only for place_verify's "yes" videos); gmaps search -> filter -> counts -> list -> crawl
-> relevant -> qc -> observe; `all` runs them in order. judge dedup -> status -> audit (corpus.judge) runs after
observe and before aggregate.
"""

import argparse
import asyncio

from .crawl.common import browser
from .aggregate import run as aggregate_run
from .serving import run as serving_run
from . import judge
from .review import server as review_server
from .crawl.gmaps import counts as gmaps_counts, crawl as gmaps_crawl, filter as gmaps_filter, listing as gmaps_list, qc as gmaps_qc, relevant as gmaps_relevant, extremes as gmaps_extremes, search as gmaps_search
from .observe import gmaps as gmaps_observe
from .observe.gmaps import photos as gmaps_photo_observe
from .observe import tiktok as tiktok_observe
from .crawl.gmaps import photos as gmaps_photos
from .crawl.tiktok import (asr as tiktok_asr, asr_alt as tiktok_asr_alt, asr_check as tiktok_asr_check,
                           comments_crawl as tiktok_comments_crawl, crawl as tiktok_crawl,
                           filter as tiktok_filter, listing as tiktok_list, place_verify as tiktok_place_verify,
                           place_crawl as tiktok_place_crawl, place_filter as tiktok_place_filter,
                           place_search as tiktok_place_search, search as tiktok_search)

PHASES = {  # source -> phase -> (run, needs a browser)
    "tiktok": {"search": (tiktok_search.run, True), "list": (tiktok_list.run, False), "filter": (tiktok_filter.run, False),
               "crawl": (tiktok_crawl.run, True), "place_search": (tiktok_place_search.run, True),
               "place_filter": (tiktok_place_filter.run, False), "place_crawl": (tiktok_place_crawl.run, True),
               "asr": (tiktok_asr.run, False), "asr_check": (tiktok_asr_check.run, False),
               "asr_alt": (tiktok_asr_alt.run, False),
               "place_verify": (tiktok_place_verify.run, False),
               "comments_crawl": (tiktok_comments_crawl.run, True),
               "observe": (tiktok_observe.run, False)},
    "gmaps": {"search": (gmaps_search.run, True), "filter": (gmaps_filter.run, False), "counts": (gmaps_counts.run, True),
              "list": (gmaps_list.run, False),
              "crawl": (gmaps_crawl.run, True), "relevant": (gmaps_relevant.run, True), "extremes": (gmaps_extremes.run, True),
              "photos": (gmaps_photos.run, True), "qc": (gmaps_qc.run, False),
              "observe": (gmaps_observe.run, False), "photo_observe": (gmaps_photo_observe.run, False)},
}


SHARDABLE = {"place_search", "place_crawl", "comments_crawl"}  # tiktok phases that split their todo list by --shard for a second account


def run(source: str, phase: str, city: str, headed: bool, limit: int | None = None, wait_relevant: bool = False,
        profile: str | None = None, shard: tuple[int, int] | None = None) -> None:
    for p in PHASES[source] if phase == "all" else (phase,):
        fn, browser_phase = PHASES[source][p]
        if browser_phase and source == "tiktok":
            out = fn(city, headed, profile_name=profile, **({"shard": shard} if p in SHARDABLE else {}))
        elif browser_phase and p in ("photos", "extremes"):
            out = fn(city, headed, limit=limit)
        elif browser_phase:
            out = fn(city, headed)
        elif p == "observe" and source == "gmaps":
            out = fn(city, limit=limit, wait_relevant=wait_relevant)
        elif p in ("observe", "photo_observe"):
            out = fn(city, limit=limit)
        else:
            out = fn(city)
        if asyncio.iscoroutine(out):
            asyncio.run(out)


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m corpus")
    sub = ap.add_subparsers(dest="cmd", required=True)
    lp = sub.add_parser("login")
    lp.add_argument("source", choices=list(browser.LOGIN_URL))
    lp.add_argument("--profile", help="second browser profile name, e.g. tiktok2, for a second account")
    rp = sub.add_parser("review", help="local page for the items that need a person")
    rp.add_argument("--city", default="dalat")
    rp.add_argument("--port", type=int, default=8765)
    sub.add_parser("aggregate", help="every source's observations -> data/intel/places/").add_argument("--city", default="dalat")
    sub.add_parser("serving", help="intel -> data/serving/places.json for Place Decision").add_argument("--city", default="dalat")
    jp = sub.add_parser("judge", help="the Judge model labels claims, place status, duplicate places")
    jp.add_argument("phase", choices=[*judge.PHASES, "all"])
    jp.add_argument("--city", default="dalat")
    jp.add_argument("--limit", type=int, help="audit: only the first N calls")
    for source, phases in PHASES.items():
        sp = sub.add_parser(source)
        sp.add_argument("phase", choices=[*phases, "all"])
        sp.add_argument("--city", default="dalat")
        sp.add_argument("--headed", action="store_true")
        sp.add_argument("--limit", type=int, help="observe / photos: only the first N places")
        sp.add_argument("--wait-relevant", action="store_true",
                        help="gmaps observe: skip places whose relevant reviews are not crawled yet")
        if source == "tiktok":
            sp.add_argument("--profile", help="second browser profile name, e.g. tiktok2, for a second account "
                                               "(login it first: `python -m corpus login tiktok --profile tiktok2`)")
            sp.add_argument("--shard", help="i/n: only this process's 1/n share of the todo list, for "
                                             "place_search/place_crawl run in parallel under a second --profile")
    args = ap.parse_args()
    try:
        if args.cmd == "login":
            asyncio.run(browser.login(args.source, args.profile))
        elif args.cmd == "review":
            review_server.run(args.city, args.port)
        elif args.cmd == "aggregate":
            aggregate_run(args.city)
        elif args.cmd == "serving":
            serving_run(args.city)
        elif args.cmd == "judge":
            for name in ("dedup", "status", "audit") if args.phase == "all" else (args.phase,):
                fn = judge.PHASES[name]
                asyncio.run(fn(args.city, limit=args.limit) if name == "audit" else fn(args.city))
        else:
            shard = None
            if getattr(args, "shard", None):
                i, n = (int(x) for x in args.shard.split("/"))
                shard = (i, n)
            run(args.cmd, args.phase, args.city, args.headed, args.limit, args.wait_relevant,
                getattr(args, "profile", None), shard)
    except browser.LoginRequired as e:
        raise SystemExit(str(e))


if __name__ == "__main__":
    main()
