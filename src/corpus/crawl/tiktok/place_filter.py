"""Place phase 2, place_filter: an Extractor-role read of each place_search video: is it about that place?

A search for a place name also returns videos of look-alike places, other branches and the city in general. Results
go to data/tiktok/place_filter/<fid_dir>.json: {fid, name, category, address, query, checked_at, model, prompt_hash,
videos:[{video_id, url, desc, hashtags, llm:{relevance, reason}}]}, plus summary.json. A video is judged again only
when its caption, the place's address or the prompt changes; a model error leaves the video out (judged next run).
place_crawl opens only "yes": the video becomes evidence for the place. Prompt: corpus.llm.PLACE_VIDEO_FILTER.
"""

import asyncio
import collections
import json

from ...llm import PLACE_VIDEO_FILTER
from ..common.files import data_dir, load_config, now, safe_name, write_json

KEEP = ("yes",)


def _client():
    return PLACE_VIDEO_FILTER.role.client()


async def classify(client, model: str, place: dict, row: dict, city: str) -> dict:
    return await PLACE_VIDEO_FILTER.ask(client, model, city=city, name=place["name"],
                                        category=place.get("category") or "unknown",
                                        address=place.get("address") or "unknown", desc=row.get("desc") or "",
                                        hashtags=" ".join(f"#{h}" for h in row.get("hashtags") or []))


def address(fid: str) -> str | None:
    """The Maps address, once gmaps crawl saved the place (the list has none)."""
    f = data_dir() / "gmaps" / "places" / safe_name(fid) / "place.json"
    return json.loads(f.read_text(encoding="utf-8")).get("address") if f.exists() else None


ROW_KEYS = ("video_id", "url", "desc", "hashtags", "author_id", "created_at")  # search row fields carried along


def kept_videos(city: str, cap_per_place: int | None = None) -> list[dict]:
    """Search rows of the videos judged about their place, one per video, with every place and query they matched.
    cap_per_place keeps only each place's own first N "yes" videos (place_search's TikTok-relevance order, kept as
    the "yes" order within each place_filter file) — a video shared by several places counts toward each place's
    own cap independently, so it survives if any one of them still has room."""
    out = data_dir() / "tiktok" / "place_filter"
    rows: dict[str, dict] = {}
    for f in sorted(out.glob("*.json")) if out.exists() else []:
        if f.name == "summary.json":
            continue
        doc = json.loads(f.read_text(encoding="utf-8"))
        kept = [v for v in doc["videos"] if v["llm"]["relevance"] in KEEP]
        for v in kept[:cap_per_place] if cap_per_place is not None else kept:
            r = rows.setdefault(v["video_id"], {**{k: v.get(k) for k in ROW_KEYS},
                                                "queries": [], "places": []})
            r["queries"].append(doc["query"])
            r["places"].append(doc["fid"])
    return list(rows.values())


def places_by_video(city: str) -> dict[str, list[dict]]:
    """video_id -> the places ({fid, name, category, address}) its caption was judged about."""
    out = data_dir() / "tiktok" / "place_filter"
    by: dict[str, list[dict]] = {}
    for f in sorted(out.glob("*.json")) if out.exists() else []:
        if f.name == "summary.json":
            continue
        doc = json.loads(f.read_text(encoding="utf-8"))
        place = {k: doc.get(k) for k in ("fid", "name", "category", "address")}
        for v in doc["videos"]:
            if v["llm"]["relevance"] in KEEP:
                by.setdefault(v["video_id"], []).append(place)
    return by


async def run(city: str) -> dict:
    name, _ = load_config(city)
    root = data_dir() / "tiktok"
    src = root / "place_search" / city
    if not src.exists():
        raise SystemExit(f"no {src}; run `python -m corpus tiktok place_search --city {city}` first")
    client, model = _client()
    sem = asyncio.Semaphore(PLACE_VIDEO_FILTER.parallel)
    errors = [0]

    async def judge(place: dict, row: dict, done: dict):
        old = done.get(row["video_id"])
        if old and old["desc"] == row["desc"]:
            return {**old, **{k: row.get(k) for k in ROW_KEYS}}  # rows judged before author_id was kept
        async with sem:
            try:
                llm = await classify(client, model, place, row, name)
            except Exception:
                errors[0] += 1
                return None
        return {**{k: row.get(k) for k in ROW_KEYS}, "llm": llm}

    async def one(f):
        s = json.loads(f.read_text(encoding="utf-8"))
        place = {**s, "address": address(s["fid"])}
        target = root / "place_filter" / f.name
        prev = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
        same = prev.get("prompt_hash") == PLACE_VIDEO_FILTER.prompt_hash and prev.get("address") == place["address"]
        done = {v["video_id"]: v for v in prev.get("videos", [])} if same else {}
        rows = [r for r in s["items"] if not r.get("photo")]
        videos = [v for v in await asyncio.gather(*(judge(place, r, done) for r in rows)) if v]
        res = {"fid": s["fid"], "name": s["name"], "category": s.get("category"), "address": place["address"],
               "query": s["query"], "checked_at": now(), "model": model, "prompt_hash": PLACE_VIDEO_FILTER.prompt_hash,
               "videos": videos}
        if videos != prev.get("videos") or not same:
            write_json(target, res)
        return res

    results = await asyncio.gather(*(one(f) for f in sorted(src.glob("*.json"))))
    counts = collections.Counter(v["llm"]["relevance"] for r in results for v in r["videos"])
    kept = [sum(v["llm"]["relevance"] in KEEP for v in r["videos"]) for r in results]
    summary = {"at": now(), "places": len(results), "videos": sum(counts.values()), "relevance": dict(counts),
               "kept": sum(kept), "places_without_video": sum(k == 0 for k in kept), "llm_errors": errors[0]}
    write_json(root / "place_filter" / "summary.json", summary)
    print(f"place_filter {city}: {json.dumps(summary, ensure_ascii=False)}")
    return summary
