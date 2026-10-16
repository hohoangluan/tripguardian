"""Phase stay_price: the price a night of a lodging whose hotel-list card showed none -> data/gmaps/stay_price/<city>.jsonl.

Maps' hotel list gives a price only for some stays; the detail page of a stay it has booking offers for carries the
same figure as a chip above the tabs ("1.258.600 ₫ · 4 – 5 thg 1": the price a night for Maps' default dates, a
reference and not the trip's dates). A stay with no offers has no "Giá" tab and no chip: nothing is written for it but
`price_vnd: null`, so it is not opened again. One line per place: {fid, at, price_vnd, stay_dates}. listing.build_stay
reads it for the places no hotel-list card priced; never inferred, never an average.

No login: every try runs in a fresh cookie-less context, like search.run_stay.
"""

import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import BrowserContext

from ..common.browser import LoginRequired, open_sessions, pause
from ..common.files import STAY, append_jsonl, data_dir, load_config, log_error, now
from ..common.throttle import Throttle
from .page import CaptchaBlocked, open_page, text_only

ATTEMPTS = 2
SETTLE_S = 14  # the offers load after the page: wait this long for the chip before calling a stay priceless
_AMOUNT = re.compile(r"^(\d{1,3}(?:\.\d{3})+)\s?₫$")
_DATES = re.compile(r"^\d{1,2}\s?–\s?\d{1,2} thg \d{1,2}$|^\d{1,2} thg \d{1,2}\s?–\s?\d{1,2} thg \d{1,2}$")
TEXT_JS = "() => document.body.innerText"


def parse_price(text: str) -> dict | None:
    """{price_vnd, stay_dates} from a stay page's text, None when the page shows no offer. The chip sits just above the
    "Tổng quan" tab. The offer list below it is not read: it also holds "other prices from …" lines, and a chip not
    drawn yet is waited for, not guessed from them."""
    lines = [re.sub(r"[  ]+", " ", l).strip() for l in text.splitlines()]
    lines = [l for l in lines if l]
    if "Tổng quan" not in lines or "Giá" not in lines:
        return None
    tab = lines.index("Tổng quan")
    for i in range(tab - 1, max(tab - 8, -1), -1):
        if m := _AMOUNT.match(lines[i]):
            dates = lines[i + 1] if i + 1 < tab and _DATES.match(lines[i + 1]) else None
            return {"price_vnd": int(m.group(1).replace(".", "")), "stay_dates": dates}
    return None


def load_prices(path: Path) -> dict[str, tuple[str, int]]:
    """fid -> (at, VND a night) of the newest line with a price."""
    out: dict[str, tuple[str, int]] = {}
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        r = json.loads(line)
        if r.get("price_vnd") and (r["fid"] not in out or r["at"] > out[r["fid"]][0]):
            out[r["fid"]] = (r["at"], r["price_vnd"])
    return out


def _checked(path: Path) -> set[str]:
    return {json.loads(l)["fid"] for l in path.read_text(encoding="utf-8").splitlines()} if path.exists() else set()


async def read_price(ctx: BrowserContext, url: str) -> dict | None:
    page = await ctx.new_page()
    try:
        await open_page(page, url, "h1", signed_in=False)
        found = None
        for _ in range(SETTLE_S):
            found = parse_price(await page.evaluate(TEXT_JS))
            if found:
                break
            await page.wait_for_timeout(1000)
        return found
    finally:
        await page.close()


async def run(city: str, headed: bool = False, sessions=open_sessions, limit: int | None = None) -> None:
    _, cfg = load_config(city)
    c, root = cfg["gmaps"], data_dir() / "gmaps"
    listed = root / "list" / f"{city}{STAY}.json"
    if not listed.exists():
        raise SystemExit(f"no {listed}; run `python -m corpus gmaps list --city {city}` first")
    out = root / "stay_price" / f"{city}.jsonl"
    seen = _checked(out)
    todo = [r for r in json.loads(listed.read_text(encoding="utf-8"))["items"]
            if not r.get("price_vnd") and r["fid"] not in seen and r.get("url")]
    todo = todo[:limit] if limit is not None else todo
    print(f"stay_price {city}: {len(todo)} stays without a price left")
    throttle = Throttle(root / "stay_price_throttle.json", start=1, hi=c.get("stay_price_tabs", 8),
                        cooldown_s=c.get("cooldown_s", 60), max_cooldown_s=c.get("max_cooldown_s", 900))
    found = 0

    async def one(new_session, r: dict) -> None:
        nonlocal found
        for attempt in range(1, ATTEMPTS + 1):
            async with throttle:
                ctx = None
                try:
                    ctx = await new_session()
                    await text_only(ctx)  # the chip is text: no map tiles, no photos
                    got = await read_price(ctx, r["url"])
                    append_jsonl(out, {"fid": r["fid"], "at": now(), "price_vnd": got and got["price_vnd"],
                                       "stay_dates": got and got["stay_dates"]})
                    found += bool(got)
                    throttle.success()
                    return
                except (LoginRequired, CaptchaBlocked):
                    raise
                except Exception as e:
                    if attempt < ATTEMPTS and (type(e).__name__ == "TimeoutError" or "net::ERR_" in str(e)):
                        throttle.blocked()
                        continue
                    log_error(root, r["fid"], "stay_price", e)
                    return
                finally:
                    if ctx is not None:
                        await ctx.close()
                    await pause(*c.get("pause_s", (2.0, 5.0)))

    try:
        async with sessions(headed) as new_session, asyncio.TaskGroup() as tg:
            for r in todo:
                tg.create_task(one(new_session, r))
    except* (LoginRequired, CaptchaBlocked) as eg:
        print(f"stay_price {city}: stopped by a captcha ({found} priced so far); run again with --headed to solve it")
        raise eg.exceptions[0] from None
    print(f"stay_price {city}: {found}/{len(todo)} stays have a price on their page")
