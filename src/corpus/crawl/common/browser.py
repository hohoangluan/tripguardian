"""One persistent Chrome profile per source (.browser/<source>/), logged in once by a person."""

import asyncio
import json
import os
import random
import re
import time
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
# "chromium" (Playwright's build) where Chrome is not installed, e.g. a Linux server without sudo
CHANNEL = os.environ.get("CORPUS_BROWSER_CHANNEL", "chrome")
# a server with no screen: a person reaches the headless tabs through DevTools (ssh -L <port>, chrome://inspect),
# so captchas and logins wait for them as in a headed window
DEBUG_PORT = os.environ.get("CORPUS_DEBUG_PORT")
# cookies in memory, loaded from and saved back to .browser/<source>.json: a profile directory on NFS stalls
# Chrome (cookie SQLite + disk cache), a page did not load in 200 s that a fresh browser loads in 3 s (2026-10-06)
STATE = os.environ.get("CORPUS_PROFILE_STATE") == "1"
# DevTools URL of a login window that is still open (`corpus login`): crawl inside that browser instead of a copy of its
# cookies. Google ends a session whose cookies moved to another browser within minutes (2026-10-07)
ATTACH_URL = os.environ.get("CORPUS_ATTACH_URL")


async def _user_agent(p, headless: bool) -> str | None:
    """Headless Chrome says "HeadlessChrome" in its user agent and Google then serves Maps in "limited view" (no
    reviews, photos or hours, even signed in): headless runs present the installed Chrome's normal user agent."""
    if not headless:
        return None
    if "ua" not in _ua:
        browser = await p.chromium.launch(channel=CHANNEL, headless=True)
        page = await browser.new_page()
        _ua["ua"] = (await page.evaluate("navigator.userAgent")).replace("HeadlessChrome", "Chrome")
        await browser.close()
    return _ua["ua"]


class LoginRequired(RuntimeError):
    def __init__(self, source: str):
        super().__init__(f"{source}: login or captcha needed, run `python -m corpus login {source}`")


@asynccontextmanager
async def open_profile(source: str, headed: bool = False):
    if STATE:
        async with _open_state(source, headed) as ctx:
            yield ctx
        return
    async with async_playwright() as p:
        ctx: BrowserContext = await p.chromium.launch_persistent_context(
            ROOT / ".browser" / source, channel=CHANNEL, headless=not headed, locale="vi-VN",
            viewport={"width": 1280, "height": 900}, user_agent=await _user_agent(p, not headed),
            ignore_default_args=["--enable-automation"], args=["--disable-blink-features=AutomationControlled"]
            + ([f"--remote-debugging-port={DEBUG_PORT}"] if DEBUG_PORT else []))
        ctx.headless = not headed and not DEBUG_PORT
        try:
            yield ctx
        finally:
            await ctx.close()

STATE_SAVE_S = 60.0  # how often the in-memory cookies are written back to .browser/<name>.json


# tab ids each attached process opened: a login window outlives the processes crawling in it, so tabs of a process that
# died (RAM guard, stall kill, restart) stayed open for good; the next process to attach closes them (2026-10-07)
TABS_DIR = ROOT / ".browser" / "attached"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


async def _reap(cdp, key: str) -> None:
    """Closes the tabs of processes that attached to this browser and died without closing them."""
    for f in TABS_DIR.glob(f"{key}__*.json"):
        pid = int(f.stem.rsplit("__", 1)[1])
        if pid == os.getpid() or _alive(pid):
            continue
        try:
            tids = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            tids = []
        for tid in tids:
            try:
                await cdp.send("Target.closeTarget", {"targetId": tid})
            except Exception:
                pass  # already gone
        f.unlink(missing_ok=True)


@asynccontextmanager
async def _attach(url: str):
    """The signed-in context of a running browser; leaves the browser (and its login tab) open on exit.

    The login window keeps its session in a context made by new_context(); over CDP Playwright files that context's
    pages under its default context, whose own cookies are empty and whose new_page() opens signed-out tabs
    (2026-10-07: every attached run stopped at once with "login needed"). So tabs and cookies go through CDP with
    the real context id."""
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(url)
        ctx = browser.contexts[0]
        cdp = await browser.new_browser_cdp_session()
        mine: set = set()  # target ids this process opened and has not closed
        own = None
        ids = (await cdp.send("Target.getBrowserContexts"))["browserContextIds"]
        if ids:
            cid = ids[0]
            for i in ids:
                ck = (await cdp.send("Storage.getCookies", {"browserContextId": i}))["cookies"]
                if any(k["name"] == "SID" for k in ck):
                    cid = i

            key = re.sub(r"\W", "_", url)
            TABS_DIR.mkdir(parents=True, exist_ok=True)
            await _reap(cdp, key)
            own = TABS_DIR / f"{key}__{os.getpid()}.json"

            def remember() -> None:
                own.write_text(json.dumps(sorted(mine)), encoding="utf-8")

            def forget(page) -> None:
                target_of.pop(page, None)
                if page in owned:
                    mine.discard(owned.pop(page))
                    remember()

            # Matched by target id, not by "the next new page": every process attached to this browser hears of every
            # new tab, so the next page was often another process's tab: two shared one, ~800 leaked (2026-10-07).
            target_of: dict = {}
            owned: dict = {}  # this process's pages -> target id

            async def new_page():
                tid = (await cdp.send("Target.createTarget",
                                      {"url": "about:blank", "browserContextId": cid}))["targetId"]
                mine.add(tid)
                remember()
                for _ in range(300):
                    for page in ctx.pages:
                        if page not in target_of:
                            try:
                                s = await ctx.new_cdp_session(page)
                                target_of[page] = (await s.send("Target.getTargetInfo"))["targetInfo"]["targetId"]
                                await s.detach()
                                page.once("close", forget)
                            except Exception:
                                continue  # closed meanwhile (another process's tab): look again next round
                        if target_of[page] == tid:
                            owned[page] = tid
                            return page
                    await asyncio.sleep(0.1)
                await cdp.send("Target.closeTarget", {"targetId": tid})
                mine.discard(tid)
                remember()
                raise TimeoutError("attached tab never showed up")

            async def cookies(urls=None):
                return (await cdp.send("Storage.getCookies", {"browserContextId": cid}))["cookies"]

            ctx.new_page, ctx.cookies = new_page, cookies
        ctx.headless = False  # a person reaches its tabs through the same DevTools port: captchas wait for them
        try:
            yield ctx
        finally:
            for tid in list(mine):  # tabs left open by an error or a cancel: the login window keeps only its own
                try:
                    await cdp.send("Target.closeTarget", {"targetId": tid})
                except Exception:
                    pass
            if own:
                own.unlink(missing_ok=True)


@asynccontextmanager
async def _open_state(source: str, headed: bool):
    if ATTACH_URL:
        async with _attach(ATTACH_URL) as ctx:
            yield ctx
        return
    path = ROOT / ".browser" / f"{source}.json"
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel=CHANNEL, headless=not headed,
            ignore_default_args=["--enable-automation"], args=["--disable-blink-features=AutomationControlled"]
            + ([f"--remote-debugging-port={DEBUG_PORT}"] if DEBUG_PORT else []))
        ctx = await browser.new_context(storage_state=path if path.exists() else None, locale="vi-VN",
                                        viewport={"width": 1280, "height": 900},
                                        user_agent=await _user_agent(p, not headed))
        ctx.headless = not headed and not DEBUG_PORT

        async def save() -> None:
            tmp = path.with_suffix(".json.tmp")
            await ctx.storage_state(path=tmp)  # refreshed session cookies outlive this run
            os.replace(tmp, path)

        async def save_often() -> None:  # a killed run still keeps a captcha someone solved minutes ago
            while True:
                await asyncio.sleep(STATE_SAVE_S)
                try:
                    await save()
                except Exception:
                    pass

        saver = asyncio.create_task(save_often())
        try:
            yield ctx
        finally:
            saver.cancel()
            await save()
            await browser.close()


@asynccontextmanager
async def open_sessions(headed: bool = False):
    """A Chrome without a profile; yields new_session() -> a fresh context with no cookies. For pages that need no
    login: a site limiting one session (Google Maps lists) sees each new context as a new visitor."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel=CHANNEL, headless=not headed,
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


async def wait_for_person(page: Page, source: str, wait_s: float | None = None) -> None:
    """On a captcha, a person solves it in the headed window, however long that takes (wait_s=None; user 2026-10-07:
    the tab waits and goes on, no retry); headless runs stop instead. Once another tab of the same session gets
    past its captcha, a waiting tab reloads once: the solved session often passes without a second captcha."""
    if not await is_captcha(page):
        return
    if await _is_headless(page):
        raise LoginRequired(source)
    print(f"{source}: captcha in the browser window, solve it to continue"
          + (f" (waiting {wait_s:.0f}s)" if wait_s else "") + "...")
    try:
        await page.bring_to_front()  # the person's tab: rendered at full priority, not throttled as a background tab
    except Exception:
        pass
    start = time.monotonic()
    seen = getattr(page.context, "captcha_solved_at", 0.0)
    while wait_s is None or time.monotonic() - start < wait_s:
        await asyncio.sleep(1)
        try:
            if not await is_captcha(page):
                page.context.captcha_solved_at = time.monotonic()
                return
        except Exception:
            if page.is_closed():
                raise LoginRequired(source)
            continue  # the page is navigating (the person's submit or our reload): look again
        solved = getattr(page.context, "captcha_solved_at", 0.0)
        if solved > seen:
            seen = solved
            try:
                await page.reload(wait_until="domcontentloaded")
            except Exception:
                pass
    raise LoginRequired(source)


async def login(source: str, profile: str | None = None) -> None:
    """profile overrides the .browser/<dir> name, so a second account can log in under e.g. "tiktok2"
    while LOGIN_URL still comes from the real source."""
    async with open_profile(profile or source, headed=not DEBUG_PORT) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(LOGIN_URL[source])
        if DEBUG_PORT:  # a headless context cannot be closed by hand: closing the tab ends the login
            print(f"Log in to {source} through chrome://inspect (port {DEBUG_PORT}), then close that tab.")
            await page.wait_for_event("close", timeout=0)
            return
        print(f"Log in to {source} in the browser window (solve any captcha), then close the window.")
        await ctx.wait_for_event("close", timeout=0)
