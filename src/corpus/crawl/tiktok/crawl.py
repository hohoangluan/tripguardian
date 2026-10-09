"""Phase 3, crawl: open every video of data/tiktok/list/<city>.json and save it.

Writes only data/tiktok/videos/<video_id>/: info.json (item JSON of the video page, fresh stats and play address),
video.json (readable record with comments and nested replies), then video.mp4 (= done; a rerun skips it).
Videos run in parallel tabs (throttle.py); the tab is released before the mp4 download, which needs no page.
"""

import asyncio
import collections
import json
import os

import httpx
from playwright.async_api import BrowserContext

from ..common.browser import LoginRequired, open_profile, pause
from ..common.files import author_hash, data_dir, load_config, log_error, now, write_json
from ..common.throttle import Throttle
from ...review import retry_ids
from .filter import kept_ids
from .page import ITEM_JS, collect, ensure_login, is_block, open_item

COMMENT_API = "/api/comment/list/"
REPLY_API = "/api/comment/list/reply/"
# Comments load only after the panel opens: the icon, or the "Bình luận" panel tab in the newer layout.
COMMENT_BUTTON = '[data-e2e="comment-icon"], :text-is("Bình luận")'
COMMENT_ITEM = '[class*="DivCommentObjectWrapper"]'
REPLY_BUTTON = '[class*="DivViewRepliesContainer"]'  # "Xem N câu trả lời" / "Xem thêm" / "Ẩn"
ATTEMPTS = 3  # per video, when the failure looks like a block
MISS_WINDOW, MISS_LIMIT = 10, 6  # a block when this many of the last MISS_WINDOW video pages had no item data


class NoItemData(RuntimeError):
    """The video page came back without its item: Akamai's answer to a throttled IP (no captcha, no error page), but
    also what a deleted or private video gives."""

    def __init__(self):
        super().__init__("no item data on the video page")


class MissWatchThrottle(Throttle):
    """Throttle that also reads a run of NoItemData as a block: one empty page is a dead video, six of the last ten are
    a throttled IP. Without it the tabs kept at 8 while every video failed (2026-10-07: 50 videos/min, then 16 errors/min)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._recent: collections.deque[bool] = collections.deque(maxlen=MISS_WINDOW)

    def success(self) -> None:
        self._recent.append(False)
        super().success()

    def missed(self) -> bool:
        """Record one empty page; True when the latest ones say the IP is throttled (the window starts over)."""
        self._recent.append(True)
        if len(self._recent) == MISS_WINDOW and sum(self._recent) >= MISS_LIMIT:
            self._recent.clear()
            return True
        return False


def throttled(e: Exception, throttle: Throttle) -> bool:
    """True when the failure means the session is throttled: wait it out and try the video again."""
    if isinstance(e, NoItemData):
        return isinstance(throttle, MissWatchThrottle) and throttle.missed()
    return is_block(e)


POI_KEYS = ("id", "name", "address", "category")


def poi_of(item: dict) -> dict | None:
    """The TikTok place the video is tagged with (its place page lists more videos shot there); None when untagged."""
    poi = item.get("poi") or {}
    return {k: poi.get(k) for k in POI_KEYS} if poi.get("id") else None


_COMMENT_KEYS = ("comment_id", "author_hash", "text", "created_at", "likes", "reply_count")  # reply_count: TikTok's own


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


def video_doc(row: dict, item: dict, rows: list[dict], video_path: str, complete: bool | None = True) -> dict:
    """One readable record per video: url, local path, caption, stats, comments with their replies nested.
    complete=None (comments_complete) means comments were never attempted: the video-only crawl defers them to
    place_verify's "yes" videos (crawl_comments), so an empty comments list here is not a failure."""
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
        "video_id": row["video_id"], "video_url": row["url"], "video_path": video_path,
        "caption": item.get("desc", row.get("desc", "")), "hashtags": row.get("hashtags", []),
        "author_id": row.get("author_id") or (item.get("author") or {}).get("uniqueId"), "created_at": item.get("createTime", row.get("created_at")),
        "stats": item.get("stats") or {}, "poi": poi_of(item), "queries": row.get("queries", []), "fetched_at": now(),
        "comments_complete": complete, "comments": top,
    }


def comments_done(rows: list[dict], ended: set[str]) -> bool:
    """TikTok said has_more=0 for the top-level list and for the replies of every comment that has any (or all its
    replies arrived). Hidden replies still end their list, with fewer rows than reply_count."""
    if "" not in ended:
        return False
    have = collections.Counter(r["parent_id"] for r in rows if r["parent_id"])
    return all(r["comment_id"] in ended or have[r["comment_id"]] >= r["reply_count"]
               for r in rows if not r["parent_id"] and r["reply_count"])


async def comments(ctx: BrowserContext, url: str, limit: int | None) -> tuple[dict | None, list[dict], bool]:
    """The video page's item JSON, its top-level comments and replies (parent_id set), and whether every list ended;
    limit=None reads all."""
    rows, item, complete = await collect(ctx, url, {COMMENT_API: parse_comments, REPLY_API: parse_comments},
                                         "comment_id", limit, click=COMMENT_BUTTON, scroll_to=COMMENT_ITEM,
                                         expand=REPLY_BUTTON, state_js=ITEM_JS, done=comments_done)
    return item, rows, complete


_ua: dict = {}


async def _user_agent(ctx: BrowserContext) -> str:
    """The browser's own user agent, read once on a blank page (a crawl tab may be navigating)."""
    if "ua" not in _ua:
        page = await ctx.new_page()
        try:
            _ua["ua"] = (await page.evaluate("navigator.userAgent")).replace("HeadlessChrome", "Chrome")
        finally:
            await page.close()
    return _ua["ua"]


async def download_video(ctx: BrowserContext, play_url: str, path) -> None:
    """Streamed with the context's cookies, not ctx.request: Playwright's Python transport joins a large body chunk by
    chunk (quadratic), a 55 MB file pinned a core for minutes; streamed it takes ~4 s (2026-10-06)."""
    cookies = {c["name"]: c["value"] for c in await ctx.cookies(play_url)}
    headers = {"Referer": "https://www.tiktok.com/", "User-Agent": await _user_agent(ctx)}
    tmp = path.with_name(path.name + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    # trust_env=False: .env's SSL_CERT_FILE is a private CA bundle for the model endpoint, not for TikTok's CDN
    async with httpx.AsyncClient(cookies=cookies, headers=headers, follow_redirects=True, timeout=300,
                                 trust_env=False) as client:
        async with client.stream("GET", play_url) as r:  # files reach 50+ MB
            if r.status_code != 200:
                raise RuntimeError(f"video HTTP {r.status_code}")
            with open(tmp, "wb") as f:
                async for chunk in r.aiter_bytes(1 << 20):
                    f.write(chunk)
    os.replace(tmp, path)


async def _video(ctx: BrowserContext, row: dict, root, c: dict, throttle: Throttle, downloads: asyncio.Semaphore) -> None:
    d = root / "videos" / row["video_id"]
    for attempt in range(1, ATTEMPTS + 1):
        async with throttle:
            try:
                item, cm, complete = await comments(ctx, row["url"], c["max_comments_per_video"])
                if not item:
                    raise NoItemData()
                if not cm and (item.get("stats") or {}).get("commentCount"):
                    raise RuntimeError("no comments captured")  # panel blocked
                if not complete and attempt < ATTEMPTS:
                    raise RuntimeError("comments incomplete: a list never said has_more=0")
                if not complete:  # last attempt: keep what was served, flagged, and say so
                    log_error(root, row["video_id"], "comments", RuntimeError("comments incomplete after retries"))
                play_url = (item.get("video") or {}).get("playAddr")
                write_json(d / "info.json", item)
                write_json(d / "video.json", video_doc(row, item, cm, f"tiktok/videos/{row['video_id']}/video.mp4",
                                                       complete))
                throttle.success()
                break
            except LoginRequired:
                raise
            except Exception as e:
                # a throttled session also gets empty comment API bodies: cool down instead of running through the list
                if attempt < ATTEMPTS and (throttled(e, throttle) or "no comments captured" in str(e) or "incomplete" in str(e)):
                    throttle.blocked()
                    continue
                log_error(root, row["video_id"], "video", e)
                return
            finally:
                await pause(*c.get("pause_s", (0.0, 0.0)))
    if not play_url:
        log_error(root, row["video_id"], "video", ValueError("no video file (photo post)"))
        return
    async with downloads:
        try:
            await download_video(ctx, play_url, d / "video.mp4")  # written last = done
        except Exception as e:
            log_error(root, row["video_id"], "download", e)


async def _video_only(ctx: BrowserContext, row: dict, root, c: dict, throttle: Throttle, downloads: asyncio.Semaphore) -> None:
    """info.json + video.mp4, comments_complete=None (not attempted): place_crawl's lightweight pass, so comments
    (the costly part) are fetched later only for the videos place_verify confirms (crawl_comments)."""
    d = root / "videos" / row["video_id"]
    play_url = None
    for attempt in range(1, ATTEMPTS + 1):
        async with throttle:
            try:
                item = await open_item(ctx, row["url"])
                if not item:
                    raise NoItemData()
                play_url = (item.get("video") or {}).get("playAddr")
                write_json(d / "info.json", item)
                write_json(d / "video.json", video_doc(row, item, [], f"tiktok/videos/{row['video_id']}/video.mp4", None))
                throttle.success()
                break
            except LoginRequired:
                raise
            except Exception as e:
                if throttled(e, throttle) and attempt < ATTEMPTS:
                    throttle.blocked()
                    continue
                log_error(root, row["video_id"], "video", e)
                return
            finally:
                await pause(*c.get("pause_s", (0.0, 0.0)))
    if not play_url:
        log_error(root, row["video_id"], "video", ValueError("no video file (photo post)"))
        return
    async with downloads:
        try:
            await download_video(ctx, play_url, d / "video.mp4")  # written last = done
        except Exception as e:
            log_error(root, row["video_id"], "download", e)


async def _comments(ctx: BrowserContext, row: dict, root, c: dict, throttle: Throttle) -> None:
    """Comments for a video place_crawl already saved (video.mp4 exists); updates video.json in place, keeping
    what asr/asr_check/place_verify wrote. row needs only video_id and url."""
    d = root / "videos" / row["video_id"]
    for attempt in range(1, ATTEMPTS + 1):
        async with throttle:
            try:
                item, cm, complete = await comments(ctx, row["url"], c["max_comments_per_video"])
                if not item:
                    raise NoItemData()
                if not cm and (item.get("stats") or {}).get("commentCount"):
                    raise RuntimeError("no comments captured")  # panel blocked
                if not complete and attempt < ATTEMPTS:
                    raise RuntimeError("comments incomplete: a list never said has_more=0")
                if not complete:  # last attempt: keep what was served, flagged, and say so
                    log_error(root, row["video_id"], "comments", RuntimeError("comments incomplete after retries"))
                v = json.loads((d / "video.json").read_text(encoding="utf-8"))  # read late: keep other phases' writes
                doc = video_doc(row, item, cm, v.get("video_path", f"tiktok/videos/{row['video_id']}/video.mp4"), complete)
                v.update({k: doc[k] for k in ("caption", "hashtags", "author_id", "created_at", "stats", "poi",
                                              "comments_complete", "comments", "fetched_at")})
                write_json(d / "video.json", v)
                throttle.success()
                return
            except LoginRequired:
                raise
            except Exception as e:
                if attempt < ATTEMPTS and (throttled(e, throttle) or "no comments captured" in str(e) or "incomplete" in str(e)):
                    throttle.blocked()
                    continue
                log_error(root, row["video_id"], "comments", e)
                return
            finally:
                await pause(*c.get("pause_s", (0.0, 0.0)))


async def run(city: str, headed: bool = False, profile=open_profile, profile_name: str | None = None) -> None:
    _, cfg = load_config(city)
    c, root = cfg["tiktok"], data_dir() / "tiktok"
    lst = root / "list" / f"{city}.json"
    if not lst.exists():
        raise SystemExit(f"no {lst}; run `python -m corpus tiktok list --city {city}` first")
    rows = json.loads(lst.read_text(encoding="utf-8"))["items"]
    kept = kept_ids(city)  # videos filter.py judged about travel in the city ("yes" / "unsure"), or a person kept
    fetched = {f.parent.name: json.loads(f.read_text(encoding="utf-8")).get("fetched_at", "")
               for f in (root / "videos").glob("*/video.json")}
    again = retry_ids("video_comments", fetched)  # a person asked to crawl these again (review)
    removed = {f.parent.name for f in (root / "videos").glob("*/video.json")
               if json.loads(f.read_text(encoding="utf-8")).get("clip_removed")}  # finished; clip deleted on purpose
    todo = [r for r in rows if not r.get("photo") and r["video_id"] in kept and r["video_id"] not in removed
            and (r["video_id"] in again or not (root / "videos" / r["video_id"] / "video.mp4").exists())]
    print(f"crawl {city}: {len(todo)} videos left ({sum(bool(r.get('photo')) for r in rows)} photo posts, "
          f"{sum(1 for r in rows if not r.get('photo') and r['video_id'] not in kept)} not kept by filter)")
    await crawl_videos(todo, c, root, headed, profile, profile_name)
    done = sum((root / "videos" / r["video_id"] / "video.mp4").exists() for r in todo)
    print(f"crawl {city}: {done}/{len(todo)} done, the rest in errors.jsonl")


async def crawl_videos(todo: list[dict], c: dict, root, headed: bool, profile, profile_name: str | None = None,
                       with_comments: bool = True) -> None:
    """Every row's video into data/tiktok/videos/<video_id>/, in parallel tabs; failures go to errors.jsonl.
    with_comments=False (place_crawl) skips the comment panel: comments_complete is written None, fetched later
    by crawl_comments only for the videos place_verify confirms."""
    suffix = f"_{profile_name}" if profile_name else ""
    throttle = MissWatchThrottle(root / f"throttle{suffix}.json", start=c.get("tabs_start", 2), hi=c.get("tabs", 1),
                                 cooldown_s=c.get("cooldown_s", 60), max_cooldown_s=c.get("max_cooldown_s", 900))
    downloads = asyncio.Semaphore(c.get("downloads", 4))
    fn = _video if with_comments else _video_only
    async with profile(profile_name or "tiktok", headed) as ctx:
        await ensure_login(ctx)
        try:
            async with asyncio.TaskGroup() as tg:  # one LoginRequired stops all
                for row in todo:
                    tg.create_task(fn(ctx, row, root, c, throttle, downloads))
        except* LoginRequired as eg:
            raise eg.exceptions[0] from None


async def crawl_comments(todo: list[dict], c: dict, root, headed: bool, profile, profile_name: str | None = None) -> None:
    """Comments only, for videos already downloaded and place_verify-approved; its own throttle state since opening
    the comment panel is a different request pattern than the video-only crawl."""
    suffix = f"_{profile_name}" if profile_name else ""
    throttle = Throttle(root / f"comments_throttle{suffix}.json", start=c.get("tabs_start", 2), hi=c.get("tabs", 1),
                        cooldown_s=c.get("cooldown_s", 60), max_cooldown_s=c.get("max_cooldown_s", 900))
    async with profile(profile_name or "tiktok", headed) as ctx:
        await ensure_login(ctx)
        try:
            async with asyncio.TaskGroup() as tg:  # one LoginRequired stops all
                for row in todo:
                    tg.create_task(_comments(ctx, row, root, c, throttle))
        except* LoginRequired as eg:
            raise eg.exceptions[0] from None
