"""Phase 2, filter: an Extractor-role read of each searched place's name and Maps category: is it for visitors?

Search by category also returns offices, shops, companies and houses whose names contain the query ("Công ty Thác
Mơ"). Every distinct place of the search files (in the area, not lodging: list.py drops those anyway) is judged once,
to data/gmaps/filter/<fid_dir>.json and data/gmaps/filter/summary.json; again only when its name or category or the
prompt changes. list.py ranks only kept places: "yes" and "unsure" (too little to tell is not a reason to drop).
Prompt and model settings: corpus.llm.PLACE_FILTER.
"""

import asyncio
import collections
import json

from ...llm import PLACE_FILTER
from ..common.files import data_dir, load_config, now, safe_name, write_json
from .listing import KEEP, is_lodging
from .tiles import in_area


def _client():
    return PLACE_FILTER.role.client()


async def classify(client, model: str, row: dict, city: str) -> dict:
    return await PLACE_FILTER.ask(client, model, city=city, name=row["name"], category=row.get("category") or "none")


def candidates(search_dir, area) -> list[dict]:
    """Distinct places of the search files that list.py could keep, first sighting per fid."""
    rows: dict[str, dict] = {}
    for f in sorted(search_dir.glob("*.jsonl")) if search_dir.exists() else []:
        for line in f.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            if "end" not in rec or rec.get("lodging") or not all("rating" in r for r in rec["items"]):
                continue
            for r in rec["items"]:
                if in_area(r["lat"], r["lng"], area) and not is_lodging(r.get("category")):
                    rows.setdefault(r["fid"], r)
    return list(rows.values())


async def run(city: str) -> dict:
    name, cfg = load_config(city)
    root = data_dir() / "gmaps"
    rows = candidates(root / "search" / city, cfg.get("area"))
    if not rows:
        raise SystemExit(f"no places in {root / 'search' / city}; run `python -m corpus gmaps search --city {city}` first")
    client, model = _client()
    sem = asyncio.Semaphore(PLACE_FILTER.parallel)
    errors = [0]

    async def one(row):
        target = root / "filter" / f"{safe_name(row['fid'])}.json"
        if target.exists():
            done = json.loads(target.read_text(encoding="utf-8"))
            if (done["name"], done["category"]) == (row["name"], row.get("category")) \
                    and done.get("prompt_hash") == PLACE_FILTER.prompt_hash:
                return done
        async with sem:
            try:
                llm = await classify(client, model, row, name)
            except Exception:
                errors[0] += 1
                return None  # no file: judged again next run
        res = {"fid": row["fid"], "name": row["name"], "category": row.get("category"), "url": row.get("url"),
               "checked_at": now(), "model": model, "prompt_hash": PLACE_FILTER.prompt_hash, "llm": llm}
        write_json(target, res)
        return res

    results = [r for r in await asyncio.gather(*(one(r) for r in rows)) if r]
    counts = collections.Counter(r["llm"]["relevance"] for r in results)
    summary = {"at": now(), "places": len(rows), "relevance": dict(counts),
               "kept": sum(counts[k] for k in KEEP), "llm_errors": errors[0],
               "dropped": sorted(f"{r['name']} ({r['category']}): {r['llm']['reason']}"
                                 for r in results if r["llm"]["relevance"] not in KEEP)}
    write_json(root / "filter" / "summary.json", summary)
    print(f"filter {city}: {json.dumps({k: summary[k] for k in ('places', 'relevance', 'kept', 'llm_errors')}, ensure_ascii=False)}")
    return summary
