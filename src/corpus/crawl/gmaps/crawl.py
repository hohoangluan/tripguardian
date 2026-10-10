"""Phase 4, crawl: open every place of data/gmaps/list/<city>.json and save its details and reviews.

Writes only data/gmaps/places/<fid_dir>/: reviews.json, then place.json (= done; a rerun skips it). Places are
scraped in parallel tabs (throttle.py). A place with fewer reviews than too_few() allows is retried, never saved, and
a saved one is crawled again: a signed-out or throttled page shows only a handful of reviews.
"""

import asyncio
import json
import re

from playwright.async_api import BrowserContext, Page

from ..common.browser import LoginRequired, open_profile, pause
from ..common.files import author_hash, data_dir, load_config, log_error, now, safe_name, write_json
from ..common.throttle import Throttle
from .gate import GateThrottle
from ...review import retry_ids
from .page import CaptchaBlocked, check_signed_in, ensure_login, more, open_page, text_only

HOURS_BUTTON = '[role="button"][jsaction*="openhours"][jsaction*="dropdown"]'
SORT_BUTTON = 'button[aria-haspopup="true"][aria-label="Phù hợp nhất"]'  # label = current review order
SORTED_NEWEST_JS = """() => [...document.querySelectorAll('button[aria-haspopup="true"]')]
  .some(b => b.getAttribute('aria-label')?.normalize('NFC') === 'Mới nhất')"""  # label switches to decomposed text
NEWEST_ITEM = '[role="menuitemradio"][data-index="1"]'  # "Mới nhất"; menu text is NFD, so match by position

REVIEW_DIV = "div.jftiEf[data-review-id]"
PLACE_JS = r"""() => {
  const clean = s => s.replace(/[\ue000-\uf8ff]/g, '').trim();  // drop icon-font glyphs (address pin, hours arrow)
  const q = s => document.querySelector(s), t = e => e ? clean(e.innerText) : null;
  const labels = [...document.querySelectorAll('[aria-label]')].map(e => e.getAttribute('aria-label').trim());
  return {
    name: t(q('h1.DUwDvf')), category: t(q('button[jsaction*="category"]')),
    address: t(q('[data-item-id="address"]')), website: q('a[data-item-id="authority"]')?.href ?? null,
    phone: q('[data-item-id^="phone:tel:"]')?.dataset.itemId.slice(10) ?? null,
    description: t(q('.PYvSYb')),
    hours: [...document.querySelectorAll('table.eK4R0e tr')].map(r => clean(r.innerText.replace(/\s+/g, ' '))).filter(Boolean),
    status: t(q('.ZDu9vd span')),
    attributes: labels.filter(a => /^(Có|Không có|Phù hợp|Lối vào|Nhà vệ sinh|Chỗ đậu xe)/.test(a)),
    popular_times: [...document.querySelectorAll('div.C7xf8b > div')].map(day =>  // 7 days, Sunday first
      [...day.querySelectorAll('[role="img"][aria-label]')].map(e => e.getAttribute('aria-label').trim())),
    rating: labels.find(a => /^[\d,]+ sao$/.test(a)) ?? null,
    review_count: labels.find(a => /^[\d.]+ bài đánh giá$/.test(a)) ?? null,
    rating_histogram: [...document.querySelectorAll('tr[aria-label]')].map(e => e.getAttribute('aria-label').trim()),  // 5 stars first
    price: labels.find(a => /^Khoảng giá/.test(a)) ?? labels.find(a => /^Giá (rẻ|vừa phải|đắt|rất đắt)/.test(a)) ?? null,
    plus_code: t(q('[data-item-id="oloc"]')),
    tickets: [...document.querySelectorAll('h2')].filter(h => /^Vé vào cửa/.test(h.innerText.trim()))
      .map(h => h.parentElement.parentElement.parentElement.innerText.trim())[0] ?? null,  // raw offers text
  };
}"""

# "Xem thêm" of the review only: the owner's reply (.CDe7pd) is not evidence (docs/P1_CORPUS.md, source roles)
EXPAND_JS = """() => { const b = [...document.querySelectorAll('div.jftiEf button.w8nwRe')].filter(e => !e.closest('.CDe7pd'));
  b.forEach(e => e.click()); return b.length; }"""

# The review pane ends in a loader (a div with a spinner) while more reviews can load; Maps empties it once the
# last batch is in. An empty last child = end of list, known without waiting for a timeout.
LIST_END_JS = """() => { const l = document.querySelector('div.m6QErb.DxyBCb')?.lastElementChild;
  return !!l && l.childElementCount === 0; }"""

LAST_DATE_JS = f"() => [...document.querySelectorAll('{REVIEW_DIV} :is(.rsqaWe, .xRkPPb)')].pop()?.innerText ?? null"

REVIEWS_JS = r"""() => [...document.querySelectorAll('div.jftiEf[data-review-id]')].map(r => {
  const own = r.querySelector('.CDe7pd'), mine = s => [...r.querySelectorAll(s)].find(e => !own?.contains(e));
  const photos = [...r.querySelectorAll('button.Tya61d[aria-label]')].map(b => b.getAttribute('aria-label'));
  return {
    review_id: r.dataset.reviewId,
    author: r.querySelector('[data-href*="/contrib/"]')?.dataset.href.match(/contrib\/(\d+)/)?.[1] ?? '',
    author_meta: r.querySelector('.RfnDt')?.innerText.trim() || null,  // "Local Guide · 56 bài đánh giá · 235 ảnh"
    rating: r.querySelector('[role="img"][aria-label*="sao"]')?.getAttribute('aria-label').trim()
      ?? r.querySelector('.fzvQIb')?.innerText.trim() ?? null,  // lodging layout: "4/5"
    text: mine('.wiI7pd')?.innerText.trim() ?? '',  // the owner's reply (not kept) uses the same class
    details: [...r.querySelectorAll('.PBK6be')].map(e => e.innerText.trim()).filter(Boolean),  // "Dịch vụ: 5", ...
    published_text: r.querySelector('.rsqaWe, .xRkPPb')?.innerText.trim() ?? null,  // lodging: "… trước trên Google"
    likes: parseInt(r.querySelector('.pkWtMe')?.innerText ?? '0', 10) || 0,
    photos: photos.filter(a => /^Ảnh số/.test(a)).length + photos.reduce((n, a) => n + +(a.match(/^và (\d+)/)?.[1] ?? 0), 0),
  };
})"""


_AGE = re.compile(r"(một|\d+) (phút|giờ|ngày|tuần|tháng|năm) trước")


def age_months(published_text: str | None) -> int | None:
    """Whole months from Maps' relative date ("4 tháng trước"); None when it cannot be read."""
    m = _AGE.search(published_text or "")
    if not m:
        return None
    n = 1 if m.group(1) == "một" else int(m.group(1))
    return {"tháng": n, "năm": 12 * n}.get(m.group(2), 0)


def count(text: str | None) -> int | None:
    """Number in a Maps label ("1.701 bài đánh giá" -> 1701)."""
    digits = re.sub(r"\D", "", (text or "").split(" ")[0])
    return int(digits) if digits else None


def keep_recent(reviews: list[dict], max_age_months: int | None, min_count: int) -> list[dict]:
    """Newest-first reviews: the first min_count always, then only those within max_age_months."""
    if max_age_months is None:
        return reviews
    return [r for i, r in enumerate(reviews)
            if i < min_count or (age_months(r["published_text"]) or 0) <= max_age_months]


async def parse_place(page: Page) -> dict:
    return await page.evaluate(PLACE_JS)


async def parse_reviews(page: Page) -> list[dict]:
    rows = []
    for r in await page.evaluate(REVIEWS_JS):
        r["author_hash"] = author_hash(r.pop("author"))
        rows.append(r)
    return list({r["review_id"]: r for r in rows}.values())


async def scrape_place(ctx: BrowserContext, url: str, max_reviews: int | None, max_age_months: int | None = None,
                       min_reviews: int = 0) -> tuple[dict, list[dict]]:
    page = await ctx.new_page()
    try:
        await open_page(page, url, "h1.DUwDvf")
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
        if max_reviews != 0 and await tab.count():  # None = no cap, 0 = no reviews
            await tab.first.click()
            await page.wait_for_timeout(1500)
            sort = page.locator(SORT_BUTTON)
            try:  # the button renders a moment after the tab; without it the order is "most relevant"
                await sort.first.wait_for(timeout=10000)
            except Exception:
                pass  # place without reviews; run() rejects it if the place says it has some
            if await sort.count():
                await sort.first.click()
                await page.locator(NEWEST_ITEM).click()
                await page.wait_for_function(SORTED_NEWEST_JS, timeout=10000)  # raises when the sort did not apply
                await page.wait_for_timeout(1500)
            try:  # the list reloads after sorting and is empty for a while, longer when many tabs are open
                await page.wait_for_selector(REVIEW_DIV, timeout=20000)
            except Exception:
                pass  # place without reviews; run() rejects it if the place says it has some
            pane = page.locator("div.m6QErb.DxyBCb").first
            total = count(place.get("review_count"))
            complete = False  # stopped on an explicit signal, not on silence
            while True:
                n = await page.locator(REVIEW_DIV).count()
                if (max_reviews and n >= max_reviews) or (total and n >= total) or await page.evaluate(LIST_END_JS):
                    complete = True
                    break
                # scrollBy / wheel often fail to trigger the next batch; bringing the last review into view does
                await page.locator(REVIEW_DIV).last.scroll_into_view_if_needed()
                await pane.evaluate("e => e.scrollTo(0, e.scrollHeight)")
                if not await more(page, REVIEW_DIV, n, timeout=15000):
                    complete = await page.evaluate(LIST_END_JS)  # safety net: batches can take 8+ s
                    break
                old = max_age_months is not None and (age_months(await page.evaluate(LAST_DATE_JS)) or 0) > max_age_months
                if n >= min_reviews and old:  # newest first: the rest is older
                    complete = True
                    break
            place["reviews_complete"] = complete
            for _ in range(3):  # "Xem thêm": expand long reviews and replies; best effort, a miss keeps the cut text
                if not await page.evaluate(EXPAND_JS):
                    break
                await page.wait_for_timeout(500)
            parsed = await parse_reviews(page)
            loaded = parsed[:max_reviews]
            reviews = keep_recent(loaded, max_age_months, min_reviews)
            # newest first: once an older one loaded, the kept ones are all the recent ones there are
            place["reviews_age_cut"] = len(reviews) < len(loaded)
            # every review the place has: ended on the list's own end signal, nothing cut by age or by the cap
            place["reviews_full"] = complete and not place["reviews_age_cut"] and not (max_reviews and len(parsed) >= max_reviews)
        await check_signed_in(page)  # the Google bar, with its sign-in link, renders well after the title
        return place, reviews
    finally:
        await page.close()



ATTEMPTS = 3  # per place, when the failure looks like a block


def too_few(n: int, review_count: str | None, c: dict, age_cut: bool) -> bool:
    """Under half the reviews the place shows (up to the cap) while no review past the age limit was reached: a
    signed-out or throttled page stops at ~8. Maps' count runs a little above what it lists, hence the half.
    Cut by age: under half of min_reviews_per_place (older reviews are kept up to that many) is too few as well."""
    total = count(review_count)
    cap = c.get("max_reviews_per_place")
    if cap == 0 or not total:
        return False
    if age_cut:
        return n < min(total, c.get("min_reviews_per_place") or 0) // 2
    return n < min(total, cap or total) // 2


def needs_deeper(p: dict, n: int, c: dict) -> bool:
    """A saved place the current limits would crawl further: cut by age or by the cap (or saved before those were
    recorded) and under 90% of the reviews the config now asks for. A place saved whole, or flagged incomplete after
    its retries, is never crawled again here."""
    total, cap = count(p.get("review_count")), c.get("max_reviews_per_place")
    if p.get("reviews_full") or p.get("reviews_complete") is False or cap == 0 or not total:
        return False
    if p.get("reviews_age_cut") and c.get("max_review_age_months") is not None:
        return False  # the age limit still applies: nothing more to take
    return n < 0.9 * min(total, cap or total)


async def _place(ctx: BrowserContext, row: dict, root, c: dict, throttle: Throttle) -> None:
    d = root / "places" / safe_name(row["fid"])
    for attempt in range(1, ATTEMPTS + 1):
        async with throttle:
            try:
                place, reviews = await scrape_place(ctx, row["url"], c.get("max_reviews_per_place"),
                                                    c.get("max_review_age_months"), c.get("min_reviews_per_place", 0))
                if too_few(len(reviews), place.get("review_count"), c, place.get("reviews_age_cut", False)):
                    raise RuntimeError(f"too few reviews: {len(reviews)} of {place.get('review_count')}")
                if place.get("reviews_complete") is False and attempt < ATTEMPTS:
                    raise RuntimeError("reviews incomplete: the list stopped loading without its end signal")
                if place.get("reviews_complete") is False:  # last attempt: keep what loaded, flagged, and say so
                    log_error(root, row["fid"], "reviews", RuntimeError("reviews incomplete after retries"))
                write_json(d / "reviews.json", reviews)
                write_json(d / "place.json", {**row, **place, "fetched_at": now()})  # written last = done
                throttle.success()
                return
            except LoginRequired:
                raise
            except Exception as e:
                slow = "too few reviews: 0 " in str(e)  # list not loaded yet
                slow = slow or "incomplete" in str(e)  # a slow batch, not a block: retry without cutting tabs
                blocked = type(e).__name__ == "TimeoutError" or isinstance(e, CaptchaBlocked) or ("too few reviews" in str(e) and not slow)
                if attempt < ATTEMPTS and (slow or blocked):
                    print(f"retry {row['fid']} ({attempt}/{ATTEMPTS}): {str(e).splitlines()[0][:120]}")
                    if blocked:  # a page that never loads is Google throttling; a slow review list is not
                        throttle.blocked()
                    continue
                log_error(root, row["fid"], "place", e)
                return
            finally:
                await pause(*c.get("pause_s", (2.0, 5.0)))


async def run(city: str, headed: bool = False, profile=open_profile, shard: tuple[int, int] | None = None,
              profile_name: str | None = None) -> None:
    _, cfg = load_config(city)
    c, root = cfg["gmaps"], data_dir() / "gmaps"
    lst = root / "list" / f"{city}.json"
    if not lst.exists():
        raise SystemExit(f"no {lst}; run `python -m corpus gmaps list --city {city}` first")
    fetched, thin = {}, set()
    for f in (root / "places").glob("*/place.json"):
        p = json.loads(f.read_text(encoding="utf-8"))
        fetched[p["fid"]] = p["fetched_at"]
        reviews = json.loads((f.parent / "reviews.json").read_text(encoding="utf-8"))
        age_cut = p.get("reviews_age_cut") or any((age_months(r.get("published_text")) or 0) > (c.get("max_review_age_months") or 10**6)
                                                  for r in reviews)  # older files kept a few old reviews
        if too_few(len(reviews), p.get("review_count"), c, age_cut) or needs_deeper(p, len(reviews), c):
            thin.add(p["fid"])  # saved from a signed-out or throttled page, or under the current depth
    again = retry_ids("place_reviews", fetched) | thin  # a person asked to crawl these again (review)
    todo = [r for r in json.loads(lst.read_text(encoding="utf-8"))["items"]
            if r["fid"] in again or not (root / "places" / safe_name(r["fid"]) / "place.json").exists()]
    if thin:
        print(f"crawl {city}: {len(thin)} saved places have too few reviews or fewer than the config asks for, crawling them again")
    if shard:  # one process per shard, each with its own browser (one Python process caps ~8 tabs)
        todo = todo[shard[0]::shard[1]]
    print(f"crawl {city}: {len(todo)} places left" + (f" (shard {shard[0]}/{shard[1]})" if shard else ""))
    throttle = GateThrottle(root / "throttle.json", start=c.get("tabs_start", 1), hi=c.get("tabs", 1),
                        cooldown_s=c.get("cooldown_s", 60), max_cooldown_s=c.get("max_cooldown_s", 900))
    async with profile(profile_name or "gmaps", headed) as ctx:
        await text_only(ctx)  # text and aria-labels only: a drawn map kept ~1 core busy per tab (2026-10-07)
        await ensure_login(ctx)
        try:
            async with asyncio.TaskGroup() as tg:  # one LoginRequired stops all
                for row in todo:
                    tg.create_task(_place(ctx, row, root, c, throttle))
        except* LoginRequired as eg:
            raise eg.exceptions[0] from None
    done = sum((root / "places" / safe_name(r["fid"]) / "place.json").exists() for r in todo)
    print(f"crawl {city}: {done}/{len(todo)} done, the rest in errors.jsonl")
