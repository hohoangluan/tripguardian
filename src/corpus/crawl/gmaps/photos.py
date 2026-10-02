"""Phase photos: newest Maps photos of each listed place -> data/gmaps/places/<fid_dir>/photos/ + photos.json.

The place page's photo gallery, tab "Mới nhất" (newest first; "Tất cả" when a place has no such tab), first
photos_per_place tiles. Each tile is opened once to read who posted it (contrib id -> author_hash, the same hash
as their reviews, so one person is one vote across text and photos) and when ("Ảnh - thg 9 2026"); the image is
downloaded at photo_px. A photo posted by the place itself (contributor name = place name) is flagged `owner`:
marketing pictures, kept but weighed by the reader. Video tiles keep their still frame (`kind = video`).

At most PER_AUTHOR photos per poster, from the first SCAN_FACTOR x photos_per_place tiles. Complete = enough photos,
or the gallery ended (stopped growing after END_SCROLLS scrolls: a small gallery). A page that breaks mid-way is retried; the last try is saved with `complete: false` and logged.
Written once per place; delete photos.json to fetch again.
"""

import asyncio
import collections
import json
import re

from playwright.async_api import BrowserContext, Page

from ..common.browser import LoginRequired, open_profile, pause
from ..common.files import author_hash, data_dir, load_config, log_error, now, safe_name, write_json
from ..common.throttle import Throttle
from .page import ensure_login, more, open_page

FILE = "photos.json"
TILE = "a[data-photo-index]"
ATTEMPTS = 2
END_SCROLLS = 2
PER_AUTHOR = 3  # photos kept per poster
SCAN_FACTOR = 3  # tiles looked at per photo wanted
MAX_AGE_YEARS = 3  # older photos (taken, else posted) are skipped: the place may have changed
_SIZE = re.compile(r"=w\d+-h\d+[^\"')]*$")

TILES_JS = r"""() => [...document.querySelectorAll('a[data-photo-index]')].map(a => {
  const img = a.querySelector('[style*="googleusercontent"]');
  const url = img?.getAttribute('style').match(/url\(["']?([^"')]+)/)?.[1] ?? null;
  return {index: +a.dataset.photoIndex, url, video: (a.getAttribute('aria-label') || '') === 'Video'};
})"""

VIEWER_JS = r"""() => {
  const who = [...document.querySelectorAll('a[href*="/contrib/"]')].find(a => a.innerText.trim());
  const texts = [...document.querySelectorAll('div, span')].map(e => e.childElementCount ? '' : (e.innerText || '').trim());
  return {
    id: location.href.match(/!1s([^!?]+)/)?.[1] ?? null,
    contributor: who?.href.match(/contrib\/(\d+)/)?.[1] ?? null,
    name: who?.innerText.trim() ?? null,
    posted: texts.find(t => /^(Ảnh|Video)\s*-\s*\S/.test(t)) ?? null,      // "Ảnh - thg 2 2026"
    taken: texts.find(t => /^Ảnh chụp vào:/.test(t))?.replace(/^Ảnh chụp vào:\s*/, '') ?? null,
  };
}"""


def sized(url: str, px: int) -> str:
    url = url if url.startswith("http") else "https:" + url
    return _SIZE.sub(f"=w{px}-h{px}-k-no", url) if _SIZE.search(url) else url + f"=w{px}-h{px}-k-no"


def norm(s: str | None) -> str:
    return re.sub(r"\W+", "", (s or "").casefold())


TABS = ("Mới nhất", "Tất cả")  # newest first; "Mới nhất" holds only recent months, "Tất cả" fills the rest


async def open_gallery(page: Page, label: str) -> bool:
    b = page.locator(f'button[aria-label^="{label}"], button:has-text("{label}")')
    if not await b.count():
        return False
    await b.first.click()
    await page.wait_for_timeout(1500)  # the tiles of the previous tab stay until the new ones render
    await page.wait_for_selector(TILE, timeout=15000)
    return True


async def list_tiles(page: Page, n: int) -> tuple[list[dict], bool]:
    """First n tiles; complete = n reached or the gallery stopped growing after END_SCROLLS scrolls."""
    idle = 0
    while True:
        k = await page.locator(TILE).count()
        if k >= n:
            break
        await page.locator(TILE).last.scroll_into_view_if_needed(timeout=5000)
        if await more(page, TILE, k, timeout=6000):
            idle = 0
            continue
        idle += 1
        if idle >= END_SCROLLS:
            break
    tiles = sorted(await page.evaluate(TILES_JS), key=lambda t: t["index"])[:n]
    return [t for t in tiles if t["url"]], True


async def viewer_moved(page: Page, last_id: str | None, timeout_s: float = 8.0) -> dict | None:
    """The viewer's metadata once it shows a photo other than last_id with its poster line, read the same twice in a
    row (the header updates field by field: a single read can mix two photos); None if it never settles."""
    prev = None
    for _ in range(int(timeout_s / 0.4)):
        meta = await page.evaluate(VIEWER_JS)
        if meta["id"] and meta["id"] != last_id and meta["posted"]:
            if meta == prev:
                return meta
            prev = meta
        await page.wait_for_timeout(400)
    return None


_MONTH = re.compile(r"thg (\d{1,2}) (\d{4})")


def month(text: str | None) -> str | None:
    """"Ảnh - thg 9 2026" -> "2026-09"; relative dates ("2 tuần trước") are recent -> None, never too old."""
    m = _MONTH.search(text or "")
    return f"{m.group(2)}-{int(m.group(1)):02d}" if m else None


async def scrape_photos(ctx: BrowserContext, place: dict, d, n: int, px: int, per_author: int = PER_AUTHOR,
                        max_age_years: int = MAX_AGE_YEARS) -> dict:
    """Up to n photos, at most per_author from one poster (a gallery's newest are often one person's burst), from the
    first SCAN_FACTOR * n tiles."""
    oldest = f"{int(now()[:4]) - max_age_years}-{now()[5:7]}"
    page, img = await ctx.new_page(), await ctx.new_page()
    try:
        await open_page(page, place["url"], "h1.DUwDvf")
        out, last_id, skipped, by_author, seen = [], None, collections.Counter(), collections.Counter(), set()
        tabs, complete = [], True
        (d / "photos").mkdir(exist_ok=True)
        for tab in TABS:
            if len(out) >= n or not await open_gallery(page, tab):
                continue
            tabs.append(tab)
            tiles, _ = await list_tiles(page, n * SCAN_FACTOR)
            complete = len(tiles) < n * SCAN_FACTOR  # the whole tab was looked at
            for t in tiles:
                if len(out) >= n:
                    break
                if t["url"] in seen:
                    continue
                seen.add(t["url"])
                last_id = await _one(page, img, place, d, t, px, per_author, last_id, out, skipped, by_author, oldest)
        complete = complete or len(out) >= n
        return {"fetched_at": now(), "tabs": tabs, "complete": complete, "photos": out, "skipped": dict(skipped)}
    finally:
        await page.close()
        await img.close()


async def _one(page: Page, img: Page, place: dict, d, t: dict, px: int, per_author: int, last_id: str | None,
               out: list, skipped: collections.Counter, by_author: collections.Counter, oldest: str) -> str | None:
    """Open one tile, keep its photo; returns the viewer's photo id for the next wait."""
    await page.locator(f'{TILE}[data-photo-index="{t["index"]}"]').first.click()
    meta = await viewer_moved(page, last_id)
    if meta is None:
        skipped["no_metadata"] += 1
        return last_id
    if any(o["photo_id"] == meta["id"] for o in out):
        return meta["id"]
    when = month(meta["taken"]) or month(meta["posted"])
    if when and when < oldest:
        skipped["too_old"] += 1
        return meta["id"]
    who = author_hash(meta["contributor"]) if meta["contributor"] else None
    if who and by_author[who] >= per_author:
        skipped["same_author"] += 1
        return meta["id"]
    url = sized(t["url"], px)
    r = await img.goto(url, timeout=30000)  # a browser tab: direct requests to the image host time out
    if not r or not r.ok or not (r.headers.get("content-type") or "").startswith("image/"):
        skipped["download"] += 1
        return meta["id"]
    f = d / "photos" / f"{safe_name(meta['id'])[:80]}.jpg"
    f.write_bytes(await r.body())
    by_author[who] += 1
    out.append({"photo_id": meta["id"], "file": f"photos/{f.name}", "url": url,
                "kind": "video" if t["video"] else "photo", "author_hash": who,
                "owner": bool(meta["name"]) and norm(meta["name"]) == norm(place.get("name")),
                "posted": meta["posted"], "taken": meta["taken"], "month": when})
    return meta["id"]



async def _place(ctx, d, place: dict, n: int, px: int, root, c: dict, throttle: Throttle) -> None:
    for attempt in range(1, ATTEMPTS + 1):
        async with throttle:
            try:
                res = await scrape_photos(ctx, place, d, n, px)
                write_json(d / FILE, res)
                throttle.success()
                return
            except LoginRequired:
                raise
            except Exception as e:
                if attempt < ATTEMPTS:
                    if type(e).__name__ == "TimeoutError":
                        throttle.blocked()
                    continue
                log_error(root, d.name, "photos", e)
                return
            finally:
                await pause(*c.get("pause_s", (2.0, 5.0)))


async def run(city: str, headed: bool = False, profile=open_profile, limit: int | None = None) -> None:
    _, cfg = load_config(city)
    c, root = cfg["gmaps"], data_dir() / "gmaps"
    n, px = c.get("photos_per_place", 20), c.get("photo_px", 768)
    listed = root / "list" / f"{city}.json"
    keep = {safe_name(r["fid"]) for r in json.loads(listed.read_text(encoding="utf-8"))["items"]} if listed.exists() else None
    todo = []
    for f in sorted((root / "places").glob("*/place.json")):
        if (f.parent / FILE).exists() or (keep is not None and f.parent.name not in keep):
            continue
        todo.append((f.parent, json.loads(f.read_text(encoding="utf-8"))))
    todo = todo[:limit] if limit is not None else todo
    print(f"photos {city}: {len(todo)} places left")
    throttle = Throttle(root / "photos_throttle.json", start=c.get("tabs_start", 1), hi=c.get("photo_tabs", 3),
                        cooldown_s=c.get("cooldown_s", 60), max_cooldown_s=c.get("max_cooldown_s", 900))
    async with profile("gmaps", headed) as ctx:
        await ensure_login(ctx)
        try:
            async with asyncio.TaskGroup() as tg:
                for d, place in todo:
                    tg.create_task(_place(ctx, d, place, n, px, root, c, throttle))
        except* LoginRequired as eg:
            raise eg.exceptions[0] from None
    done = sum((d / FILE).exists() for d, _ in todo)
    print(f"photos {city}: {done}/{len(todo)} done, the rest in errors.jsonl")
