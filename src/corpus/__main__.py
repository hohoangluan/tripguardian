"""python -m corpus {login <source> | tiktok | gmaps} --city <key> [--headed]"""

import argparse
import asyncio

from .crawl import browser, gmaps, tiktok

RUNNERS = {"tiktok": tiktok.run, "gmaps": gmaps.run}


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m corpus")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login").add_argument("source", choices=list(browser.LOGIN_URL))
    for name in RUNNERS:
        sp = sub.add_parser(name)
        sp.add_argument("--city", default="dalat")
        sp.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    try:
        if args.cmd == "login":
            asyncio.run(browser.login(args.source))
        else:
            asyncio.run(RUNNERS[args.cmd](args.city, args.headed))
    except browser.LoginRequired as e:
        raise SystemExit(str(e))

if __name__ == "__main__":
    main()
