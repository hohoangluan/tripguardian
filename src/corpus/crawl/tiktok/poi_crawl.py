"""Place phase, poi_crawl: the best videos on each mapped place's own TikTok place page -> data/tiktok/videos/.

No search and no login: place_poi gave a Maps place its TikTok place (POI), and the place page, opened in a fresh
logged-out session (served with no captcha, 2026-10-09), lists the videos tagged there, most popular first. The first
`poi_list_items` are ranked in code (score: saves, shares and likes, halved per year of age, times NAMED when the
caption or hashtags name the place; photo posts, ads, very short or long clips left out), one per author, and the
top `poi_download` are downloaded at once in the same session (playAddr is bound to that session's cookies and
expires). Each video gets the files crawl.py writes (info.json = the
list item, video.json with comments_complete null, video.mp4); a video saved before keeps its video.json (transcript,
verdicts) and only gets its clip back. Then data/tiktok/poi_crawl/<fid_dir>.json (written last = the place is done):
{at, fid, name, category, address, poi, listed, videos:[{video_id, url, author_id, desc, hashtags, created_at, score}]}.
asr -> asr_check -> place_verify then judge each video for its place (place_filter.places_by_video reads these files),
and clips picks the ones users see.
"""

import asyncio
import json
import math
import time

from playwright.async_api import BrowserContext

from ..common.browser import LoginRequired, open_sessions, pause
from ..common.files import data_dir, load_config, log_error, now, safe_name, slug, write_json
from ..common.throttle import Throttle
from .crawl import download_video, video_doc
from .page import collect, is_block

PLACE_URL = "https://www.tiktok.com/place/x-{poi}"  # any slug works: TikTok reads the id at the end
POI_API = "/api/poi/item_list/"
MIN_S, MAX_S = 5, 180  # clip length a user will watch on a place card
HALF_LIFE_DAYS = 365  # a place changes: a two-year-old video counts a quarter
NAMED = 4  # a place tag alone is often a viral clip shot nearby (karaoke covers tagged "Xuan Huong Lake")
GENERIC = {"da", "lat", "dalat", "ca", "phe", "cafe", "coffee", "quan", "nha", "hang", "tiem", "the", "and", "va", "ho",
           "lake", "khu", "du", "lich", "restaurant", "shop", "spa", "farm", "garden", "homestay", "hotel", "vietnam"}
ATTEMPTS = 3
ROW_KEYS = ("video_id", "url", "author_id", "desc", "hashtags", "created_at", "score")


def name_keys(*names: str) -> set[str]:
    """Accent-free joined word pairs of the place's names that are not generic ("xuanhuong", "thenhthang"), or a
    lone distinctive word of 5+ letters: found in a caption or hashtag, the video names the place."""
    keys = set()
    for name in names:
        words = slug(name or "").split("-")
        keys |= {a + b for a, b in zip(words, words[1:]) if not {a, b} <= GENERIC}
        keys |= {w for w in words if len(w) >= 5 and w not in GENERIC and len(words) == 1}
    return keys


def names_place(item: dict, keys: set[str]) -> bool:
    text = slug(" ".join([item.get("desc") or ""] + [t.get("hashtagName") or "" for t in item.get("textExtra") or []]))
    return any(k in text.replace("-", "") for k in keys)


def score(item: dict, keys: set[str] = frozenset(), at: float | None = None) -> float | None:
    """How worth showing a listed video is; None when it can't be shown (photo post, ad, too short or long)."""
    video = item.get("video") or {}
    if not video.get("playAddr") or item.get("imagePost") or item.get("isAd"):
        return None
    if not MIN_S <= (video.get("duration") or 0) <= MAX_S:
        return None
    s = item.get("stats") or {}
    n = {k: int(s.get(k) or 0) for k in ("collectCount", "shareCount", "diggCount")}
    age_days = max(0.0, ((at or time.time()) - int(item.get("createTime") or 0)) / 86400)
    named = NAMED if names_place(item, keys) else 1
    return round((n["collectCount"] + n["shareCount"] + n["diggCount"] / 10) * math.pow(0.5, age_days / HALF_LIFE_DAYS)
                 * named, 2)


def parse_list(payload: dict, keys: set[str] = frozenset()) -> tuple[list[dict], bool]:
    rows = []
    for it in payload.get("itemList") or []:
        author = (it.get("author") or {}).get("uniqueId")
        rows.append({"video_id": it["id"], "url": f"https://www.tiktok.com/@{author}/video/{it['id']}",
                     "author_id": author, "desc": it.get("desc", ""), "created_at": it.get("createTime"),
                     "hashtags": [t["hashtagName"] for t in it.get("textExtra") or [] if t.get("hashtagName")],
                     "score": score(it, keys), "item": it})
    return rows, bool(payload.get("hasMore"))


def pick(rows: list[dict], n: int) -> list[dict]:
    """The n best showable rows, one per author (a creator's ten clips of one visit are one view of the place)."""
    out, authors = [], set()
    for r in sorted((r for r in rows if r["score"] is not None), key=lambda r: -r["score"]):
        if r["author_id"] not in authors:
            authors.add(r["author_id"])
            out.append(r)
    return out[:n]


async def list_place(ctx: BrowserContext, poi_id: str, limit: int, keys: set[str] = frozenset()) -> list[dict]:
    rows, _, complete = await collect(ctx, PLACE_URL.format(poi=poi_id), {POI_API: lambda p: parse_list(p, keys)},
                                      "video_id", limit)
    if not rows and not complete:
        raise RuntimeError("place list never loaded")  # a throttled session gets an empty page
    return rows


async def _save(ctx: BrowserContext, row: dict, root, downloads: asyncio.Semaphore) -> None:
    d = root / "videos" / row["video_id"]
    if (d / "video.mp4").exists():
        return
    item = row["item"]
    async with downloads:
        await download_video(ctx, item["video"]["playAddr"], d / "video.mp4")
    write_json(d / "info.json", item)
    doc = d / "video.json"
    v = json.loads(doc.read_text(encoding="utf-8")) if doc.exists() else video_doc(
        row, item, [], f"tiktok/videos/{row['video_id']}/video.mp4", None)
    v.pop("clip_removed", None)  # a clip deleted after its verdict is back
    write_json(doc, v)


async def _place(ctx: BrowserContext, place: dict, root, c: dict, throttle: Throttle,
                 downloads: asyncio.Semaphore) -> None:
    rows = None
    for attempt in range(1, ATTEMPTS + 1):
        async with throttle:
            try:
                rows = await list_place(ctx, place["poi"]["id"], c["poi_list_items"],
                                        name_keys(place["name"], place["poi"]["name"]))
                throttle.success()
                break
            except LoginRequired:
                raise
            except Exception as e:
                if attempt < ATTEMPTS and (is_block(e) or "never loaded" in str(e)):
                    throttle.blocked()
                    continue
                log_error(root, place["fid"], "poi_crawl", e)
                return
            finally:
                await pause(*c.get("pause_s", (0.0, 0.0)))
    best = pick(rows, c["poi_download"])
    results = await asyncio.gather(*(_save(ctx, r, root, downloads) for r in best), return_exceptions=True)
    for r, e in zip(best, results):
        if e:
            log_error(root, r["video_id"], "download", e)
    if any(results):
        return  # listed again next run: the play addresses will be fresh
    write_json(root / "poi_crawl" / f"{safe_name(place['fid'])}.json", {
        "at": now(), **{k: place.get(k) for k in ("fid", "name", "category", "address", "poi")}, "listed": len(rows),
        "videos": [{k: r[k] for k in ROW_KEYS} for r in best]})


async def run(city: str, headed: bool = False, profile_name: str | None = None, sessions=open_sessions,
              limit: int | None = None) -> None:
    """profile_name is ignored: place pages need no account."""
    _, cfg = load_config(city)
    c, root = cfg["tiktok"], data_dir() / "tiktok"
    src = root / "place_poi" / f"{city}.json"
    if not src.exists():
        raise SystemExit(f"no {src}; run `python -m corpus tiktok place_poi --city {city}` first")
    places = [{"fid": fid, **p} for fid, p in json.loads(src.read_text(encoding="utf-8"))["places"].items() if p["poi"]]
    todo = [p for p in places if not (root / "poi_crawl" / f"{safe_name(p['fid'])}.json").exists()]
    print(f"poi_crawl {city}: {len(todo)} of {len(places)} mapped places left" + (f", running {limit}" if limit else ""))
    if limit:
        todo = todo[:limit]  # a batch: verify, pick clips and free the rest before the next one
    throttle = Throttle(root / "poi_crawl_throttle.json", start=c.get("poi_tabs_start", 2), hi=c.get("poi_tabs", 3),
                        cooldown_s=c.get("cooldown_s", 60), max_cooldown_s=c.get("max_cooldown_s", 900))
    downloads = asyncio.Semaphore(c.get("downloads", 4))
    async with sessions(headed) as new_session:
        ctx = await new_session()
        try:
            async with asyncio.TaskGroup() as tg:  # a captcha in a headless run stops all
                for p in todo:
                    tg.create_task(_place(ctx, p, root, c, throttle, downloads))
        except* LoginRequired as eg:
            raise eg.exceptions[0] from None
    done = sum((root / "poi_crawl" / f"{safe_name(p['fid'])}.json").exists() for p in todo)
    print(f"poi_crawl {city}: {done}/{len(todo)} places done, the rest in errors.jsonl")
