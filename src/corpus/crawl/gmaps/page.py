"""Browser steps shared by the phases that open Maps pages."""

from playwright.async_api import BrowserContext, Page

import asyncio
import re

from ..common.browser import LoginRequired, is_captcha


async def ensure_login(ctx: BrowserContext) -> None:
    # Logged-out Maps is "limited view": no reviews tab, no popular times.
    if not any(c["name"] == "SID" for c in await ctx.cookies("https://www.google.com")):
        raise LoginRequired("gmaps")


# Map tiles, photos, avatars and fonts: phases reading text only (keywords, extremes) skip them. A rendered map
# costs ~700 MB per headless tab (2026-10-05); only matching URLs reach the handler, the rest load untouched.
_PICTURES = re.compile(r"/maps/vt|/kh/v|googleusercontent\.com|\.(png|jpe?g|gif|webp|woff2?)(\?|$)|/maps/.*tactile")


async def text_only(ctx: BrowserContext) -> None:
    await ctx.route(_PICTURES, lambda route: route.abort())


SIGN_IN_LINK = 'a[href*="accounts.google.com/ServiceLogin"]'
LIMITED = 'text=/xem Google Maps ở chế độ bị hạn chế/'  # signed in, yet no reviews / photos / hours


async def check_signed_in(page: Page) -> None:
    """Google can end the session while the SID cookie stays; signed-out or "limited view" Maps lists fewer places
    (still with the end-of-list marker), no reviews and no photos, so stop instead of saving a thinner copy."""
    if await page.locator(SIGN_IN_LINK).count() or await page.locator(LIMITED).count():
        raise LoginRequired("gmaps")


async def _wait_unblocked(page: Page, wait_s: int = 300) -> None:
    """Google's block page (/sorry/, a captcha): headed, a person solves it in the window; headless stops."""
    if getattr(page.context, "headless", False):
        raise LoginRequired("gmaps")
    print("gmaps: captcha in the browser window, solve it to continue (waiting %ds)..." % wait_s)
    for _ in range(wait_s):
        await asyncio.sleep(1)
        if "sorry" not in page.url and not await is_captcha(page):
            return
    raise LoginRequired("gmaps")


async def open_page(page: Page, url: str, selector: str, signed_in: bool = True) -> None:
    await page.goto(url, wait_until="domcontentloaded")
    try:
        await page.wait_for_selector(selector, timeout=20000)
    except Exception:
        if not (await is_captcha(page) or "sorry" in page.url):
            raise
        await _wait_unblocked(page)
        await page.wait_for_selector(selector, timeout=20000)
    if signed_in:
        await check_signed_in(page)


async def more(page: Page, selector: str, n: int, timeout: int = 4000) -> bool:
    """Wait for more than n matches after a scroll; False when nothing new loads in time."""
    try:
        await page.wait_for_function("([s, n]) => document.querySelectorAll(s).length > n",
                                     arg=[selector, n], timeout=timeout)
        return True
    except Exception:
        return False
