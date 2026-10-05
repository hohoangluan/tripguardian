"""Phase visit: Maps' "people typically spend ... here" line of listed places -> data/gmaps/places/<fid_dir>/visit.json.

Maps prints it under the popular times graph ("Mọi người thường dành tối đa 1 giờ ở đây"), from many visitors' time
on site: the best source for visit length, which reviews rarely state. Only places whose saved page had popular
times are opened (no graph, no line). The line is read from the page text with a regex, not from a selector, and
saved verbatim (`text`; null when the page shows the graph but no line). A page is complete once the popular times
graph rendered (its end signal); a graph that never shows is retried, the last try saved with `complete: false`.
Written once per place.
"""

import asyncio
import json

from playwright.async_api import BrowserContext

from ..common.browser import LoginRequired, open_profile, pause
from ..common.files import data_dir, load_config, log_error, now, safe_name, write_json
from ..common.throttle import Throttle
from .page import ensure_login, open_page

FILE = "visit.json"
ATTEMPTS = 2
GRAPH = "div.C7xf8b"  # popular times graph (crawl.py reads the same block)
_LINE_JS = r"""() => { const m = (document.querySelector('div[role="main"]') || document.body).innerText
  .match(/[^\n]*thường dành[^\n]*/i); return m ? m[0].trim() : null; }"""


async def read_visit(ctx: BrowserContext, url: str) -> dict:
    page = await ctx.new_page()
    try:
        await open_page(page, url, "h1.DUwDvf")
        try:
            await page.wait_for_selector(GRAPH, timeout=15000)
            complete = True
        except Exception:
            complete = False
        await page.wait_for_timeout(500)
        return {"fetched_at": now(), "complete": complete, "text": await page.evaluate(_LINE_JS)}
    finally:
        await page.close()


async def _place(ctx, d, url: str, root, c: dict, throttle: Throttle) -> None:
    for attempt in range(1, ATTEMPTS + 1):
        async with throttle:
            try:
                res = await read_visit(ctx, url)
                if not res["complete"] and attempt < ATTEMPTS:
                    raise RuntimeError("popular times graph did not render")
                write_json(d / FILE, res)
                throttle.success()
                return
            except LoginRequired:
                raise
            except Exception as e:
                if attempt < ATTEMPTS:
                    continue
                log_error(root, d.name, "visit", e)
                return
            finally:
                await pause(*c.get("pause_s", (2.0, 5.0)))


async def run(city: str, headed: bool = False, profile=open_profile, limit: int | None = None) -> None:
    _, cfg = load_config(city)
    c, root = cfg["gmaps"], data_dir() / "gmaps"
    listed = root / "list" / f"{city}.json"
    keep = {safe_name(r["fid"]) for r in json.loads(listed.read_text(encoding="utf-8"))["items"]} if listed.exists() else None
    todo = []
    for f in sorted((root / "places").glob("*/place.json")):
        if (f.parent / FILE).exists() or (keep is not None and f.parent.name not in keep):
            continue
        place = json.loads(f.read_text(encoding="utf-8"))
        if any(place.get("popular_times") or []):
            todo.append((f.parent, place["url"]))
    todo = todo[:limit]
    print(f"visit {city}: {len(todo)} places left")
    throttle = Throttle(root / "visit_throttle.json", start=c.get("keyword_tabs_start", 4), hi=c.get("keyword_tabs", 8),
                        cooldown_s=c.get("cooldown_s", 60), max_cooldown_s=c.get("max_cooldown_s", 900))
    async with profile("gmaps", headed) as ctx:
        await ensure_login(ctx)
        try:
            async with asyncio.TaskGroup() as tg:
                for d, url in todo:
                    tg.create_task(_place(ctx, d, url, root, c, throttle))
        except* LoginRequired as eg:
            raise eg.exceptions[0] from None
    found = sum(bool(json.loads((d / FILE).read_text(encoding="utf-8")).get("text")) for d, _ in todo if (d / FILE).exists())
    print(f"visit {city}: {sum((d / FILE).exists() for d, _ in todo)}/{len(todo)} done, {found} with a time line")
