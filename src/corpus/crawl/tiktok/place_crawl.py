"""Place phase 3, place_crawl: the videos place_filter judged about their place -> the same files crawl.py writes.

Writes only data/tiktok/videos/<video_id>/ (info.json, video.json with comments, video.mp4 = done), so a video that
the city crawl already saved is not opened again. Which place a video belongs to stays in place_filter/<fid_dir>.json.
"""

from ..common.browser import open_profile
from ..common.files import data_dir, load_config
from . import crawl
from .place_filter import kept_videos


async def run(city: str, headed: bool = False, profile=open_profile, profile_name: str | None = None,
             shard: tuple[int, int] | None = None) -> None:
    _, cfg = load_config(city)
    c, root = cfg["tiktok"], data_dir() / "tiktok"
    rows = kept_videos(city)
    todo = [r for r in rows if not (root / "videos" / r["video_id"] / "video.mp4").exists()]
    if shard:
        i, n = shard
        todo = [r for idx, r in enumerate(todo) if idx % n == i]  # same source order every run: no overlap between shards
    print(f"place_crawl {city}: {len(todo)} of {len(rows)} place videos left" + (f" (shard {shard[0]}/{shard[1]})" if shard else ""))
    await crawl.crawl_videos(todo, c, root, headed, profile, profile_name)
    done = sum((root / "videos" / r["video_id"] / "video.mp4").exists() for r in todo)
    print(f"place_crawl {city}: {done}/{len(todo)} done, the rest in errors.jsonl")
