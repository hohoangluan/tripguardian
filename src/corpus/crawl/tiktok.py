"""TikTok: search by query, then keep each video's item JSON, comments and mp4 under data/tiktok/."""

import asyncio
from urllib.parse import quote, urlparse

from playwright.async_api import BrowserContext

from .browser import LoginRequired, open_profile, pause, wait_for_person
from .files import append_jsonl, author_hash, data_dir, load_config, log_error, now, slug, write_bytes, write_json
from .throttle import Throttle

SEARCH_URL = "https://www.tiktok.com/search/video?q="
SEARCH_API = "/api/search/item/full"
COMMENT_API = "/api/comment/list/"
REPLY_API = "/api/comment/list/reply/"
# Comments load only after the panel opens: the icon, or the "Bình luận" panel tab in the newer layout.
COMMENT_BUTTON = '[data-e2e="comment-icon"], :text-is("Bình luận")'
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


_COMMENT_KEYS = ("comment_id", "author_hash", "text", "created_at", "likes")


def video_doc(it: dict, rows: list[dict], video_path: str) -> dict:
    """One readable record per video: url, local path, caption, stats, comments with their replies nested."""
    top = [{**{k: r.get(k) for k in _COMMENT_KEYS}, "replies": []} for r in rows if not r.get("parent_id")]
    by_id = {c["comment_id"]: c for c in top}
    for r in rows:
        parent = r.get("parent_id")
        if not parent:
            continue
        reply = {k: r.get(k) for k in _COMMENT_KEYS}
        if parent in by_id:
            by_id[parent]["replies"].append(reply)
        else:
            top.append({**reply, "reply_to": parent, "replies": []})  # parent not served by TikTok
    return {
        "video_id": it["video_id"], "video_url": it["url"], "video_path": video_path,
        "caption": it.get("desc", ""), "hashtags": it.get("hashtags", []), "author_id": it.get("author_id"),
        "created_at": it.get("created_at"), "stats": (it.get("raw") or {}).get("stats") or {},
        "fetched_at": now(), "comments": top,
    }


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


ROUND_S = 1.5  # max wait for the next API page after each scroll
SETTLE_S = 1.0  # a list is finished once no API response arrived for this long
_HEAVY = {"media"}  # video streams; the mp4 is fetched directly. Blocking images/fonts hides the comment button.


async def _skip_heavy(route) -> None:
    if route.request.resource_type in _HEAVY:
        await route.abort()
    else:
        await route.continue_()


async def _next_response(arrived: asyncio.Event, timeout: float) -> bool:
    try:
        await asyncio.wait_for(arrived.wait(), timeout)
        return True
    except TimeoutError:
        return False
    finally:
        arrived.clear()


async def _collect(ctx: BrowserContext, url: str, apis: dict, key: str, limit: int | None,
                   click: str | None = None, scroll_to: str | None = None, expand: str | None = None) -> list[dict]:
    """apis maps API path -> parser; the first path's has_more decides when the list ends.

    Waits are driven by API responses: each round moves on as soon as the next page lands.
    """
    page = await ctx.new_page()
    await page.route("**/*", _skip_heavy)
    got: dict[str, dict] = {}  # by id: TikTok re-sends pages it already served
    more = [True]
    arrived = asyncio.Event()
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
        arrived.set()

    page.on("response", on_response)
    try:
        await page.goto(url, wait_until="domcontentloaded")
        if click:
            button = page.locator(click).filter(visible=True).first
            await button.wait_for(timeout=15000)
            await wait_for_person(page, "tiktok")
            await button.click(timeout=15000)
        seen = stale = 0
        while True:
            await _next_response(arrived, ROUND_S)
            await wait_for_person(page, "tiktok")
            opened = await _expand(page, expand) if expand else 0
            if ((limit and len(got) >= limit) or not more[0]) and not opened:
                break
            stale, seen = (0 if opened or len(got) != seen else stale + 1), len(got)
            if stale >= (3 if got else 15):  # no new rows for a while: exhausted or stuck (first page may be slow)
                break
            if scroll_to and await page.locator(scroll_to).count():  # side panel: the page itself does not scroll
                try:
                    await page.locator(scroll_to).last.scroll_into_view_if_needed(timeout=5000)
                except Exception:
                    pass  # list re-rendered under us; the next round retries
            else:
                await page.mouse.wheel(0, 6000)
        while await _next_response(arrived, SETTLE_S):  # replies opened in the last round may still be in flight
            pass
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


def _is_block(e: Exception) -> bool:
    # Throttled sessions get error pages or pages that never finish rendering.
    return "ERR_HTTP_RESPONSE_CODE_FAILURE" in str(e) or type(e).__name__ == "TimeoutError"


ATTEMPTS = 3  # per video / search, when the failure looks like a block


async def _search(ctx: BrowserContext, query: str, limit: int, root, throttle: Throttle) -> list[dict]:
    for attempt in range(1, ATTEMPTS + 1):
        async with throttle:
            try:
                items = await search(ctx, query, limit)
                throttle.success()
                return items
            except LoginRequired:
                raise
            except Exception as e:
                if attempt < ATTEMPTS and _is_block(e):
                    throttle.blocked()
                    continue
                log_error(root, query, "search", e)
                return []


async def _video(ctx: BrowserContext, it: dict, root, c: dict, throttle: Throttle,
                 downloads: asyncio.Semaphore) -> bool:
    """True once the video is done. The tab is released before the mp4 download, which needs no page."""
    d = root / "videos" / it["video_id"]
    if (d / "video.mp4").exists():
        return True
    if not it["play_url"]:
        log_error(root, it["video_id"], "video", ValueError("no video file (photo post)"))
        return False
    for attempt in range(1, ATTEMPTS + 1):
        async with throttle:
            try:
                write_json(d / "info.json", it["raw"])
                cm = await comments(ctx, it["url"], c["max_comments_per_video"])
                if not cm and (it["raw"].get("stats") or {}).get("commentCount"):
                    raise RuntimeError("no comments captured")  # panel blocked
                write_json(d / "video.json", video_doc(it, cm, f"tiktok/videos/{it['video_id']}/video.mp4"))
                throttle.success()
                break
            except LoginRequired:
                raise
            except Exception as e:
                if attempt < ATTEMPTS and _is_block(e):
                    throttle.blocked()
                    continue
                log_error(root, it["video_id"], "video", e)
                return False
            finally:
                await pause(*c.get("pause_s", (0.0, 0.0)))
    async with downloads:
        try:
            await download_video(ctx, it["play_url"], d / "video.mp4")  # written last = done
            return True
        except Exception as e:
            log_error(root, it["video_id"], "download", e)
            return False


async def run(city: str, headed: bool = False, profile=open_profile) -> None:
    """Every query, then a second pass over videos that did not finish; safe to rerun (done videos are skipped)."""
    name, cfg = load_config(city)
    c, root = cfg["tiktok"], data_dir() / "tiktok"
    throttle = Throttle(root / "throttle.json", start=c.get("tabs_start", 2), hi=c.get("tabs", 1),
                        cooldown_s=c.get("cooldown_s", 60), max_cooldown_s=c.get("max_cooldown_s", 900))
    downloads = asyncio.Semaphore(c.get("downloads", 4))
    found: dict[str, dict] = {}  # video_id -> item, across queries: a video is fetched once per run
    async with profile("tiktok", headed) as ctx:
        await ensure_login(ctx)
        try:
            async with asyncio.TaskGroup() as tg:  # searches feed videos into shared tabs; one LoginRequired stops all
                for group, queries in c["queries"].items():
                    for q in queries:
                        query = q.format(city=name)
                        items = await _search(ctx, query, c["max_videos_per_query"], root, throttle)
                        append_jsonl(root / "search" / city / f"{slug(query)}.jsonl", {
                            "at": now(), "group": group, "query": query,
                            "items": [{k: v for k, v in it.items() if k not in ("raw", "play_url")} for it in items]})
                        for it in items:
                            if it["video_id"] not in found:
                                found[it["video_id"]] = it
                                tg.create_task(_video(ctx, it, root, c, throttle, downloads))
            left = [it for it in found.values() if not (root / "videos" / it["video_id"] / "video.mp4").exists()]
            async with asyncio.TaskGroup() as tg:  # second pass
                for it in left:
                    tg.create_task(_video(ctx, it, root, c, throttle, downloads))
        except* LoginRequired as eg:
            raise eg.exceptions[0] from None
    done = sum((root / "videos" / v / "video.mp4").exists() for v in found)
    print(f"tiktok: {done}/{len(found)} videos done, {len(found) - done} left for the next run (see errors.jsonl)")
