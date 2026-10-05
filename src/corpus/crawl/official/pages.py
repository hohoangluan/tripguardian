"""Phase pages: the website of every listed place -> data/official/pages/<fid_dir>.json.

The website comes from the place's Maps record, so it is the operator's own (docs/CORPUS.md §4, trang official:
`verified`). Social pages, booking / ticket resellers and link shorteners are not official pages and are skipped.
The home page and up to MAX_PAGES - 1 pages it links to on the same site whose link text or address names
tickets, prices, hours, contact or about are opened without a login; each page's visible text is saved as is.
A page is read after its load event (the site's own end signal); a page that never loads fails the place, which
gets no file and one line in data/official/errors.jsonl (retried next run). A saved place is fetched again after
REFRESH_DAYS (hours change; docs/CORPUS.md §5 freshness).
"""

import asyncio
import json
import re
from datetime import datetime, timedelta, UTC
from urllib.parse import urljoin, urlparse

from ..common.browser import open_sessions
from ..common.files import data_dir, load_config, log_error, now, safe_name, write_json

MAX_PAGES = 5
TEXT_CHARS = 40000  # per page; longer text is cut and the page marked `cut`
PARALLEL = 6
REFRESH_DAYS = 90
NOT_OFFICIAL = ("facebook.", "fb.com", "fb.me", "instagram.", "tiktok.", "youtube.", "youtu.be", "zalo.", "linktr.ee",
                "booking.com", "agoda.", "klook.", "traveloka.", "trip.com", "kkday.", "tripadvisor.", "google.",
                "goo.gl", "bit.ly", "shopee.", "foody.", "grab.", "ticket", "getyourguide.", "airbnb.", "expedia.",
                "mytour.", "vntrip.", "ivivu.")
LINK = re.compile(r"giá vé|bảng giá|giá|vé|ticket|price|pricing|fee|giờ mở|giờ hoạt động|thời gian|opening|hours|"
                  r"giới thiệu|about|liên hệ|contact|tham quan|visit|gia-ve|bang-gia|gio-mo|lien-he|gioi-thieu",
                  re.I)
_LINKS_JS = """() => [...document.querySelectorAll('a[href]')].map(a => [a.href, (a.innerText || '').trim().slice(0, 80)])"""


def official_site(url: str | None) -> bool:
    if not url:
        return False
    host = urlparse(url if "//" in url else "http://" + url).netloc.lower()
    return bool(host) and not any(x in host for x in NOT_OFFICIAL)


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def pick_links(base: str, links: list[list[str]], n: int) -> list[str]:
    """Up to n pages of the same site whose address or link text names tickets, prices, hours, contact or about."""
    out, host = [], _host(base)
    for href, text in links:
        url = urljoin(base, href).split("#")[0]
        if not url.startswith("http") or _host(url) != host or url.rstrip("/") == base.rstrip("/"):
            continue
        if re.search(r"\.(pdf|jpe?g|png|webp|zip|docx?)$", url, re.I):
            continue
        if (LINK.search(text) or LINK.search(urlparse(url).path)) and url not in out:
            out.append(url)
    return out[:n]


async def read_page(ctx, url: str) -> dict:
    page = await ctx.new_page()
    try:
        await page.goto(url, wait_until="load", timeout=45000)  # load event: the page says it has arrived
        await page.wait_for_timeout(1500)  # scripts that fill the page right after load
        text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        links = await page.evaluate(_LINKS_JS)
        return {"url": page.url, "title": await page.title(), "text": text[:TEXT_CHARS], "cut": len(text) > TEXT_CHARS,
                "links": links}
    finally:
        await page.close()


async def fetch_site(new_session, website: str) -> list[dict]:
    ctx = await new_session()
    try:
        home = await read_page(ctx, website if "//" in website else "http://" + website)
        pages = [home]
        for url in pick_links(home["url"], home["links"], MAX_PAGES - 1):
            try:
                pages.append(await read_page(ctx, url))
            except Exception:  # a broken sub-page is left out; the home page still counts
                continue
        return [{k: v for k, v in p.items() if k != "links"} for p in pages]
    finally:
        await ctx.close()


def fresh(path) -> bool:
    if not path.exists():
        return False
    at = json.loads(path.read_text(encoding="utf-8")).get("fetched_at")
    return bool(at) and datetime.fromisoformat(at) > datetime.now(UTC) - timedelta(days=REFRESH_DAYS)


async def run(city: str, headed: bool = False, limit: int | None = None) -> dict:
    load_config(city)
    root, gmaps = data_dir() / "official", data_dir() / "gmaps"
    items = json.loads((gmaps / "list" / f"{city}.json").read_text(encoding="utf-8"))["items"]
    todo = []
    for it in items:
        f = gmaps / "places" / safe_name(it["fid"]) / "place.json"
        if not f.exists():
            continue
        place = json.loads(f.read_text(encoding="utf-8"))
        if official_site(place.get("website")) and not fresh(root / "pages" / f"{safe_name(it['fid'])}.json"):
            todo.append(place)
    todo = todo[:limit]
    print(f"official pages {city}: {len(todo)} sites to fetch", flush=True)
    sem, done = asyncio.Semaphore(PARALLEL), 0
    async with open_sessions(headed) as new_session:
        async def one(place):
            nonlocal done
            async with sem:
                try:
                    pages = await fetch_site(new_session, place["website"])
                except Exception as e:
                    log_error(root, safe_name(place["fid"]), "pages", e)
                    return
            write_json(root / "pages" / f"{safe_name(place['fid'])}.json",
                       {"fid": place["fid"], "name": place.get("name"), "website": place["website"],
                        "fetched_at": now(), "pages": pages})
            done += 1

        await asyncio.gather(*(one(p) for p in todo))
    print(f"official pages {city}: {done}/{len(todo)} saved, the rest in data/official/errors.jsonl", flush=True)
    return {"sites": len(todo), "saved": done}
