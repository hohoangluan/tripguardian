"""Google Maps: search places per category, keep each place's details and reviews under data/gmaps/."""

import asyncio
import re
from urllib.parse import quote

from playwright.async_api import BrowserContext, Page

from .browser import LoginRequired, is_captcha, open_profile, pause
from .files import (append_jsonl, author_hash, data_dir, load_config, log_error, now, safe_name, slug,
                    write_json)
from .throttle import Throttle

SEARCH_URL = "https://www.google.com/maps/search/{}?hl=vi"
_FID = re.compile(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)")
_LATLNG = re.compile(r"!3d(-?[\d.]+)!4d(-?[\d.]+)")
HOURS_BUTTON = '[role="button"][jsaction*="openhours"][jsaction*="dropdown"]'
SORT_BUTTON = 'button[aria-haspopup="true"][aria-label="Phù hợp nhất"]'  # label = current review order
NEWEST_ITEM = '[role="menuitemradio"][data-index="1"]'  # "Mới nhất"; menu text is NFD, so match by position

FEED_A = "a.hfpxzc"
REVIEW_DIV = "div.jftiEf[data-review-id]"
FEED_JS = "() => [...document.querySelectorAll('a.hfpxzc')].map(a => [a.getAttribute('aria-label'), a.href])"

PLACE_JS = r"""() => {
  const q = s => document.querySelector(s), t = e => e ? e.innerText.trim() : null;
  const labels = [...document.querySelectorAll('[aria-label]')].map(e => e.getAttribute('aria-label').trim());
  return {
    name: t(q('h1.DUwDvf')), category: t(q('button[jsaction*="category"]')),
    address: t(q('[data-item-id="address"]')), website: q('a[data-item-id="authority"]')?.href ?? null,
    phone: q('[data-item-id^="phone:tel:"]')?.dataset.itemId.slice(10) ?? null,
    description: t(q('.PYvSYb')),
    hours: [...document.querySelectorAll('table.eK4R0e tr')].map(r => r.innerText.replace(/\s+/g, ' ').trim()).filter(Boolean),
    status: t(q('.ZDu9vd span')),
    attributes: labels.filter(a => /^(Có|Không có|Phù hợp|Lối vào|Nhà vệ sinh|Chỗ đậu xe)/.test(a)),
    popular_times: [...document.querySelectorAll('div.C7xf8b > div')].map(day =>  // 7 days, Sunday first
      [...day.querySelectorAll('[role="img"][aria-label]')].map(e => e.getAttribute('aria-label').trim())),
    rating: labels.find(a => /^[\d,]+ sao$/.test(a)) ?? null,
    review_count: labels.find(a => /^[\d.]+ bài đánh giá$/.test(a)) ?? null,
  };
}"""

REVIEWS_JS = r"""() => [...document.querySelectorAll('div.jftiEf[data-review-id]')].map(r => ({
  review_id: r.dataset.reviewId,
  author: r.querySelector('[data-href*="/contrib/"]')?.dataset.href.match(/contrib\/(\d+)/)?.[1] ?? '',
  rating: r.querySelector('[role="img"][aria-label*="sao"]')?.getAttribute('aria-label').trim() ?? null,
  text: r.querySelector('.wiI7pd')?.innerText.trim() ?? '',
  published_text: r.querySelector('.rsqaWe')?.innerText.trim() ?? null,
}))"""


def _place_row(name: str, url: str) -> dict | None:
    fid, ll = _FID.search(url), _LATLNG.search(url)
    if not fid:
        return None
    return {"fid": fid.group(1), "name": name, "url": url,
            "lat": float(ll.group(1)) if ll else None, "lng": float(ll.group(2)) if ll else None}


async def parse_feed(page: Page, url: str | None = None) -> list[dict]:
    rows = [_place_row(n, h) for n, h in await page.evaluate(FEED_JS)]
    if not rows:  # exact match: Maps opened the place page itself
        name = await page.evaluate("() => document.querySelector('h1.DUwDvf')?.innerText.trim() ?? ''")
        rows = [_place_row(name, url or page.url)] if name else []
    return list({r["fid"]: r for r in rows if r}.values())


async def parse_place(page: Page) -> dict:
    return await page.evaluate(PLACE_JS)


async def parse_reviews(page: Page) -> list[dict]:
    rows = []
    for r in await page.evaluate(REVIEWS_JS):
        r["author_hash"] = author_hash(r.pop("author"))
        rows.append(r)
    return list({r["review_id"]: r for r in rows}.values())


async def ensure_login(ctx: BrowserContext) -> None:
    # Logged-out Maps is "limited view": no reviews tab, no popular times.
    if not any(c["name"] == "SID" for c in await ctx.cookies("https://www.google.com")):
        raise LoginRequired("gmaps")


async def _more(page: Page, selector: str, n: int, timeout: int = 4000) -> bool:
    """Wait for more than n matches after a scroll; False when nothing new loads (end of list)."""
    try:
        await page.wait_for_function("([s, n]) => document.querySelectorAll(s).length > n",
                                     arg=[selector, n], timeout=timeout)
        return True
    except Exception:
        return False


async def _open(page: Page, url: str, selector: str) -> None:
    await page.goto(url, wait_until="domcontentloaded")
    try:
        await page.wait_for_selector(selector, timeout=20000)
    except Exception:
        if await is_captcha(page) or "sorry" in page.url:
            raise LoginRequired("gmaps")
        raise


async def search(ctx: BrowserContext, query: str, limit: int) -> list[dict]:
    page = await ctx.new_page()
    try:
        await _open(page, SEARCH_URL.format(quote(query)), 'div[role="feed"], h1.DUwDvf')
        feed = page.locator('div[role="feed"]')
        for _ in range(limit // 7 + 3):
            n = len(await page.evaluate(FEED_JS))
            if not await feed.count() or n >= limit:
                break
            if await page.get_by_text("Bạn đã xem hết danh sách này").count():
                break
            await feed.evaluate("e => e.scrollBy(0, 5000)")
            await _more(page, FEED_A, n)
        return (await parse_feed(page))[:limit]
    finally:
        await page.close()


async def scrape_place(ctx: BrowserContext, url: str, max_reviews: int) -> tuple[dict, list[dict]]:
    page = await ctx.new_page()
    try:
        await _open(page, url, "h1.DUwDvf")
        hours = page.locator(HOURS_BUTTON)
        if await hours.count():
            await hours.first.click()
            await page.wait_for_timeout(800)
        place = await parse_place(page)
        about = page.locator('button[role="tab"]:has-text("Giới thiệu")')
        if await about.count():
            await about.first.click()
            await page.wait_for_timeout(1500)
            place["attributes"] = (await parse_place(page))["attributes"]
        reviews: list[dict] = []
        tab = page.locator('button[role="tab"]:has-text("Bài đánh giá")')
        if max_reviews and await tab.count():
            await tab.first.click()
            await page.wait_for_timeout(1500)
            sort = page.locator(SORT_BUTTON)
            if await sort.count():
                await sort.first.click()
                await page.locator(NEWEST_ITEM).click()
                await page.wait_for_timeout(1500)
            pane = page.locator("div.m6QErb.DxyBCb").first
            for _ in range(max_reviews // 10 + 3):
                n = await page.locator(REVIEW_DIV).count()
                if n >= max_reviews:
                    break
                await pane.evaluate("e => e.scrollBy(0, 5000)")
                if not await _more(page, REVIEW_DIV, n):
                    break  # all reviews loaded
            for more in await page.locator("button.w8nwRe:visible").all():  # "Thêm": expand long reviews
                try:
                    await more.click(timeout=3000)
                except Exception:
                    pass  # best effort: an unexpanded review keeps its truncated text
            reviews = (await parse_reviews(page))[:max_reviews]
        return place, reviews
    finally:
        await page.close()


ATTEMPTS = 3  # per place, when the failure looks like a block


async def _place(ctx: BrowserContext, row: dict, root, c: dict, throttle: Throttle) -> None:
    d = root / "places" / safe_name(row["fid"])
    for attempt in range(1, ATTEMPTS + 1):
        async with throttle:
            try:
                place, reviews = await scrape_place(ctx, row["url"], c["max_reviews_per_place"])
                write_json(d / "reviews.json", reviews)
                write_json(d / "place.json", {**row, **place, "fetched_at": now()})  # written last = done
                throttle.success()
                return
            except LoginRequired:
                raise
            except Exception as e:
                if attempt < ATTEMPTS and type(e).__name__ == "TimeoutError":  # throttled pages stop rendering
                    throttle.blocked()
                    continue
                log_error(root, row["fid"], "place", e)
                return
            finally:
                await pause(*c.get("pause_s", (2.0, 5.0)))


async def run(city: str, headed: bool = False, profile=open_profile) -> None:
    """Searches run one by one and feed places into shared tabs; safe to rerun (done places are skipped)."""
    name, cfg = load_config(city)
    c, root = cfg["gmaps"], data_dir() / "gmaps"
    throttle = Throttle(root / "throttle.json", start=c.get("tabs_start", 1), hi=c.get("tabs", 1),
                        cooldown_s=c.get("cooldown_s", 60), max_cooldown_s=c.get("max_cooldown_s", 900))
    seen: set[str] = set()  # fid, across queries: a place is scraped once per run
    async with profile("gmaps", headed) as ctx:
        await ensure_login(ctx)
        try:
            async with asyncio.TaskGroup() as tg:  # one LoginRequired stops all
                for category in c["categories"]:
                    query = f"{category} {name}"
                    rows = await search(ctx, query, c["max_places_per_query"])
                    append_jsonl(root / "search" / city / f"{slug(query)}.jsonl",
                                 {"at": now(), "query": query, "items": rows})
                    for row in rows:
                        if row["fid"] in seen or (root / "places" / safe_name(row["fid"]) / "place.json").exists():
                            continue
                        seen.add(row["fid"])
                        tg.create_task(_place(ctx, row, root, c, throttle))
                    await pause(*c.get("pause_s", (2.0, 5.0)))
        except* LoginRequired as eg:
            raise eg.exceptions[0] from None
