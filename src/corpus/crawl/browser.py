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
_CAPTCHA = re.compile(r"Kéo thanh trượt|Drag the slider|Verify to continue|Xác minh để tiếp tục")


class LoginRequired(RuntimeError):
    def __init__(self, source: str):
        super().__init__(f"{source}: login or captcha needed, run `python -m corpus login {source}`")


@asynccontextmanager
async def open_profile(source: str, headed: bool = False):
    async with async_playwright() as p:
        ctx: BrowserContext = await p.chromium.launch_persistent_context(
            ROOT / ".browser" / source, channel="chrome", headless=not headed, locale="vi-VN",
            viewport={"width": 1280, "height": 900},
            ignore_default_args=["--enable-automation"], args=["--disable-blink-features=AutomationControlled"])
        try:
            yield ctx
        finally:
            await ctx.close()


async def pause(lo: float = 2.0, hi: float = 5.0) -> None:
    await asyncio.sleep(random.uniform(lo, hi))


async def is_captcha(page: Page) -> bool:
    return await page.get_by_text(_CAPTCHA).count() > 0


async def login(source: str) -> None:
    async with open_profile(source, headed=True) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(LOGIN_URL[source])
        print(f"Log in to {source} in the browser window (solve any captcha), then close the window.")
        await ctx.wait_for_event("close", timeout=0)
