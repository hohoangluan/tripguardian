"""Place phase 5, comments_crawl: comments for videos place_verify confirmed show the place they were matched to —
the costly part (200 comments + nested replies per video), skipped by place_crawl for every video until something
actually needs it. A video is skipped here if it has no "yes" verdict yet (still waiting on asr/asr_check/place_verify,
or place_verify said "no"/"unsure") or its comments are already complete.
"""

import json

from ..common.browser import open_profile
from ..common.files import data_dir, load_config
from . import crawl
from .place_verify import evidence_pairs


async def run(city: str, headed: bool = False, profile=open_profile, profile_name: str | None = None,
             shard: tuple[int, int] | None = None) -> None:
    _, cfg = load_config(city)
    c, root = cfg["tiktok"], data_dir() / "tiktok"
    want = sorted({video_id for video_id, _fid in evidence_pairs()})
    todo = []
    for video_id in want:
        d = root / "videos" / video_id
        f = d / "video.json"
        if not f.exists() or not (d / "video.mp4").exists():
            continue
        v = json.loads(f.read_text(encoding="utf-8"))
        if v.get("comments_complete") is True:
            continue
        todo.append({"video_id": video_id, "url": v["video_url"]})
    if shard:
        i, n = shard
        todo = [r for idx, r in enumerate(todo) if idx % n == i]  # same source order every run: no overlap between shards
    print(f"comments_crawl {city}: {len(todo)} videos left" + (f" (shard {shard[0]}/{shard[1]})" if shard else ""))
    await crawl.crawl_comments(todo, c, root, headed, profile, profile_name)
    done = sum(json.loads((root / "videos" / r["video_id"] / "video.json").read_text(encoding="utf-8"))
              .get("comments_complete") is True for r in todo)
    print(f"comments_crawl {city}: {done}/{len(todo)} done, the rest in errors.jsonl")
