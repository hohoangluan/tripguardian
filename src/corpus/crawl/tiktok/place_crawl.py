"""Place phase 3, place_crawl: the videos place_filter judged about their place -> the same files crawl.py writes.

Writes only data/tiktok/videos/<video_id>/ (info.json, video.json, video.mp4 = done), so a video that the city crawl
already saved is not opened again. Which place a video belongs to stays in place_filter/<fid_dir>.json. Comments are
NOT fetched here (comments_complete: null) — that is the costly part (200 comments + nested replies), so it waits
for place_verify to confirm the video is worth it; see crawl_comments.
"""

import json

from ..common.browser import open_profile
from ..common.files import data_dir, load_config
from . import crawl
from .place_filter import kept_videos


async def run(city: str, headed: bool = False, profile=open_profile, profile_name: str | None = None,
             shard: tuple[int, int] | None = None, limit: int | None = None) -> None:
    _, cfg = load_config(city)
    c, root = cfg["tiktok"], data_dir() / "tiktok"
    rows = kept_videos(city, cap_per_place=c.get("crawl_videos_per_place"))
    removed = {f.parent.name for f in (root / "videos").glob("*/video.json")
               if json.loads(f.read_text(encoding="utf-8")).get("clip_removed")}  # verified; clip deleted on purpose
    todo = [r for r in rows if r["video_id"] not in removed and not (root / "videos" / r["video_id"] / "video.mp4").exists()]
    if shard:
        i, n = shard
        todo = [r for idx, r in enumerate(todo) if idx % n == i]  # same source order every run: no overlap between shards
    if limit:
        todo = todo[:limit]  # a batch: the caller verifies and deletes these clips before the next one, to keep the disk free
    print(f"place_crawl {city}: {len(todo)} of {len(rows)} place videos left" + (f" (shard {shard[0]}/{shard[1]})" if shard else ""))
    await crawl.crawl_videos(todo, c, root, headed, profile, profile_name, with_comments=False)
    done = sum((root / "videos" / r["video_id"] / "video.mp4").exists() for r in todo)
    print(f"place_crawl {city}: {done}/{len(todo)} done, the rest in errors.jsonl")
