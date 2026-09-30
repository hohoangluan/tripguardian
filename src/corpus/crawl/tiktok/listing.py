"""Phase 2, list: search files -> one list of unique videos. No browser.

Writes only data/tiktok/list/<city>.json: {at, stats, items:[{video_id, url, author_id, desc, created_at, hashtags,
photo, queries[]}]}, in the order first found. Rebuilt from scratch every time, so it always matches the search files.
"""

import json

from ..common.files import data_dir, now, write_json

KEYS = ("video_id", "url", "author_id", "desc", "created_at", "hashtags", "photo")


def build(search_dir) -> dict:
    items: dict[str, dict] = {}
    raw = 0
    for f in sorted(search_dir.glob("*.jsonl")) if search_dir.exists() else []:
        for line in f.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            for r in rec["items"]:
                raw += 1
                it = items.setdefault(r["video_id"], {**{k: r.get(k) for k in KEYS}, "queries": []})
                if rec["query"] not in it["queries"]:
                    it["queries"].append(rec["query"])
    stats = {"raw": raw, "duplicates": raw - len(items), "videos": len(items)}
    return {"at": now(), "stats": stats, "items": list(items.values())}


def run(city: str) -> dict:
    root = data_dir() / "tiktok"
    lst = build(root / "search" / city)
    write_json(root / "list" / f"{city}.json", lst)
    print(f"list {city}: {lst['stats']}")
    return lst["stats"]
