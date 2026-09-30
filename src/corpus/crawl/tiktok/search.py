"""Phase 1, search: every query of config/queries.yaml -> the videos TikTok's search API returns.

Writes only data/tiktok/search/<city>/<query_slug>.jsonl: {at, group, query, items:[{video_id, url, author_id, desc,
created_at, hashtags, photo}]}. A query already in its file is not searched again (delete the file to refresh).
"""

import asyncio
from urllib.parse import quote

from playwright.async_api import BrowserContext

from ..common.browser import LoginRequired, open_profile, pause
from ..common.files import append_jsonl, data_dir, load_config, log_error, now, slug
from .page import collect, ensure_login, is_block

SEARCH_URL = "https://www.tiktok.com/search/video?q="
SEARCH_API = "/api/search/item/full"
ATTEMPTS = 3


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
            "photo": not (it.get("video") or {}).get("playAddr"),  # photo post: no mp4
        })
    return out


async def search(ctx: BrowserContext, query: str, limit: int) -> list[dict]:
    rows, _, _ = await collect(ctx, SEARCH_URL + quote(query),
                            {SEARCH_API: lambda p: (parse_search(p), bool(p.get("has_more")))}, "video_id", limit)
    return rows


async def run(city: str, headed: bool = False, profile=open_profile) -> None:
    name, cfg = load_config(city)
    c, root = cfg["tiktok"], data_dir() / "tiktok"
    async with profile("tiktok", headed) as ctx:
        await ensure_login(ctx)
        for group, queries in c["queries"].items():
            for q in queries:
                query = q.format(city=name)
                out = root / "search" / city / f"{slug(query)}.jsonl"
                if out.exists():
                    continue
                for attempt in range(1, ATTEMPTS + 1):
                    try:
                        items = await search(ctx, query, c["max_videos_per_query"])
                        if not items:
                            raise RuntimeError("no videos")  # blocked or logged out; retried next run
                        append_jsonl(out, {"at": now(), "group": group, "query": query, "items": items})
                        print(f"search {query!r}: {len(items)} videos")
                        break
                    except LoginRequired:
                        raise
                    except Exception as e:
                        if attempt < ATTEMPTS and "no videos" in str(e):
                            continue  # the page sometimes reloads itself and never calls the search API
                        if attempt < ATTEMPTS and is_block(e):
                            await asyncio.sleep(c.get("cooldown_s", 60))
                            continue
                        log_error(root, query, "search", e)
                        break
                await pause(*c.get("pause_s", (0.0, 0.0)))
