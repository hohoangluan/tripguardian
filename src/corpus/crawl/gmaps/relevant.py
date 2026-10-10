"""Phase relevant: Maps' "most relevant" reviews of crawled places -> data/gmaps/places/<fid_dir>/reviews_relevant.json.

crawl.py keeps the newest reviews under the age limit; Maps' default order puts long, detailed reviews first, which
name stairs, walks, roofs and visit length far more often. Only places that show more reviews than crawl kept are
opened (otherwise the relevant ones are already there). No age limit: the age stays in published_text, so freshness
and trend see it. Written once per place (a rerun skips it); observe merges it with reviews.json by review_id.
"""

import asyncio
import json

from playwright.async_api import BrowserContext

from ..common.browser import LoginRequired, open_profile, pause
from ..common.files import data_dir, load_config, log_error, now, write_json
from ..common.throttle import Throttle
from .gate import GateThrottle
from .crawl import EXPAND_JS, LIST_END_JS, REVIEW_DIV, count, parse_reviews
from .page import CaptchaBlocked, ensure_login, more, open_page, text_only

FILE = "reviews_relevant.json"
ATTEMPTS = 2


def wanted(place: dict, n_kept: int) -> bool:
    total = count(place.get("review_count"))
    return bool(total) and total > n_kept


async def scrape_relevant(ctx: BrowserContext, url: str, n: int) -> tuple[list[dict], bool]:
    """First n reviews in Maps' default order; complete = stopped at n or at the list's end signal."""
    page = await ctx.new_page()
    try:
        await open_page(page, url, "h1.DUwDvf")
        tab = page.locator('button[role="tab"]:has-text("Bài đánh giá")')
        if not await tab.count():
            return [], True
        await tab.first.click()
        await page.wait_for_selector(REVIEW_DIV, timeout=20000)  # default order: no sorting
        pane = page.locator("div.m6QErb.DxyBCb").first
        complete, detached = False, 0
        while True:
            k = await page.locator(REVIEW_DIV).count()
            if k >= n or await page.evaluate(LIST_END_JS):
                complete = True
                break
            try:
                await page.locator(REVIEW_DIV).last.scroll_into_view_if_needed(timeout=5000)
            except Exception as e:  # the default-order list re-renders while loading: the last review is replaced
                detached += 1
                if "not attached" not in str(e) or detached > 3:
                    raise
                await page.wait_for_timeout(1000)
                continue
            await pane.evaluate("e => e.scrollTo(0, e.scrollHeight)")
            if not await more(page, REVIEW_DIV, k, timeout=15000):
                complete = await page.evaluate(LIST_END_JS)
                break
        for _ in range(3):  # "Xem thêm", best effort as in crawl.py
            if not await page.evaluate(EXPAND_JS):
                break
            await page.wait_for_timeout(500)
        return (await parse_reviews(page))[:n], complete
    finally:
        await page.close()


async def _place(ctx: BrowserContext, d, url: str, n: int, root, c: dict, throttle: Throttle) -> None:
    for attempt in range(1, ATTEMPTS + 1):
        async with throttle:
            try:
                reviews, complete = await scrape_relevant(ctx, url, n)
                if not complete and attempt < ATTEMPTS:
                    raise RuntimeError("relevant reviews incomplete: the list stopped loading without its end signal")
                write_json(d / FILE, {"fetched_at": now(), "complete": complete, "reviews": reviews})
                throttle.success()
                return
            except LoginRequired:
                raise
            except Exception as e:
                if attempt < ATTEMPTS:
                    if type(e).__name__ == "TimeoutError" or isinstance(e, CaptchaBlocked):
                        throttle.blocked()
                    continue
                log_error(root, d.name, "relevant", e)
                return
            finally:
                await pause(*c.get("pause_s", (2.0, 5.0)))


async def run(city: str, headed: bool = False, profile=open_profile, shard: tuple[int, int] | None = None,
              profile_name: str | None = None) -> None:
    _, cfg = load_config(city)
    c, root = cfg["gmaps"], data_dir() / "gmaps"
    n = c.get("relevant_reviews_per_place", 50)
    todo = []
    for f in sorted((root / "places").glob("*/place.json")):
        if (f.parent / FILE).exists():
            continue
        place = json.loads(f.read_text(encoding="utf-8"))
        kept = json.loads((f.parent / "reviews.json").read_text(encoding="utf-8"))
        if wanted(place, len(kept)):
            todo.append((f.parent, place["url"]))
    if shard:  # one process per shard, each with its own browser (one Python process caps ~8 tabs)
        todo = todo[shard[0]::shard[1]]
    print(f"relevant {city}: {len(todo)} places left" + (f" (shard {shard[0]}/{shard[1]})" if shard else ""))
    throttle = GateThrottle(root / "throttle.json", start=c.get("tabs_start", 1), hi=c.get("tabs", 1),
                        cooldown_s=c.get("cooldown_s", 60), max_cooldown_s=c.get("max_cooldown_s", 900))
    async with profile(profile_name or "gmaps", headed) as ctx:
        await text_only(ctx)  # text and aria-labels only: a drawn map kept ~1 core busy per tab (2026-10-07)
        await ensure_login(ctx)
        try:
            async with asyncio.TaskGroup() as tg:
                for d, url in todo:
                    tg.create_task(_place(ctx, d, url, n, root, c, throttle))
        except* LoginRequired as eg:
            raise eg.exceptions[0] from None
    done = sum((d / FILE).exists() for d, _ in todo)
    print(f"relevant {city}: {done}/{len(todo)} done, the rest in errors.jsonl")
