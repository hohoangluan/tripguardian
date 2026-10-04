"""Phase 1, search: every category over map tiles of the city area; a tile whose list is capped is split.

Writes only data/gmaps/search/<city>/<category>.jsonl, one line per tile: {at, query, tile, end, lodging, items:[{fid,
name, url, category, rating, reviews, lat, lng, price_vnd, amenities}]}, only places inside the area; price_vnd and
amenities are read from the card's own text and are None / [] outside the lodging list; end = the list was scrolled to its end; lodging = Maps switched to its hotel list (URL "!6e3"),
which ignores the viewport, so splitting it only helps down to grid.lodging_max_zoom. Maps pads a short list with
places in other cities (Hồ Chí Minh…): those are dropped. Raw otherwise: duplicates across tiles, lodging, off-topic. Tiles already in the file (with an end flag) are not searched again.

No login: Google limits one session (lists stop growing after a few dozen tiles, whatever the tab count) but not the
IP, and a signed-out list is the same list. So every try runs in a fresh cookie-less context.
"""

import asyncio
import collections
import json
import re
import unicodedata
from urllib.parse import quote

from playwright.async_api import BrowserContext, Page

from ..common.browser import LoginRequired, open_sessions, pause
from ..common.files import append_jsonl, data_dir, load_config, log_error, now, slug
from ..common.throttle import Throttle
from .page import more, open_page
from .tiles import bounds, children, in_area, overlaps, root_tiles

TILE_URL = "https://www.google.com/maps/search/{}/@{},{},{}z?hl=vi"
FEED_A = "a.hfpxzc"
# [label, href, first info line, stars label]; the info line starts with the Maps category ("Quán cà phê · $$ · …"),
# the stars label reads "4,4 sao 25.362 bài đánh giá"
FEED_JS = """() => [...document.querySelectorAll('a.hfpxzc')].map(a => {
  const card = a.closest('div.Nv2PK') || a.parentElement;
  return [a.getAttribute('aria-label'), a.href, card.querySelector('div.W4Efsd > div.W4Efsd')?.innerText ?? '',
          [...card.querySelectorAll('[role="img"][aria-label]')].map(e => e.getAttribute('aria-label'))
            .find(l => /sao/.test(l)) ?? '', card.innerText];
})"""
_VISITED = re.compile(r"\s*·?\s*Đường liên kết đã truy cập\s*$")  # added to links this profile opened before
_STARS = re.compile(r"([\d,]+) sao(?: ([\d.]+) bài đánh giá)?")
_FID = re.compile(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)")
_LATLNG = re.compile(r"!3d(-?[\d.]+)!4d(-?[\d.]+)")


_PRICE = re.compile(r"([\d][\d.]*)\s*₫")
# Best-effort: a candidate's card text against a fixed phrase list, not a guessed CSS class. Re-check against the
# live hotel list before trusting this — Maps may word or lay these out differently than assumed here.
_AMENITY = {"parking": re.compile(r"bãi đỗ xe|bãi đậu xe", re.I), "breakfast": re.compile(r"bữa sáng", re.I),
           "pool": re.compile(r"hồ bơi", re.I), "wifi": re.compile(r"wi-?fi", re.I)}


def price_vnd(card_text: str) -> int | None:
    m = _PRICE.search(card_text or "")
    return int(m.group(1).replace(".", "")) if m else None


def amenities(card_text: str) -> list[str]:
    return [a for a, pat in _AMENITY.items() if pat.search(card_text or "")]


def place_row(name: str, url: str, info: str = "", stars: str = "", card_text: str = "") -> dict | None:
    fid, ll = _FID.search(url), _LATLNG.search(url)
    if not fid:
        return None
    st = _STARS.search(unicodedata.normalize("NFC", stars or ""))
    return {"fid": fid.group(1), "name": _VISITED.sub("", unicodedata.normalize("NFC", name)).strip(), "url": url,
            "category": info.split("·")[0].strip() or None,
            "rating": float(st.group(1).replace(",", ".")) if st else None,
            "reviews": int(st.group(2).replace(".", "")) if st and st.group(2) else None,
            "lat": float(ll.group(1)) if ll else None, "lng": float(ll.group(2)) if ll else None,
            "price_vnd": price_vnd(card_text), "amenities": amenities(card_text)}


async def parse_feed(page: Page, url: str | None = None) -> list[dict]:
    rows = [place_row(*r) for r in await page.evaluate(FEED_JS)]
    if not rows:  # exact match: Maps opened the place page itself
        name, category, stars, count = await page.evaluate(
            "() => [document.querySelector('h1.DUwDvf')?.innerText.trim() ?? '',"
            " document.querySelector('button[jsaction*=\"category\"]')?.innerText.trim() ?? '',"
            " [...document.querySelectorAll('[aria-label]')].map(e => e.getAttribute('aria-label').trim())"
            "   .find(l => /^[\\d,]+ sao$/.test(l)) ?? '',"
            " [...document.querySelectorAll('[aria-label]')].map(e => e.getAttribute('aria-label').trim())"
            "   .find(l => /^[\\d.]+ bài đánh giá$/.test(l)) ?? '']")
        rows = [place_row(name, url or page.url, category, f"{stars} {count}")] if name else []
    return list({r["fid"]: r for r in rows if r}.values())


STALE_ROUNDS = 3  # scrolls in a row that load nothing: the list is stuck, not finished


LODGING_URL = "!6e3"  # Maps' hotel list: date / price filters, results city-wide whatever the viewport
# Maps stopped putting LODGING_URL in the URL (2026-10-04); the hotel list's own controls are the stable sign
HOTEL_CONTROLS = '[aria-label="Giá mỗi đêm"], [aria-label^="Đặt ngày nhận phòng"]'


async def is_hotel_list(page: Page) -> bool:
    """Whether Maps answered with its hotel list (check-in / check-out and nightly price controls)."""
    return LODGING_URL in page.url or await page.locator(HOTEL_CONTROLS).count() > 0


async def search(ctx: BrowserContext, query: str, limit: int, at: tuple) -> tuple[list[dict], bool, bool]:
    """Places Maps lists for query in the viewport at = (lat, lng, zoom), whether the list reached its end, and
    whether Maps showed its hotel list instead."""
    page = await ctx.new_page()
    try:
        await open_page(page, TILE_URL.format(quote(query), *at), 'div[role="feed"], h1.DUwDvf', signed_in=False)
        feed = page.locator('div[role="feed"]')
        end, stale = not await feed.count(), 0  # no feed = single place page: that is the whole list
        while not end and stale < STALE_ROUNDS:
            n = len(await page.evaluate(FEED_JS))
            if n >= limit or await page.get_by_text("Bạn đã xem hết danh sách này").count():
                end = True
                break
            # scrollBy often fails to trigger the next batch; bringing the last result into view does
            await page.locator(FEED_A).last.scroll_into_view_if_needed()
            await feed.evaluate("e => e.scrollTo(0, e.scrollHeight)")
            stale = 0 if await more(page, FEED_A, n, timeout=10000) else stale + 1
        return (await parse_feed(page))[:limit], end, await is_hotel_list(page)
    finally:
        await page.close()


def done_tiles(d) -> dict:
    """(query, tile) -> (items, end, lodging) already searched; cut-short lists and records without an end flag or
    item category / rating (older formats) are searched again; lodging is None on records made before it was recorded."""
    done = {}
    for f in sorted(d.glob("*.jsonl")) if d.exists() else []:
        for line in f.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            if rec.get("tile") and "end" in rec and all("rating" in i for i in rec["items"])                     and (rec["end"] or rec.get("lodging")):  # a cut-short list was a soft block: search again
                done[(rec["query"], tuple(rec["tile"]))] = (rec["items"], rec["end"], rec.get("lodging"))
    return done


ATTEMPTS = 3  # per tile, when the page never loads (Google throttling)


async def run(city: str, headed: bool = False, sessions=open_sessions) -> None:
    """One category at a time, its tiles in parallel tabs (throttle.py: self-tuning count, saved in
    gmaps/search_throttle.json), so each category file is finished before the next one starts."""
    name, cfg = load_config(city)
    c, root, area = cfg["gmaps"], data_dir() / "gmaps", cfg.get("area")
    if not area:
        raise SystemExit(f"config/cities.yaml: {city} has no area")
    grid, out = c["grid"], root / "search" / city
    done = done_tiles(out)
    throttle = Throttle(root / "search_throttle.json", start=c.get("search_tabs_start", 1), hi=c.get("search_tabs", 1),
                        cooldown_s=c.get("cooldown_s", 60), max_cooldown_s=c.get("max_cooldown_s", 900))
    new = collections.Counter()

    async def fetch(new_session, category: str, tile: tuple):
        for attempt in range(1, ATTEMPTS + 1):
            async with throttle:
                ctx = None
                try:
                    ctx = await new_session()
                    found = await search(ctx, category, grid.get("limit", 120), tile)
                    found = ([r for r in found[0] if in_area(r.get("lat"), r.get("lng"), area)], *found[1:])
                    if not found[1] and not found[2] and attempt < ATTEMPTS:
                        # a session loading too fast gets lists that stop growing (no error, no captcha): slow down
                        throttle.blocked()
                        continue
                    append_jsonl(out / f"{slug(category)}.jsonl",
                                 {"at": now(), "query": category, "tile": list(tile), "end": found[1],
                                  "lodging": found[2], "items": found[0]})
                    new[category] += 1
                    throttle.success()
                    return found
                except LoginRequired:
                    raise
                except Exception as e:
                    # timeouts (throttling) and network drops (net::ERR_…, e.g. a network switch) are worth another try
                    if attempt < ATTEMPTS and (type(e).__name__ == "TimeoutError" or "net::ERR_" in str(e)):
                        throttle.blocked()
                        continue
                    log_error(root, f"{category}@{list(tile)}", "search", e)
                    return None
                finally:
                    if ctx is not None:
                        await ctx.close()
                    await pause(*c.get("pause_s", (2.0, 5.0)))

    async def visit(ctx, tg, category: str, tile: tuple):
        found = done.get((category, tile))
        if found and found[2] is None and (len(found[0]) >= grid["full_at"] or not found[1]):
            found = None  # recorded before the lodging flag, which now decides how deep to split
        if found is None:
            found = await fetch(ctx, category, tile)
            if found is None:
                return
        rows, end, lodging = found
        deepest = grid.get("lodging_max_zoom", grid["max_zoom"]) if lodging else grid["max_zoom"]
        # Maps fills a list with far-away places (other cities) once the viewport runs out: only places inside the
        # tile say the list was capped
        local = sum(in_area(r.get("lat"), r.get("lng"), bounds(tile)) for r in rows)
        if local >= grid["full_at"] or not end:  # capped or cut-short list: places are missing, look closer
            if tile[2] < deepest:
                for t in children(tile):
                    if overlaps(t, area):
                        tg.create_task(visit(ctx, tg, category, t))
            elif not end and not lodging:  # full at max_zoom is expected (shallow search); a cut-short list is not
                log_error(root, f"{category}@{list(tile)}", "search", RuntimeError("list cut short at max zoom"))

    async with sessions(headed) as ctx:
        for category in c["categories"]:
            try:
                async with asyncio.TaskGroup() as tg:  # one LoginRequired stops all
                    for tile in root_tiles(area, grid["start_zoom"]):
                        tg.create_task(visit(ctx, tg, category, tile))
            except* LoginRequired as eg:
                raise eg.exceptions[0] from None
            print(f"search {category}: {new[category]} new tiles")
