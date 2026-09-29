"""TikTok: search by query, then keep each video's item JSON, comments and mp4 under data/tiktok/."""

import asyncio
from urllib.parse import quote, urlparse

from playwright.async_api import BrowserContext

from .browser import LoginRequired, open_profile, pause, wait_for_person
from .files import append_jsonl, author_hash, data_dir, load_config, log_error, now, slug, write_bytes, write_json

SEARCH_URL = "https://www.tiktok.com/search/video?q="
SEARCH_API = "/api/search/item/full"
COMMENT_API = "/api/comment/list/"
REPLY_API = "/api/comment/list/reply/"
COMMENT_BUTTON = '[data-e2e="comment-icon"]'  # comments load only after the panel opens
COMMENT_ITEM = '[class*="DivCommentObjectWrapper"]'
REPLY_BUTTON = '[class*="DivViewRepliesContainer"]'  # "Xem N câu trả lời" / "Xem thêm" / "Ẩn"


def parse_search(payload: dict) -> list[dict]:
    out = []
    for it in payload.get("item_list") or []:
        author = it.get("author") or {}
        out.append({
            "video_id": it["id"],
            "url": f"https://www.tiktok.com/@{author.get('uniqueId')}/video/{it['id']}",
            "author_id": author.get("uniqueId"),
            "desc": it.get("desc", ""),
            "created_at": it.get("createTime"),
            "hashtags": [t["hashtagName"] for t in it.get("textExtra") or [] if t.get("hashtagName")],
            "play_url": (it.get("video") or {}).get("playAddr") or None,  # None for photo posts
            "raw": it,
        })
    return out


def parse_comments(payload: dict) -> tuple[list[dict], bool]:
    comments = [{
        "comment_id": c["cid"],
        "author_hash": author_hash(str((c.get("user") or {}).get("uid", ""))),
        "text": c.get("text", ""),
        "created_at": c.get("create_time"),
        "likes": c.get("digg_count", 0),
        "reply_count": c.get("reply_comment_total", 0),
        "parent_id": None if str(c.get("reply_id", "0")) == "0" else str(c["reply_id"]),  # set on replies
    } for c in payload.get("comments") or []]
    return comments, bool(payload.get("has_more"))


async def ensure_login(ctx: BrowserContext) -> None:
    # Logged-out sessions get empty search results instead of an error.
    if not any(c["name"] == "sessionid" for c in await ctx.cookies("https://www.tiktok.com")):
        raise LoginRequired("tiktok")


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


async def _collect(ctx: BrowserContext, url: str, apis: dict, key: str, limit: int | None,
                   click: str | None = None, scroll_to: str | None = None, expand: str | None = None) -> list[dict]:
    """apis maps API path -> parser; the first path's has_more decides when the list ends."""
    page = await ctx.new_page()
    got: dict[str, dict] = {}  # by id: TikTok re-sends pages it already served
    more = [True]

    main = next(iter(apis))

    async def on_response(r):
        path = urlparse(r.url).path.rstrip("/")
        api = next((a for a in apis if a.rstrip("/") == path), None)  # exact: reply path extends comment path
        if api is None:
            return
        try:
            rows, has_more = apis[api](await r.json())
        except Exception:
            return
        got.update((row[key], row) for row in rows if row[key] not in got)
        if api == main:
            more[0] = has_more

    page.on("response", on_response)
    try:
        await page.goto(url, wait_until="domcontentloaded")
        if click:
            await page.wait_for_timeout(2000)
            await wait_for_person(page, "tiktok")
            await page.locator(click).first.click(timeout=15000)
        seen = stale = 0
        while True:
            await page.wait_for_timeout(1000)
            await wait_for_person(page, "tiktok")
            opened = await _expand(page, expand) if expand else 0
            if ((limit and len(got) >= limit) or not more[0]) and not opened:
                break
            stale, seen = (0 if opened or len(got) != seen else stale + 1), len(got)
            if stale >= (3 if got else 15):  # no new rows for a while: exhausted or stuck (first page may be slow)
                break
            if scroll_to and await page.locator(scroll_to).count():  # side panel: the page itself does not scroll
                await page.locator(scroll_to).last.scroll_into_view_if_needed()
            else:
                await page.mouse.wheel(0, 6000)
        rows = list(got.values())
        return rows[:limit] if limit else rows
    finally:
        await page.close()


async def search(ctx: BrowserContext, query: str, limit: int) -> list[dict]:
    return await _collect(ctx, SEARCH_URL + quote(query),
                          {SEARCH_API: lambda p: (parse_search(p), bool(p.get("has_more")))}, "video_id", limit)


async def comments(ctx: BrowserContext, url: str, limit: int | None) -> list[dict]:
    """Top-level comments and their replies (parent_id set); limit=None reads every page."""
    return await _collect(ctx, url, {COMMENT_API: parse_comments, REPLY_API: parse_comments}, "comment_id", limit,
                          click=COMMENT_BUTTON, scroll_to=COMMENT_ITEM, expand=REPLY_BUTTON)


async def download_video(ctx: BrowserContext, play_url: str, path) -> None:
    r = await ctx.request.get(play_url, headers={"Referer": "https://www.tiktok.com/"}, timeout=300_000)  # files reach 50+ MB
    if not r.ok:
        raise RuntimeError(f"video HTTP {r.status}")
    write_bytes(path, await r.body())


async def _video(ctx: BrowserContext, it: dict, root, c: dict, tabs: asyncio.Semaphore) -> None:
    d = root / "videos" / it["video_id"]
    if (d / "video.mp4").exists():
        return
    async with tabs:
        try:
            if not it["play_url"]:
                raise ValueError("no video file (photo post)")
            write_json(d / "info.json", it["raw"])
            cm = await comments(ctx, it["url"], c["max_comments_per_video"])
            if not cm and (it["raw"].get("stats") or {}).get("commentCount"):
                raise RuntimeError("no comments captured")  # panel blocked; retry next run
            write_json(d / "comments.json", cm)
            await download_video(ctx, it["play_url"], d / "video.mp4")  # written last = done
        except LoginRequired:
            raise
        except Exception as e:
            log_error(root, it["video_id"], "video", e)
        await pause(*c.get("pause_s", (2.0, 5.0)))


async def run(city: str, headed: bool = False, profile=open_profile) -> None:
    name, cfg = load_config(city)
    c, root = cfg["tiktok"], data_dir() / "tiktok"
    tabs = asyncio.Semaphore(c.get("tabs", 1))  # videos of one search open in parallel tabs
    async with profile("tiktok", headed) as ctx:
        await ensure_login(ctx)
        for group, queries in c["queries"].items():
            for q in queries:
                query = q.format(city=name)
                items = await search(ctx, query, c["max_videos_per_query"])
                append_jsonl(root / "search" / city / f"{slug(query)}.jsonl", {
                    "at": now(), "group": group, "query": query,
                    "items": [{k: v for k, v in it.items() if k not in ("raw", "play_url")} for it in items]})
                try:
                    async with asyncio.TaskGroup() as tg:  # one LoginRequired cancels the other tabs
                        for it in items:
                            tg.create_task(_video(ctx, it, root, c, tabs))
                except* LoginRequired as eg:
                    raise eg.exceptions[0] from None
                await pause(*c.get("pause_s", (2.0, 5.0)))
