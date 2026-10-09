"""Browser steps shared by the phases that open Maps pages."""

from playwright.async_api import BrowserContext, Page

import asyncio
import re
import time

from ..common.browser import LoginRequired, is_captcha
from .gate import Gate


class CaptchaBlocked(Exception):
    """A captcha nobody solved in time: a block, not a sign-out. The place is retried after the gate's cooldown."""


async def ensure_login(ctx: BrowserContext) -> None:
    # Logged-out Maps is "limited view": no reviews tab, no popular times.
    if not any(c["name"] == "SID" for c in await ctx.cookies("https://www.google.com")):
        raise LoginRequired("gmaps")


# Map tiles, photos, avatars and fonts: phases reading text only (keywords, extremes) skip them. A rendered map
# costs ~700 MB per headless tab (2026-10-05); only matching URLs reach the handler, the rest load untouched.
_PICTURES = re.compile(r"/maps/vt|/kh/v|googleusercontent\.com|\.(png|jpe?g|gif|webp|woff2?)(\?|$)|/maps/.*tactile")


async def _abort(route) -> None:
    try:
        await route.abort()
    except Exception:
        pass  # the tab closed while its picture request was in flight


async def text_only(ctx: BrowserContext) -> None:
    """Blocks pictures on the tabs this process opens, not on the whole context: processes attached to one login
    window share it, and a context route of `extremes` aborted the images `photos` was saving (2026-10-07)."""
    new_page = ctx.new_page

    async def text_page():
        page = await new_page()
        await page.route(_PICTURES, _abort)
        return page

    ctx.new_page = text_page


SIGN_IN_LINK = 'a[href*="accounts.google.com/ServiceLogin"]'
LIMITED = 'text=/xem Google Maps ở chế độ bị hạn chế/'  # signed in, yet no reviews / photos / hours


REVIEWS_TAB = 'button[role="tab"]:has-text("Bài đánh giá")'


async def check_signed_in(page: Page) -> None:
    """Google can end the session while the SID cookie stays; signed-out or "limited view" Maps lists fewer places
    (still with the end-of-list marker), no reviews and no photos, so stop instead of saving a thinner copy."""
    if await page.locator(SIGN_IN_LINK).count():
        raise LoginRequired("gmaps")
    # the lite-mode notice also shows on a signed-in page that has its reviews tab (2026-10-07): that page is fine
    if await page.locator(LIMITED).count() and not await page.locator(REVIEWS_TAB).count():
        raise LoginRequired("gmaps")


async def _wait_unblocked(page: Page, url: str, wait_s: int | None = None) -> None:
    """Google's block page (/sorry/, a captcha): headed, a person solves it in the window, however long that takes
    (wait_s=None; user 2026-10-07), and the tab goes on with its place, no retry; headless stops. While it waits every
    tab of every shard rests (gate hold). A captcha solved in another tab lifts the rest at once and this tab opens
    its page again: the session that passed often lets it through."""
    gate = Gate()
    gate.report_block()  # every tab of every shard rests; waiting on a captcha while others hammer keeps the block
    if getattr(page.context, "headless", False):
        raise LoginRequired("gmaps")
    print("gmaps: captcha in the browser window, solve it to continue" + (f" (waiting {wait_s}s)" if wait_s else "")
          + "...", flush=True)
    try:
        await page.bring_to_front()  # the person's tab: rendered at full priority, not throttled as a background tab
    except Exception:
        pass
    start, seen = time.monotonic(), gate.solved_at()
    while wait_s is None or time.monotonic() - start < wait_s:
        await asyncio.sleep(1)
        try:
            if "sorry" not in page.url and not await is_captcha(page):
                gate.solved()
                return
        except Exception:
            pass  # the page is navigating (the person's submit or our goto)
        gate.hold()
        if gate.solved_at() > seen:
            seen = gate.solved_at()
            try:
                await page.goto(url, wait_until="domcontentloaded")
            except Exception:
                pass
    raise CaptchaBlocked("gmaps captcha not solved in time")


LIMITED_RELOADS = 2


async def open_page(page: Page, url: str, selector: str, signed_in: bool = True) -> None:
    await page.goto(url, wait_until="domcontentloaded")
    try:
        await page.wait_for_selector(selector, timeout=20000)
    except Exception:
        if not (await is_captcha(page) or "sorry" in page.url):
            raise
        await _wait_unblocked(page, url)
        await page.wait_for_selector(selector, timeout=20000)
    for tries in range(LIMITED_RELOADS + 1):
        if not signed_in:
            return
        try:
            await check_signed_in(page)
            return
        except LoginRequired:  # a loaded machine gets the lite page for a signed-in session too (2026-10-07): ask again
            if tries == LIMITED_RELOADS:
                raise
            await page.wait_for_timeout(5000)
            await page.reload(wait_until="domcontentloaded")
            await page.wait_for_selector(selector, timeout=20000)


async def more(page: Page, selector: str, n: int, timeout: int = 4000) -> bool:
    """Wait for more than n matches after a scroll; False when nothing new loads in time."""
    try:
        await page.wait_for_function("([s, n]) => document.querySelectorAll(s).length > n",
                                     arg=[selector, n], timeout=timeout)
        return True
    except Exception:
        return False

