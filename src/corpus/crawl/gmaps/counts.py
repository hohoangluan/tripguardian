"""Phase 3, counts: the review count of kept places whose search cards showed a rating but no "(124)".

Signed-out Maps ("limited view") sometimes drops the count from result cards and never shows it on the place page, so
list.py would take a 4.4 with thousands of reviews for a place without reviews. This phase opens each such place
(filter.py kept it, no search sighting has a count) in the signed-in profile and reads the count from the place page.

Writes only data/gmaps/counts/<city>.json: {at, items: {fid: {rating, reviews, at}}}; places already there are not
opened again. list.py takes these counts over the search cards'.
"""

import asyncio
import json

from ..common.browser import LoginRequired, open_profile, pause
from ..common.files import data_dir, load_config, log_error, now, write_json
from .crawl import count, parse_place
from .filter import candidates
from .listing import kept_fids
from .page import ensure_login, open_page

TABS = 3


def missing(search_dir, area, kept: set[str]) -> list[dict]:
    """Kept places with a rating on some card but a review count on none."""
    rows: dict[str, dict] = {}
    for f in sorted(search_dir.glob("*.jsonl")) if search_dir.exists() else []:
        for line in f.read_text(encoding="utf-8").splitlines():
            for r in json.loads(line)["items"]:
                b = rows.setdefault(r["fid"], {**r, "rated": False, "counted": False})
                b["rated"] |= r.get("rating") is not None
                b["counted"] |= r.get("reviews") is not None
    wanted = {r["fid"] for r in candidates(search_dir, area)} & kept
    return [r for fid, r in rows.items() if fid in wanted and r["rated"] and not r["counted"]]


async def run(city: str, headed: bool = False, profile=open_profile) -> dict:
    _, cfg = load_config(city)
    c, root = cfg["gmaps"], data_dir() / "gmaps"
    if not (root / "filter" / "summary.json").exists():
        raise SystemExit(f"no {root / 'filter'}; run `python -m corpus gmaps filter --city {city}` first")
    target = root / "counts" / f"{city}.json"
    done = json.loads(target.read_text(encoding="utf-8"))["items"] if target.exists() else {}
    todo = [r for r in missing(root / "search" / city, cfg.get("area"), kept_fids(root / "filter"))
            if r["fid"] not in done]
    print(f"counts {city}: {len(todo)} places to open")
    sem = asyncio.Semaphore(TABS)

    async def one(ctx, row):
        async with sem:
            page = await ctx.new_page()
            try:
                await open_page(page, row["url"], "h1.DUwDvf")
                await page.wait_for_timeout(1500)  # rating block renders after the title
                place = await parse_place(page)
                rating, reviews = place.get("rating"), count(place.get("review_count"))
                if reviews is None:  # signed-out view (session ended, cookie kept) shows no count: open again later
                    raise LoginRequired("gmaps")
                done[row["fid"]] = {"rating": float(rating.split()[0].replace(",", ".")) if rating else None,
                                    "reviews": reviews, "at": now()}
            except LoginRequired:
                raise
            except Exception as e:
                log_error(root, row["fid"], "counts", e)
            finally:
                await page.close()
                await pause(*c.get("pause_s", (2.0, 5.0)))

    async with profile("gmaps", headed) as ctx:
        await ensure_login(ctx)
        try:
            async with asyncio.TaskGroup() as tg:  # one LoginRequired stops all
                for row in todo:
                    tg.create_task(one(ctx, row))
        except* LoginRequired as eg:
            raise eg.exceptions[0] from None
        finally:
            write_json(target, {"at": now(), "items": done})
    stats = {"opened": len(todo), "counted": sum(done[r["fid"]]["reviews"] is not None for r in todo if r["fid"] in done)}
    print(f"counts {city}: {stats}")
    return stats
