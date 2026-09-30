"""Browser steps shared by the phases that open Maps pages."""

from playwright.async_api import BrowserContext, Page

from ..common.browser import LoginRequired, is_captcha


async def ensure_login(ctx: BrowserContext) -> None:
    # Logged-out Maps is "limited view": no reviews tab, no popular times.
    if not any(c["name"] == "SID" for c in await ctx.cookies("https://www.google.com")):
        raise LoginRequired("gmaps")


SIGN_IN_LINK = 'a[href*="accounts.google.com/ServiceLogin"]'


async def check_signed_in(page: Page) -> None:
    """Google can end the session while the SID cookie stays; signed-out Maps lists fewer places (still with the
    end-of-list marker) and no reviews, so stop instead of saving a thinner copy."""
    if await page.locator(SIGN_IN_LINK).count():
        raise LoginRequired("gmaps")


async def open_page(page: Page, url: str, selector: str, signed_in: bool = True) -> None:
    await page.goto(url, wait_until="domcontentloaded")
    try:
        await page.wait_for_selector(selector, timeout=20000)
    except Exception:
        if await is_captcha(page) or "sorry" in page.url:
            raise LoginRequired("gmaps")
        raise
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
