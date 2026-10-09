"""Flights on one day from Google Flights, through corpus.crawl's public API (RULE.md §2: no deep import).

Each result row carries an aria-label that says everything needed ("Từ 890181 đồng Việt Nam trở lên. Chuyến bay
thẳng của Vietnam Airlines. Rời … lúc 06:10 vào Thứ Năm, tháng 11 12 và đến … lúc 07:05 vào …"), so the parser reads
those labels from the page's HTML, as the search first shows it. A page that shows no row (a captcha, a changed page, a blocked browser) raises
Unavailable: no flight is ever made up.
"""

import asyncio
import html as htmllib
import re
import urllib.parse
from datetime import date

from corpus.crawl import open_sessions

from ..cache import get as cache_get
from ..cache import put as cache_put
from ..http import Unavailable
from ..settings import Settings

URL = "https://www.google.com/travel/flights?q={q}&hl=vi&curr=VND"
ROW = '[aria-label^="Từ "][aria-label*="Rời"]'
LABEL = re.compile(r'aria-label="(Từ [^"]*?Rời [^"]*?)"')
FLIGHT = re.compile(r"Từ (?P<price>[\d.,]+) đồng.*?Chuyến bay (?:(?P<direct>thẳng)|có (?P<stops>\d+) điểm dừng) của (?P<carrier>.+?)\. Rời (?P<src>.+?) lúc (?P<dep>\d{1,2}:\d{2}) "
                    r"vào [^.]*?tháng (?P<dm>\d{1,2}) (?P<dd>\d{1,2}) và đến (?P<dst>.+?) lúc (?P<arr>\d{1,2}:\d{2}) "
                    r"vào [^.]*?tháng (?P<am>\d{1,2}) (?P<ad>\d{1,2})\.")
WAIT_S = 45  # the shared server is often saturated: a results page can take well over 20 s to show its rows
NO_FLIGHT = "no flight could be read from the page"  # loaded, but no row: not a block (scripts/prewarm_transit.py)
BLOCKED = re.compile(r"unusual traffic|lưu lượng truy cập bất thường|captcha", re.I)


def url(src: str, dst: str, day: date) -> str:
    """The search page for that day, also the page the user books on when nothing could be read."""
    return URL.format(q=urllib.parse.quote(f"Flights from {src} to {dst} on {day.isoformat()} one way"))


def _stamp(day: date, month: int, dom: int, clock: str) -> str:
    """The label has no year: the one that puts the date nearest the searched day (a flight landing on 1 Jan)."""
    years = (day.year - 1, day.year, day.year + 1)
    d = min((date(y, month, dom) for y in years), key=lambda x: abs((x - day).days))
    h, m = clock.split(":")
    return f"{d.isoformat()}T{int(h):02d}:{m}"


def parse(page_html: str, day: date) -> list[dict]:
    """[{"mode", "carrier", "depart_at", "arrive_at", "from_point", "to_point", "price_vnd"}] leaving on `day`,
    earliest first; a row whose label does not read as a flight is skipped, not guessed."""
    out, seen = [], set()
    for raw in LABEL.findall(page_html):
        m = FLIGHT.search(htmllib.unescape(raw))
        if not m:
            continue
        try:
            depart = _stamp(day, int(m["dm"]), int(m["dd"]), m["dep"])
            arrive = _stamp(day, int(m["am"]), int(m["ad"]), m["arr"])
        except ValueError:
            continue
        if depart[:10] != day.isoformat():
            continue
        row = {"mode": "plane", "carrier": m["carrier"].split(". ")[0].strip(),  # drop "Do … khai thác" (operator)
               "depart_at": depart, "arrive_at": arrive, "from_point": m["src"].strip(), "to_point": m["dst"].strip(),
               "price_vnd": int(re.sub(r"\D", "", m["price"])) or None, "stops": 0 if m["direct"] else int(m["stops"])}
        key = (row["carrier"], row["depart_at"], row["arrive_at"])  # one carrier, one departure, two connections
        if key not in seen:
            seen.add(key)
            out.append(row)
    return sorted(out, key=lambda r: r["depart_at"])


async def _page(link: str) -> str:
    async with open_sessions() as new_session:
        ctx = await new_session()
        try:
            page = await ctx.new_page()
            await page.goto(link, wait_until="domcontentloaded", timeout=WAIT_S * 1000)
            try:
                await page.wait_for_selector(ROW, timeout=WAIT_S * 1000)
            except Exception:
                if "/sorry/" in page.url or await page.get_by_text(BLOCKED).count():
                    raise RuntimeError("blocked by a captcha page") from None
                return await page.content()  # the page loaded with no flight row: nothing to fly that day
            # every row is already on the page; "Xem các chuyến bay khác" opens another page with none of them
            return await page.content()
        finally:
            await ctx.close()


def flights(src: str, dst: str, day: date, cfg: Settings, fetch: bool = True,
            max_age_s: int | None = None) -> list[dict] | None:
    """Flights src -> dst (IATA codes) leaving on `day`, each with source and fetched_at. fetch=False reads the cache
    only and returns None on a miss; max_age_s (the daily prewarm) treats an entry older than that as a miss. Raises
    Unavailable when the page cannot be read or shows no flight."""
    payload = {"from": src.upper(), "to": dst.upper(), "date": day.isoformat()}
    hit = cache_get("flights", payload, min(cfg.ttl_s["transit"], max_age_s or cfg.ttl_s["transit"]))
    if hit is None:
        if not fetch:
            return None
        try:
            page_html = asyncio.run(_page(url(payload["from"], payload["to"], day)))
        except Exception as e:  # a dead browser, a captcha, a page with no row: none of these invent a flight
            raise Unavailable(f"google flights: {e}") from e
        rows = parse(page_html, day)
        if not rows:
            raise Unavailable(f"google flights: {NO_FLIGHT}")
        hit = cache_put("flights", payload, rows, "google_flights")
    return [{**r, "source": hit["source"], "fetched_at": hit["fetched_at"]} for r in hit["value"]]
