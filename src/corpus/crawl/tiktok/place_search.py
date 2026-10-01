"""Place phase 1, place_search: every place of data/gmaps/list/<city>.json -> the top TikTok videos for its name.

Writes only data/tiktok/place_search/<city>/<fid_dir>.json: {at, fid, name, category, query, items:[{video_id, url,
author_id, desc, created_at, hashtags, photo}]} in TikTok's search order, at most videos_per_place. A place with a file
is not searched again (delete it to refresh). A file is written only once TikTok ended the list or the cap was reached;
a search that stalls is retried and, after the last try, logged to errors.jsonl.
"""

import asyncio
import json
from urllib.parse import quote

from playwright.async_api import BrowserContext

from ..common.browser import LoginRequired, open_profile, pause
from ..common.files import data_dir, load_config, log_error, now, safe_name, slug, write_json
from ..common.throttle import Throttle
from .page import collect, ensure_login, is_block
from .search import SEARCH_API, SEARCH_URL, parse_search

ATTEMPTS = 3


def query_for(name: str, city: str) -> str:
    """The place name, plus the city unless the name already carries it ("Chợ Đà Lạt")."""
    return name if slug(city) in slug(name) else f"{name} {city}"


async def search_place(ctx: BrowserContext, query: str, limit: int) -> tuple[list[dict], bool]:
    rows, _, complete = await collect(ctx, SEARCH_URL + quote(query),
                                      {SEARCH_API: lambda p: (parse_search(p), bool(p.get("has_more")))}, "video_id", limit)
    return rows, complete


async def _place(ctx: BrowserContext, row: dict, out, city_name: str, root, c: dict, throttle: Throttle) -> None:
    query = query_for(row["name"], city_name)
    for attempt in range(1, ATTEMPTS + 1):
        async with throttle:
            try:
                items, complete = await search_place(ctx, query, c["videos_per_place"])
                if not complete:
                    raise RuntimeError("search list never ended")  # no has_more=0 and under the cap
                write_json(out, {"at": now(), "fid": row["fid"], "name": row["name"], "category": row.get("category"),
                                 "query": query, "items": items})
                throttle.success()
                return
            except LoginRequired:
                raise
            except Exception as e:
                if attempt < ATTEMPTS and (is_block(e) or "never ended" in str(e)):
                    throttle.blocked()
                    continue
                log_error(root, row["fid"], "place_search", e)
                return
            finally:
                await pause(*c.get("place_search_pause_s", (0.0, 0.0)))


async def run(city: str, headed: bool = False, profile=open_profile) -> None:
    name, cfg = load_config(city)
    c, root = cfg["tiktok"], data_dir() / "tiktok"
    lst = data_dir() / "gmaps" / "list" / f"{city}.json"
    if not lst.exists():
        raise SystemExit(f"no {lst}; run `python -m corpus gmaps list --city {city}` first")
    out = root / "place_search" / city
    todo = [r for r in json.loads(lst.read_text(encoding="utf-8"))["items"]
            if not (out / f"{safe_name(r['fid'])}.json").exists()]
    print(f"place_search {city}: {len(todo)} places left")
    throttle = Throttle(root / "place_search_throttle.json", start=c.get("place_search_tabs_start", 1),
                        hi=c.get("place_search_tabs", 1), cooldown_s=c.get("cooldown_s", 60),
                        max_cooldown_s=c.get("max_cooldown_s", 900))
    async with profile("tiktok", headed) as ctx:
        await ensure_login(ctx)
        try:
            async with asyncio.TaskGroup() as tg:  # one LoginRequired stops all
                for r in todo:
                    tg.create_task(_place(ctx, r, out / f"{safe_name(r['fid'])}.json", name, root, c, throttle))
        except* LoginRequired as eg:
            raise eg.exceptions[0] from None
    done = sum((out / f"{safe_name(r['fid'])}.json").exists() for r in todo)
    print(f"place_search {city}: {done}/{len(todo)} done, the rest in errors.jsonl")
