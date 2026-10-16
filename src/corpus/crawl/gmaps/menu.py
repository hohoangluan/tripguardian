"""Phase menu: the "Thực đơn" tab of each food place -> data/gmaps/places/<fid_dir>/menu.json + menu/.

Answers "which place serves <dish>": dish names are what a person types ("bánh bèo", "sữa đậu nành"). The tab holds
(a) the owner's dish list: section chips ("Các Món Lẩu"), each with dish names (and an English line), plus
"Điểm nổi bật" (dishes Maps marks "Phổ biến"); (b) menu photos ("Menu" carousel), which carry prices and the dishes
the owner never typed in. Prices are kept raw when the list shows one (`price`), never inferred.

Menu photos: the carousel shows 4 of N, so the first is opened and the viewer is stepped N times (ArrowRight); the
biggest image the viewer loads for each step is saved as it arrives (no second download). Read later by an Extractor
(not here: crawl first, the model host is busy with the build).

A place without the tab gets `{"has_menu_tab": false}` so it is not opened again. Written once per place; delete
menu.json to fetch again.
"""

import asyncio
import json
import re

from playwright.async_api import BrowserContext, Page

from ..common.browser import LoginRequired, open_profile, pause
from ..common.files import data_dir, load_config, log_error, now, safe_name, write_json
from ..common.throttle import Throttle
from .gate import GateThrottle
from .keywords import category_group
from .page import CaptchaBlocked, ensure_login, open_page

FILE = "menu.json"
ATTEMPTS = 2
MAIN_TABS = ("Tổng quan", "Thực đơn", "Bài đánh giá", "Giới thiệu")
GROUPS = ("restaurant", "cafe", "dessert", "bar")  # config gmaps.menu_groups overrides
MAX_PHOTOS = 12
_PRICE = re.compile(r"^\d[\d.,\s]*\s?(₫|đ|k|vnd|vnđ)(?!\w)", re.I)
_PHOTO_LABEL = re.compile(r"^Ảnh (\d+)/(\d+)$")
_WIDTH = re.compile(r"=w(\d+)-h(\d+)")
_VIEWER_ID = re.compile(r"!1s([^!?]+)")

MAIN_TEXT_JS = "() => document.querySelector('div[role=\"main\"]')?.innerText ?? ''"
CHIPS_JS = r"""() => {
  const lists = document.querySelectorAll('div[role="main"] [role="tablist"]');
  return lists.length < 2 ? [] : [...lists[1].querySelectorAll('[role="tab"]')].map(t => t.getAttribute('aria-label') || t.innerText.trim());
}"""


def parse_lines(text: str, skip: set[str]) -> list[dict]:
    """Dish lines of a menu view: name, optional English line "(…)", optional price line, "Phổ biến" before a name.
    `skip` = labels that are chrome (tabs, chips, headers)."""
    out, popular = [], False
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line in skip:
            continue
        if line == "Phổ biến":
            popular = True
        elif line.startswith("(") and line.endswith(")") and out:
            out[-1]["name_en"] = line[1:-1].strip()
        elif _PRICE.match(line) and out and "price" not in out[-1]:
            out[-1]["price"] = line
        else:
            out.append({"name": line, "popular": popular})
            popular = False
    return out


async def chip_items(page: Page, chips: list[str], name: str) -> list[dict]:
    before = await page.evaluate(MAIN_TEXT_JS)
    await page.locator('div[role="main"] [role="tablist"]').nth(1).locator('[role="tab"]').get_by_text(name, exact=True).first.click()
    text = before
    for _ in range(12):  # the list swaps in after the click: wait for the text to change (an empty section never does)
        await page.wait_for_timeout(400)
        text = await page.evaluate(MAIN_TEXT_JS)
        if text != before:
            break
    skip = {*MAIN_TABS, *chips, "Menu", "Điểm nổi bật"}
    return parse_lines(text, skip)


async def read_text(page: Page) -> dict:
    """Sections + highlights of the open Thực đơn tab."""
    chips = await page.evaluate(CHIPS_JS)
    skip = {*MAIN_TABS, *chips, "Menu", "Điểm nổi bật"}
    highlights = parse_lines(await page.evaluate(MAIN_TEXT_JS), skip)
    sections = []
    for name in chips:
        if name == "Tổng quan":
            continue
        try:
            sections.append({"name": name, "items": await chip_items(page, chips, name)})
        except Exception as e:  # one chip that will not open must not lose the rest
            sections.append({"name": name, "items": [], "error": type(e).__name__})
    if chips:  # back to the overview chip, where the menu photos are
        await page.locator('div[role="main"] [role="tablist"]').nth(1).locator('[role="tab"]').first.click()
        await page.wait_for_timeout(1500)
    return {"highlights": highlights, "sections": sections}


def best(responses: list[tuple[str, bytes]]) -> tuple[str, bytes] | None:
    """The biggest picture a viewer step loaded: widest `=w<px>` url, ties by body size; a thumbnail (<400 px) is no menu."""
    ranked = []
    for url, body in responses:
        m = _WIDTH.search(url)
        w = int(m.group(1)) if m else 0
        if w >= 400 or len(body) >= 60_000:
            ranked.append((w, len(body), url, body))
    if not ranked:
        return None
    _, _, url, body = max(ranked, key=lambda r: r[:2])
    return url, body


async def read_photos(page: Page, d, limit: int) -> dict:
    labels = await page.evaluate("() => [...document.querySelectorAll('div[role=\"main\"] button[aria-label^=\"Ảnh \"]')].map(b => b.getAttribute('aria-label'))")
    total = max((int(m.group(2)) for l in labels if (m := _PHOTO_LABEL.match(l))), default=0)
    if not total:
        return {"declared": 0, "photos": []}
    want = min(total, limit)
    seen: list[tuple[str, bytes]] = []
    tasks: list[asyncio.Task] = []

    async def take(resp):
        try:
            if "googleusercontent" in resp.url and (resp.headers.get("content-type") or "").startswith("image/"):
                seen.append((resp.url, await resp.body()))
        except Exception:  # a response gone with its navigation
            pass

    page.on("response", lambda r: tasks.append(asyncio.ensure_future(take(r))))
    (d / "menu").mkdir(exist_ok=True)
    out, ids = [], set()
    await page.locator('div[role="main"] button[aria-label^="Ảnh 1/"]').first.click()
    for i in range(want):
        seen.clear()
        got = None
        for _ in range(16):  # the viewer swaps the picture in a moment after the arrow: wait for a big one
            await page.wait_for_timeout(500)
            await asyncio.gather(*tasks)
            got = best(list(seen))
            if got:
                break
        pid = (m.group(1) if (m := _VIEWER_ID.search(page.url)) else f"p{i}")
        if pid in ids:
            break  # the viewer wrapped around
        ids.add(pid)
        if got:
            f = d / "menu" / f"{safe_name(pid)[:80]}.jpg"
            f.write_bytes(got[1])
            out.append({"photo_id": pid, "file": f"menu/{f.name}", "url": got[0], "bytes": len(got[1])})
        await page.keyboard.press("ArrowRight")
    await page.keyboard.press("Escape")
    return {"declared": total, "photos": out}


async def scrape_menu(ctx: BrowserContext, place: dict, d, photos: int) -> dict:
    page = await ctx.new_page()
    try:
        await open_page(page, place["url"], "h1.DUwDvf")
        tab = page.locator('button[role="tab"]').get_by_text("Thực đơn", exact=True)
        if not await tab.count():
            return {"fetched_at": now(), "has_menu_tab": False}
        await tab.first.click()
        await page.wait_for_timeout(3500)
        text = await read_text(page)
        pics = await read_photos(page, d, photos) if photos else {"declared": 0, "photos": []}
        return {"fetched_at": now(), "has_menu_tab": True, **text, "photo_count_declared": pics["declared"],
                "photos": pics["photos"]}
    finally:
        await page.close()


async def _place(ctx, d, place: dict, photos: int, root, c: dict, throttle: Throttle) -> None:
    for attempt in range(1, ATTEMPTS + 1):
        async with throttle:
            try:
                write_json(d / FILE, await scrape_menu(ctx, place, d, photos))
                throttle.success()
                return
            except LoginRequired:
                raise
            except Exception as e:
                if attempt < ATTEMPTS:
                    if type(e).__name__ == "TimeoutError" or isinstance(e, CaptchaBlocked):
                        throttle.blocked()
                    continue
                log_error(root, d.name, "menu", e)
                return
            finally:
                await pause(*c.get("pause_s", (2.0, 5.0)))


def todo_places(root, listed_ids: set[str] | None, groups: set[str]) -> list[tuple]:
    out = []
    for f in sorted((root / "places").glob("*/place.json")):
        if listed_ids is not None and f.parent.name not in listed_ids:
            continue
        if (f.parent / FILE).exists():
            continue
        place = json.loads(f.read_text(encoding="utf-8"))
        if category_group(place.get("category")) in groups:
            out.append((f.parent, place))
    return out


async def run(city: str, headed: bool = False, profile=open_profile, limit: int | None = None,
              shard: tuple[int, int] | None = None, profile_name: str | None = None) -> None:
    _, cfg = load_config(city)
    c, root = cfg["gmaps"], data_dir() / "gmaps"
    photos = c.get("menu_photos", MAX_PHOTOS)
    groups = set(c.get("menu_groups", GROUPS))
    listed = root / "list" / f"{city}.json"
    keep = {safe_name(r["fid"]) for r in json.loads(listed.read_text(encoding="utf-8"))["items"]} if listed.exists() else None
    todo = todo_places(root, keep, groups)
    todo = todo[:limit] if limit is not None else todo
    if shard:
        todo = todo[shard[0]::shard[1]]
    print(f"menu {city}: {len(todo)} places left" + (f" (shard {shard[0]}/{shard[1]})" if shard else ""))
    throttle = GateThrottle(root / "menu_throttle.json", start=c.get("tabs_start", 1), hi=c.get("menu_tabs", 3),
                            cooldown_s=c.get("cooldown_s", 60), max_cooldown_s=c.get("max_cooldown_s", 900))
    async with profile(profile_name or "gmaps", headed) as ctx:
        await ensure_login(ctx)
        try:
            async with asyncio.TaskGroup() as tg:
                for d, place in todo:
                    tg.create_task(_place(ctx, d, place, photos, root, c, throttle))
        except* LoginRequired as eg:
            raise eg.exceptions[0] from None
    done = sum((d / FILE).exists() for d, _ in todo)
    print(f"menu {city}: {done}/{len(todo)} done, the rest in errors.jsonl")
