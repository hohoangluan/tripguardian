"""One persistent Chrome profile per source (.browser/<source>/), logged in once by a person."""

import asyncio
import random
import re
from contextlib import asynccontextmanager

from playwright.async_api import BrowserContext, Page, async_playwright

from .files import ROOT

LOGIN_URL = {
    "tiktok": "https://www.tiktok.com/login",
    "gmaps": "https://accounts.google.com/ServiceLogin?continue=https://www.google.com/maps",
}
_CAPTCHA = re.compile(r"Kéo thanh trượt|Drag the slider|Verify to continue|Xác minh để tiếp tục"
                      r"|unusual traffic|lưu lượng truy cập bất thường")  # last two: Google /sorry/ page


_ua: dict = {}


async def _user_agent(p, headless: bool) -> str | None:
    """Headless Chrome says "HeadlessChrome" in its user agent and Google then serves Maps in "limited view" (no
    reviews, photos or hours, even signed in): headless runs present the installed Chrome's normal user agent."""
    if not headless:
        return None
    if "ua" not in _ua:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        page = await browser.new_page()
        _ua["ua"] = (await page.evaluate("navigator.userAgent")).replace("HeadlessChrome", "Chrome")
        await browser.close()
    return _ua["ua"]


class LoginRequired(RuntimeError):
    def __init__(self, source: str):
        super().__init__(f"{source}: login or captcha needed, run `python -m corpus login {source}`")


@asynccontextmanager
async def open_profile(source: str, headed: bool = False):
    async with async_playwright() as p:
        ctx: BrowserContext = await p.chromium.launch_persistent_context(
            ROOT / ".browser" / source, channel="chrome", headless=not headed, locale="vi-VN",
            viewport={"width": 1280, "height": 900}, user_agent=await _user_agent(p, not headed),
            ignore_default_args=["--enable-automation"], args=["--disable-blink-features=AutomationControlled"])
        ctx.headless = not headed
        try:
            yield ctx
        finally:
            await ctx.close()


@asynccontextmanager
async def open_sessions(headed: bool = False):
    """A Chrome without a profile; yields new_session() -> a fresh context with no cookies. For pages that need no
    login: a site limiting one session (Google Maps lists) sees each new context as a new visitor."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome", headless=not headed,
            ignore_default_args=["--enable-automation"], args=["--disable-blink-features=AutomationControlled"])

        async def new_session() -> BrowserContext:
            ctx = await browser.new_context(locale="vi-VN", viewport={"width": 1280, "height": 900},
                                            user_agent=await _user_agent(p, not headed))
            ctx.headless = not headed
            return ctx

        try:
            yield new_session
        finally:
            await browser.close()


async def pause(lo: float = 2.0, hi: float = 5.0) -> None:
    await asyncio.sleep(random.uniform(lo, hi))


async def is_captcha(page: Page) -> bool:
    return await page.get_by_text(_CAPTCHA).count() > 0


async def _is_headless(page: Page) -> bool:
    # headless runs present a normal user agent (_user_agent), so open_profile marks its contexts instead
    return getattr(page.context, "headless", None) or "HeadlessChrome" in await page.evaluate("navigator.userAgent")


async def wait_for_person(page: Page, source: str, wait_s: float = 300) -> None:
    """On a captcha, a person solves it in the headed window; headless runs stop instead."""
    if not await is_captcha(page):
        return
    if await _is_headless(page):
        raise LoginRequired(source)
    print(f"{source}: captcha in the browser window, solve it to continue (waiting {wait_s:.0f}s)...")
    for _ in range(int(wait_s)):
        await asyncio.sleep(1)
        if not await is_captcha(page):
            return
    raise LoginRequired(source)


async def login(source: str, profile: str | None = None) -> None:
    """profile overrides the .browser/<dir> name, so a second account can log in under e.g. "tiktok2"
    while LOGIN_URL still comes from the real source."""
    async with open_profile(profile or source, headed=True) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(LOGIN_URL[source])
        print(f"Log in to {source} in the browser window (solve any captcha), then close the window.")
        await ctx.wait_for_event("close", timeout=0)
