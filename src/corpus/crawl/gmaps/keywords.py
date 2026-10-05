"""Phase keywords: reviews that Maps' own review search finds for given words -> data/gmaps/places/<fid_dir>/reviews_keywords.json.

Reviews rarely mention slopes, stairs, walks, who a place suits, tickets or booking unprompted, so newest + relevant +
extremes leave many filters without evidence. The search box of the place's review list ("Tìm bài đánh giá") returns
the reviews containing a word. `keyword_sets` pairs words with category groups (config/category_defaults.yaml):
effort and who-it-suits words for experience places, "vé" for places that sell entry, booking words for places to
eat. A place's words are searched and the first `keyword_reviews_per_word` hits of each kept. Only places that show
more reviews than crawl kept are opened, and only for words not searched yet (a new set adds its words to the
existing file). A word's list is complete at n hits or at Maps' end-of-list signal (no hit: Maps says NO_HIT;
checked on the live page 2026-10-05); observe merges the file by review_id and tags its reviews
`sample = keywords` (they count only for effort and facts, docs/CORPUS.md §5).
"""

import asyncio
import json

from playwright.async_api import BrowserContext, Page

from ..common.browser import LoginRequired, open_profile, pause
from ...categories import group
from ..common.files import data_dir, load_config, log_error, now, safe_name, write_json
from ..common.throttle import Throttle
from .crawl import EXPAND_JS, LIST_END_JS, REVIEW_DIV, count, parse_reviews
from .page import ensure_login, more, open_page, text_only

FILE = "reviews_keywords.json"
ATTEMPTS = 2
SEARCH_LABEL = "Tìm bài đánh giá"  # the review list's search box (an input labelled by this text; checked 2026-10-05)
NO_HIT = "Không có bài đánh giá nào nhắc đến cụm từ"  # Maps' own answer when no review has the word
BOX = "input[data-tg-review-search]"
# the box is labelled by an element holding SEARCH_LABEL that hides once text is typed: mark the input once
_MARK_JS = """(label) => { const l = [...document.querySelectorAll('[id]')].find(e => (e.innerText || '').trim() === label);
  const i = l && document.querySelector(`input[aria-labelledby~="${l.id}"]`);
  if (i) i.setAttribute('data-tg-review-search', '1'); return !!i; }"""


def category_group(category: str | None) -> str:
    return group(category)["id"]


def words_for(place: dict, n_kept: int, sets: list[dict]) -> list[str]:
    """The words of every keyword set whose groups hold the place's category group; none when crawl already kept
    every review Maps shows (a search would find nothing new)."""
    if (count(place.get("review_count")) or 0) <= n_kept:
        return []
    g = category_group(place.get("category"))
    return list(dict.fromkeys(w for s in sets if g in s["groups"] for w in s["words"]))


def missing(path, words: list[str]) -> list[str]:
    """Words not searched yet for this place (a file written with fewer keyword sets gets the new words only)."""
    done = json.loads(path.read_text(encoding="utf-8")).get("keywords", {}) if path.exists() else {}
    return [w for w in words if w not in done]


async def search(page: Page, word: str, n: int) -> tuple[list[dict], bool]:
    """First n reviews Maps finds for one word; complete = n reached or the list's end signal."""
    first = await page.query_selector(REVIEW_DIV)
    if not await page.locator(BOX).count():
        await page.wait_for_function(_MARK_JS, arg=SEARCH_LABEL, timeout=15000)
    box = page.locator(BOX).first
    await box.fill(word)
    await box.press("Enter")
    # Maps re-renders the list for a search: the old first review leaves the page even when the new list starts
    # with the same review (comparing ids waited out a timeout then)
    await page.wait_for_function("(e) => !e || !e.isConnected", arg=first, timeout=20000)
    await page.wait_for_timeout(1500)
    if await page.get_by_text(NO_HIT).count():
        return [], True
    pane = page.locator("div.m6QErb.DxyBCb").first
    while True:
        k = await page.locator(REVIEW_DIV).count()
        if k >= n or await page.evaluate(LIST_END_JS):
            complete = True
            break
        # the pane, not the last review: Maps replaces review nodes while loading, and waiting for a replaced node to
        # scroll timed out and cut the tab count as if Google blocked us
        await pane.evaluate("e => e.scrollTo(0, e.scrollHeight)")
        if not await more(page, REVIEW_DIV, k, timeout=15000):
            complete = await page.evaluate(LIST_END_JS)
            break
    for _ in range(3):  # "Xem thêm", best effort as in crawl.py
        if not await page.evaluate(EXPAND_JS):
            break
        await page.wait_for_timeout(500)
    return (await parse_reviews(page))[:n], complete


async def scrape_keywords(ctx: BrowserContext, url: str, words: list[str], n: int, gap) -> dict:
    page = await ctx.new_page()
    try:
        await open_page(page, url, "h1.DUwDvf")
        tab = page.locator('button[role="tab"]:has-text("Bài đánh giá")')
        if not await tab.count():
            return {w: {"complete": True, "reviews": []} for w in words}
        await tab.first.click()
        await page.wait_for_selector(REVIEW_DIV, timeout=20000)
        out = {}
        for w in words:
            reviews, complete = await search(page, w, n)
            out[w] = {"complete": complete, "reviews": reviews}
            await gap()
        return out
    finally:
        await page.close()


async def _place(ctx: BrowserContext, d, url: str, words, n: int, root, c: dict, throttle: Throttle) -> None:
    gap = lambda: pause(*c.get("pause_s", (2.0, 5.0)))  # noqa: E731
    for attempt in range(1, ATTEMPTS + 1):
        async with throttle:
            try:
                found = await scrape_keywords(ctx, url, words, n, gap)
                if not all(v["complete"] for v in found.values()) and attempt < ATTEMPTS:
                    raise RuntimeError("keyword reviews incomplete: a list stopped loading without its end signal")
                old = json.loads((d / FILE).read_text(encoding="utf-8")) if (d / FILE).exists() else {}
                write_json(d / FILE, {"fetched_at": now(), "keywords": {**old.get("keywords", {}), **found}})
                throttle.success()
                return
            except LoginRequired:
                raise
            except Exception as e:
                if attempt < ATTEMPTS:
                    print(f"retry {d.name}: {type(e).__name__}: {str(e).splitlines()[0][:120]}", flush=True)
                    if type(e).__name__ == "TimeoutError":
                        throttle.blocked()
                    continue
                log_error(root, d.name, "keywords", e)
                return
            finally:
                await gap()


async def run(city: str, headed: bool = False, profile=open_profile, limit: int | None = None) -> None:
    _, cfg = load_config(city)
    c, root = cfg["gmaps"], data_dir() / "gmaps"
    sets, n = c.get("keyword_sets", []), c.get("keyword_reviews_per_word", 20)
    listed = root / "list" / f"{city}.json"
    keep = {safe_name(r["fid"]) for r in json.loads(listed.read_text(encoding="utf-8"))["items"]} if listed.exists() else None
    todo = []
    for f in sorted((root / "places").glob("*/place.json")):
        if keep is not None and f.parent.name not in keep:
            continue
        place = json.loads(f.read_text(encoding="utf-8"))
        kept = json.loads((f.parent / "reviews.json").read_text(encoding="utf-8"))
        words = missing(f.parent / FILE, words_for(place, len(kept), sets))
        if words:
            todo.append((f.parent, place["url"], words))
    todo = todo[:limit]
    print(f"keywords {city}: {len(todo)} places left")
    throttle = Throttle(root / "keywords_throttle.json", start=c.get("keyword_tabs_start", 4), hi=c.get("keyword_tabs", 8),
                        cooldown_s=c.get("cooldown_s", 60), max_cooldown_s=c.get("max_cooldown_s", 900))
    async with profile("gmaps", headed) as ctx:
        await text_only(ctx)
        await ensure_login(ctx)
        try:
            async with asyncio.TaskGroup() as tg:
                for d, url, words in todo:
                    tg.create_task(_place(ctx, d, url, words, n, root, c, throttle))
        except* LoginRequired as eg:
            raise eg.exceptions[0] from None
    done = sum(not missing(d / FILE, words) for d, _, words in todo)
    print(f"keywords {city}: {done}/{len(todo)} done, the rest in errors.jsonl")
