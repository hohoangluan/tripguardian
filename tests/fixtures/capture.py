"""Save real responses from logged-in profiles as test fixtures. Run: python tests/fixtures/capture.py"""

import asyncio
import json
import re
from pathlib import Path

from corpus.crawl.common.browser import open_profile
from corpus.crawl.gmaps.crawl import HOURS_BUTTON, NEWEST_ITEM, SORT_BUTTON
from corpus.crawl.tiktok.crawl import COMMENT_API, COMMENT_BUTTON, REPLY_API, REPLY_BUTTON

OUT = Path(__file__).parent
TIKTOK_QUERY = "quán cà phê đà lạt"
GMAPS_QUERY = "thác đà lạt"


def scrub(html: str) -> str:
    # Pages come from a logged-in profile: drop scripts (session data) and the account's name and email.
    html = re.sub(r"<(script|style)\b.*?</\1>", "", html, flags=re.S | re.I)
    for name in set(re.findall(r"Tài khoản Google</div><div[^>]*>([^<]+)<", html)):  # account menu card
        html = html.replace(name, "Redacted")
    html = re.sub(r'aria-label="Tài khoản Google:[^"]*"', 'aria-label="Tài khoản Google"', html)
    return re.sub(r"[\w.%+-]+@(gmail|googlemail)\.com", "redacted@example.com", html)


async def save_page(page, name: str) -> None:
    (OUT / "gmaps" / name).write_text(scrub(await page.content()), encoding="utf-8")


async def tiktok() -> None:
    got: dict[str, dict] = {}

    async def keep(r):
        # "replies" before "comments": the reply path extends the comment path.
        for key, part in (("search", "/api/search/item/full"), ("replies", REPLY_API), ("comments", COMMENT_API)):
            if part in r.url:
                if key not in got:
                    try:
                        got[key] = await r.json()
                    except Exception:
                        pass
                break

    async with open_profile("tiktok", headed=True) as ctx:
        page = await ctx.new_page()
        page.on("response", keep)
        await page.goto(f"https://www.tiktok.com/search/video?q={TIKTOK_QUERY}")
        await page.wait_for_timeout(8000)
        item = got["search"]["item_list"][0]
        await page.goto(f"https://www.tiktok.com/@{item['author']['uniqueId']}/video/{item['id']}")
        await page.locator(COMMENT_BUTTON).first.click(timeout=15000)
        await page.wait_for_timeout(5000)
        await page.locator(REPLY_BUTTON).filter(has_text="Xem").first.click(timeout=15000)
        await page.wait_for_timeout(4000)
    for key, payload in got.items():
        (OUT / "tiktok").mkdir(exist_ok=True)
        (OUT / "tiktok" / f"{key}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print("tiktok:", sorted(got))


async def gmaps() -> None:
    (OUT / "gmaps").mkdir(exist_ok=True)
    async with open_profile("gmaps", headed=True) as ctx:
        page = await ctx.new_page()
        await page.goto(f"https://www.google.com/maps/search/{GMAPS_QUERY}?hl=vi")
        await page.wait_for_selector('div[role="feed"]')
        await page.wait_for_timeout(3000)
        await save_page(page, "feed.html")
        # Open the place URL directly, as gmaps.scrape_place does (a click keeps the result list in the DOM).
        await page.goto(await page.locator("a.hfpxzc").first.get_attribute("href"))
        await page.wait_for_selector("h1.DUwDvf")
        await page.wait_for_timeout(4000)
        await page.locator(HOURS_BUTTON).first.click()
        await page.wait_for_timeout(1500)
        await save_page(page, "place.html")
        await page.locator('button[role="tab"]:has-text("Bài đánh giá")').first.click()
        await page.wait_for_timeout(2000)
        await page.locator(SORT_BUTTON).first.click()
        await page.locator(NEWEST_ITEM).click()
        await page.wait_for_timeout(2000)
        await page.locator("div.m6QErb.DxyBCb").first.evaluate("e => e.scrollBy(0, 5000)")
        await page.wait_for_timeout(2000)
        await save_page(page, "reviews.html")
    print("gmaps: feed, place, reviews")


if __name__ == "__main__":
    asyncio.run(tiktok())
    asyncio.run(gmaps())
