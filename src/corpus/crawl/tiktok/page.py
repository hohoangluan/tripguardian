"""Browser steps shared by the phases that open TikTok pages: login check and API-driven list collection."""

import asyncio
import json
from urllib.parse import parse_qs, urlparse

from playwright.async_api import BrowserContext

from ..common.browser import LoginRequired, is_captcha, wait_for_person


ITEM_JS = """() => { try { return JSON.parse(document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__').textContent)
  .__DEFAULT_SCOPE__['webapp.video-detail'].itemInfo.itemStruct ?? null; } catch { return null; } }"""


async def ensure_login(ctx: BrowserContext) -> None:
    # Logged-out sessions get empty search results instead of an error.
    if not any(c["name"] == "sessionid" for c in await ctx.cookies("https://www.tiktok.com")):
        raise LoginRequired("tiktok")


def is_block(e: Exception) -> bool:
    # Throttled sessions get error pages, pages that never finish rendering, or empty API bodies.
    return ("ERR_HTTP_RESPONSE_CODE_FAILURE" in str(e) or "empty body" in str(e)
            or type(e).__name__ == "TimeoutError")


async def _expand(page, selector: str) -> int:
    """Click every visible "Xem ..." reply button (never "Ẩn", which collapses); returns clicks made."""
    n = 0
    for b in await page.locator(selector).filter(has_text="Xem", visible=True).all():
        try:
            await b.click(timeout=2000)
            n += 1
        except Exception:
            pass  # scrolled away or already expanding
    return n


ROUND_S = 1.5  # max wait for the next API page after each scroll
STALE_ROUNDS = 10  # safety net only: rounds with nothing new before an unfinished list is given up (incomplete)
FIRST_ROUNDS = 40  # rounds to wait for the first page (~60 s): slow networks take 20+ s
_HEAVY = {"media"}  # video streams; the mp4 is fetched directly. Blocking images/fonts hides the comment button.
_RENDERING = {"media", "image", "font", "stylesheet"}  # open_item reads a <script> tag's text: nothing here renders


async def _skip_heavy(route) -> None:
    if route.request.resource_type in _HEAVY:
        await route.abort()
    else:
        await route.continue_()


async def _skip_rendering(route) -> None:
    if route.request.resource_type in _RENDERING:
        await route.abort()
    else:
        await route.continue_()


STATE_WAIT_S = 20.0  # page JSON can land well after domcontentloaded, above all right after a captcha
STATE_POLL_S = 0.5


CAPTCHA_APPEAR_S = 12.0  # the slider shows a few seconds after the search API already answered with an empty body


async def _person_solved(page) -> bool:
    """True when the page shows a captcha (given CAPTCHA_APPEAR_S to appear) and a person cleared it (headless runs
    raise LoginRequired instead)."""
    for _ in range(max(1, int(CAPTCHA_APPEAR_S / STATE_POLL_S))):
        try:
            if await is_captcha(page):
                await wait_for_person(page, "tiktok")
                return True
        except LoginRequired:
            raise
        except Exception:
            return False
        await asyncio.sleep(STATE_POLL_S)
    return False


async def _wait_state(page, state_js: str):
    """state_js once it returns something; None if it never does within STATE_WAIT_S.

    The video page reloads itself right after it opens: before the reload the JSON is missing, during it evaluate
    raises; both mean "not yet".
    """
    for _ in range(max(1, int(STATE_WAIT_S / STATE_POLL_S))):
        try:
            state = await page.evaluate(state_js)
            if state:
                return state
            await wait_for_person(page, "tiktok")
        except Exception as e:
            if "context was destroyed" not in str(e):
                raise
        await asyncio.sleep(STATE_POLL_S)
    return None


async def _next_response(arrived: asyncio.Event, timeout: float) -> bool:
    try:
        await asyncio.wait_for(arrived.wait(), timeout)
        return True
    except TimeoutError:
        return False
    finally:
        arrived.clear()


def _list_of(url: str) -> str:
    """The comment a reply page belongs to (its comment_id); "" for other lists."""
    return parse_qs(urlparse(url).query).get("comment_id", [""])[0]


def main_ended(rows: list[dict], ended: set[str]) -> bool:
    return "" in ended


async def open_item(ctx: BrowserContext, url: str) -> dict | None:
    """The video page's item JSON (desc, stats, playAddr) with no comment panel opened — for the video-only crawl
    that defers the costly comment fetch until place_verify confirms the video is worth it."""
    page = await ctx.new_page()
    await page.route("**/*", _skip_rendering)
    try:
        await page.goto(url, wait_until="domcontentloaded")
        return await _wait_state(page, ITEM_JS)
    finally:
        await page.close()


async def collect(ctx: BrowserContext, url: str, apis: dict, key: str, limit: int | None, click: str | None = None,
                  scroll_to: str | None = None, expand: str | None = None, state_js: str | None = None,
                  done=main_ended) -> tuple[list[dict], object, bool]:
    """Rows served by the page's APIs while scrolling, state_js once it returns a value, and whether the list is complete.

    apis maps API path -> parser returning (rows, has_more). The page is left on explicit end signals, not on
    silence: complete = done(rows, ended) and no API request in flight, where ended holds "" once the first API
    said has_more=0 and the comment_id of each reply list that did. Only if nothing new arrives for STALE_ROUNDS
    does it give up with complete=False. An empty API body (throttled session) raises at once.
    """
    page = await ctx.new_page()
    await page.route("**/*", _skip_heavy if click else _skip_rendering)  # no click = no button that images hide
    got: dict[str, dict] = {}  # by id: TikTok re-sends pages it already served
    ended: set[str] = set()
    pending, blocked = [0], [False]
    arrived = asyncio.Event()
    main = next(iter(apis))

    def api_of(u: str) -> str | None:
        path = urlparse(u).path.rstrip("/")
        return next((a for a in apis if a.rstrip("/") == path), None)  # exact: reply path extends comment path

    def on_request(req):
        if api_of(req.url):
            pending[0] += 1

    def on_failed(req):
        if api_of(req.url):
            pending[0] = max(0, pending[0] - 1)

    async def on_response(r):
        api = api_of(r.url)
        if api is None:
            return
        try:
            body = await r.text()
            if not body.strip():
                blocked[0] = True
                return
            rows, has_more = apis[api](json.loads(body))
        except Exception:
            return
        finally:
            pending[0] = max(0, pending[0] - 1)
            arrived.set()
        got.update((row[key], row) for row in rows if row[key] not in got)
        if not has_more:
            ended.add("" if api == main else _list_of(r.url))

    page.on("request", on_request)
    page.on("requestfailed", on_failed)
    page.on("response", on_response)
    try:
        await page.goto(url, wait_until="domcontentloaded")
        state = await _wait_state(page, state_js) if state_js else None
        if click:
            button = page.locator(click).filter(visible=True).first
            await button.wait_for(timeout=15000)
            await wait_for_person(page, "tiktok")
            await button.click(timeout=15000)
        complete, seen, stale = False, 0, 0
        while True:
            await _next_response(arrived, ROUND_S)
            if blocked[0] and await _person_solved(page):  # the empty body was a captcha: lists load again after it
                blocked[0] = False
                await page.reload(wait_until="domcontentloaded")
                continue
            if blocked[0]:
                raise RuntimeError(f"{urlparse(url).path}: API returned an empty body (blocked)")
            await wait_for_person(page, "tiktok")
            rows = list(got.values())
            if (limit and len(rows) >= limit) or (done(rows, ended) and not pending[0]):
                complete = True
                break
            opened = await _expand(page, expand) if expand else 0
            stale, seen = (0 if opened or len(got) != seen else stale + 1), len(got)
            if stale >= (STALE_ROUNDS if got else FIRST_ROUNDS):
                break  # no end signal and nothing new: give up, reported as incomplete
            if scroll_to and await page.locator(scroll_to).count():  # side panel: the page itself does not scroll
                try:
                    await page.locator(scroll_to).last.scroll_into_view_if_needed(timeout=5000)
                except Exception:
                    pass  # list re-rendered under us; the next round retries
            else:
                await page.mouse.wheel(0, 6000)
        rows = list(got.values())
        return (rows[:limit] if limit else rows), state, complete
    finally:
        await page.close()
