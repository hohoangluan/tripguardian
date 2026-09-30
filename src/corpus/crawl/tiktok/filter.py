"""Phase 3, filter: an Extractor-role read of each listed video's caption: is it about travelling in the city?

Search returns videos that only mention the city (personal vlogs, ads, other places). Results go to
data/tiktok/filter/<video_id>.json and data/tiktok/filter/summary.json. A video is judged again only when its
caption or the prompt changes. crawl opens only kept videos: "yes" and "unsure" (too little text to tell is not a
reason to drop). Prompt and model settings: corpus.llm.VIDEO_FILTER.
"""

import asyncio
import collections
import json

from ...llm import VIDEO_FILTER
from ...review import decisions
from ..common.files import data_dir, load_config, now, write_json

KEEP = ("yes", "unsure")


def _client():
    return VIDEO_FILTER.role.client()


async def classify(client, model: str, row: dict, city: str) -> dict:
    return await VIDEO_FILTER.ask(client, model, city=city, desc=row.get("desc") or "",
                                  hashtags=" ".join(f"#{h}" for h in row.get("hashtags") or []))


def kept_ids(city: str) -> set[str]:
    """Videos the filter kept, with a person's keep / drop (review) overriding the model; unjudged videos are not
    kept yet."""
    out = data_dir() / "tiktok" / "filter"
    kept = set()
    for f in out.glob("*.json") if out.exists() else []:
        if f.name != "summary.json" and json.loads(f.read_text(encoding="utf-8"))["llm"]["relevance"] in KEEP:
            kept.add(f.stem)
    person = decisions("video_filter")
    return (kept | {v for v, d in person.items() if d == "keep"}) - {v for v, d in person.items() if d == "drop"}


async def run(city: str) -> dict:
    name, _ = load_config(city)
    root = data_dir() / "tiktok"
    lst = root / "list" / f"{city}.json"
    if not lst.exists():
        raise SystemExit(f"no {lst}; run `python -m corpus tiktok list --city {city}` first")
    rows = [r for r in json.loads(lst.read_text(encoding="utf-8"))["items"] if not r.get("photo")]
    client, model = _client()
    sem = asyncio.Semaphore(VIDEO_FILTER.parallel)
    errors = [0]

    async def one(row):
        target = root / "filter" / f"{row['video_id']}.json"
        if target.exists():
            done = json.loads(target.read_text(encoding="utf-8"))
            if done["desc"] == row["desc"] and done.get("prompt_hash") == VIDEO_FILTER.prompt_hash:
                return done
        async with sem:
            try:
                llm = await classify(client, model, row, name)
            except Exception:
                errors[0] += 1
                return None  # no file: judged again next run
        res = {"video_id": row["video_id"], "desc": row["desc"], "checked_at": now(), "model": model,
               "prompt_hash": VIDEO_FILTER.prompt_hash, "llm": llm}
        write_json(target, res)
        return res

    results = [r for r in await asyncio.gather(*(one(r) for r in rows)) if r]
    counts = collections.Counter(r["llm"]["relevance"] for r in results)
    summary = {"at": now(), "videos": len(rows), "relevance": dict(counts),
               "kept": sum(counts[k] for k in KEEP), "llm_errors": errors[0],
               "dropped": sorted(f"{r['video_id']}: {r['llm']['reason']}" for r in results if r["llm"]["relevance"] not in KEEP)}
    write_json(root / "filter" / "summary.json", summary)
    print(f"filter {city}: {json.dumps({k: summary[k] for k in ('videos', 'relevance', 'kept', 'llm_errors')}, ensure_ascii=False)}")
    return summary
