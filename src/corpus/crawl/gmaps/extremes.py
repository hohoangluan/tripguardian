"""Phase extremes: Maps' lowest- and highest-rated reviews of crawled places -> data/gmaps/places/<fid_dir>/reviews_extremes.json.

crawl.py keeps the newest reviews and relevant.py the "most relevant" ones; both skew towards the middle of the
rating range. The lowest-rated reviews name what goes wrong (queues, stairs, prices, closed gates), the highest what
makes a place worth it. Only places with enough reviews for the three lists to differ are opened. No age limit: the
age stays in published_text. Written once per place (a rerun skips it); observe merges it by review_id.
"""

import asyncio
import json
import re

from playwright.async_api import BrowserContext

from ..common.browser import LoginRequired, open_profile, pause
from ..common.files import data_dir, load_config, log_error, now, write_json
from ..common.throttle import Throttle
from .crawl import EXPAND_JS, LIST_END_JS, REVIEW_DIV, SORT_BUTTON, count, parse_reviews
from .page import ensure_login, more, open_page, text_only

FILE = "reviews_extremes.json"
ATTEMPTS = 2
MIN_REVIEWS = 30  # fewer: newest + relevant already cover (almost) every review
SORTS = {"highest": 2, "lowest": 3}  # position in Maps' sort menu: relevant, newest, highest, lowest (menu text is NFD)
_CHANGED_JS = """() => [...document.querySelectorAll('button[aria-haspopup="true"]')].some(
  b => b.getAttribute('aria-label') && b.getAttribute('aria-label').normalize('NFC') !== 'Phù hợp nhất'
       && /xếp hạng|mới nhất/i.test(b.getAttribute('aria-label').normalize('NFC')))"""


def stars(review: dict) -> int | None:
    m = re.match(r"(\d)", review.get("rating") or "")
    return int(m.group(1)) if m else None


def in_order(reviews: list[dict], position: int) -> bool:
    """Lowest sort = stars never go down, highest = never up (reviews without a star are skipped)."""
    xs = [x for x in map(stars, reviews) if x is not None]
    return xs == sorted(xs, reverse=position == SORTS["highest"])


def wanted(place: dict) -> bool:
    return (count(place.get("review_count")) or 0) >= MIN_REVIEWS


async def scrape_sorted(ctx: BrowserContext, url: str, position: int, n: int) -> tuple[list[dict], bool]:
    """First n reviews of one sort order; complete = stopped at n or at the list's end signal."""
    page = await ctx.new_page()
    try:
        await open_page(page, url, "h1.DUwDvf")
        tab = page.locator('button[role="tab"]:has-text("Bài đánh giá")')
        if not await tab.count():
            return [], True
        await tab.first.click()
        sort = page.locator(SORT_BUTTON)
        await sort.first.wait_for(timeout=15000)
        await page.wait_for_selector(REVIEW_DIV, timeout=20000)
        old = await page.locator(REVIEW_DIV).first.element_handle()  # the default ("relevant") list's first review
        await sort.first.click()
        await page.locator(f'[role="menuitemradio"][data-index="{position}"]').click()
        await page.wait_for_function(_CHANGED_JS, timeout=10000)  # raises when the sort did not apply
        # the sorted list replaces the old one: reading before that mixed ~10 default reviews in (8%, 2026-10-06)
        await page.wait_for_function("(e) => !e || !e.isConnected", arg=old, timeout=15000)
        await page.wait_for_selector(REVIEW_DIV, timeout=20000)
        pane = page.locator("div.m6QErb.DxyBCb").first
        complete, detached = False, 0
        while True:
            k = await page.locator(REVIEW_DIV).count()
            if k >= n or await page.evaluate(LIST_END_JS):
                complete = True
                break
            try:
                await page.locator(REVIEW_DIV).last.scroll_into_view_if_needed(timeout=5000)
            except Exception as e:  # the list re-renders while loading: the last review is replaced
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
        reviews = (await parse_reviews(page))[:n]
        if not in_order(reviews, position):
            raise RuntimeError("reviews not in the sort's star order: the old list was read")
        return reviews, complete
    finally:
        await page.close()


async def _place(ctx: BrowserContext, d, url: str, n: int, root, c: dict, throttle: Throttle) -> None:
    for attempt in range(1, ATTEMPTS + 1):
        async with throttle:
            try:
                doc: dict = {"fetched_at": now()}
                for name, position in SORTS.items():
                    reviews, complete = await scrape_sorted(ctx, url, position, n)
                    if not complete and attempt < ATTEMPTS:
                        raise RuntimeError(f"{name} reviews incomplete: the list stopped loading without its end signal")
                    doc[name] = {"complete": complete, "reviews": reviews}
                    await pause(*c.get("pause_s", (2.0, 5.0)))
                write_json(d / FILE, doc)
                throttle.success()
                return
            except LoginRequired:
                raise
            except Exception as e:
                if attempt < ATTEMPTS:
                    if type(e).__name__ == "TimeoutError":
                        throttle.blocked()
                    continue
                log_error(root, d.name, "extremes", e)
                return
            finally:
                await pause(*c.get("pause_s", (2.0, 5.0)))


async def run(city: str, headed: bool = False, profile=open_profile, limit: int | None = None) -> None:
    _, cfg = load_config(city)
    c, root = cfg["gmaps"], data_dir() / "gmaps"
    n = c.get("extreme_reviews_per_place", 30)
    todo = []
    for f in sorted((root / "places").glob("*/place.json")):
        if (f.parent / FILE).exists():
            continue
        place = json.loads(f.read_text(encoding="utf-8"))
        if wanted(place):
            todo.append((f.parent, place["url"]))
    todo = todo[:limit]
    print(f"extremes {city}: {len(todo)} places left")
    throttle = Throttle(root / "throttle.json", start=c.get("tabs_start", 1), hi=c.get("tabs", 1),
                        cooldown_s=c.get("cooldown_s", 60), max_cooldown_s=c.get("max_cooldown_s", 900))
    async with profile("gmaps", headed) as ctx:
        await text_only(ctx)
        await ensure_login(ctx)
        try:
            async with asyncio.TaskGroup() as tg:
                for d, url in todo:
                    tg.create_task(_place(ctx, d, url, n, root, c, throttle))
        except* LoginRequired as eg:
            raise eg.exceptions[0] from None
    done = sum((d / FILE).exists() for d, _ in todo)
    print(f"extremes {city}: {done}/{len(todo)} done, the rest in errors.jsonl")
