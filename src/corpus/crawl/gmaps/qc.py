"""Phase 5, qc: rule checks plus a Judge-role review of every crawled place (corpus.llm.PLACE_QC), one file per place.

Results go to data/gmaps/qc/<fid_dir>.json and data/gmaps/qc/summary.json. A place is judged again only when
its place.json was re-fetched.
"""

import asyncio
import collections
import json

from ...llm import PLACE_QC
from ..common.files import data_dir, load_config, now, write_json
from .crawl import count

CORE = ("name", "category", "address", "rating", "review_count")
SAMPLE = 12  # reviews shown to the model per place

def checks(place: dict, reviews: list[dict], cfg: dict) -> list[str]:
    """Rule checks that need no model."""
    issues = [f"missing:{k}" for k in CORE if not place.get(k)]
    area = cfg.get("area")
    if area and not (place.get("lat") is not None and area[0] <= place["lat"] <= area[2] and area[1] <= place["lng"] <= area[3]):
        issues.append("out_of_area")
    want = min(count(place.get("review_count")) or 0, cfg["gmaps"].get("min_reviews_per_place", 0))
    if len(reviews) < want:
        issues.append(f"reviews_short:{len(reviews)}/{want}")
    cut = sum(r["text"].rstrip().endswith("…") for r in reviews)
    if cut:
        issues.append(f"truncated_reviews:{cut}")
    return issues


def _client():
    return PLACE_QC.role.client()


async def judge(client, model: str, place: dict, reviews: list[dict], city: str = "Đà Lạt") -> dict:
    keep = ("name", "category", "address", "description", "rating", "review_count", "price", "hours", "status", "website", "phone")
    sample = [{k: r.get(k) for k in ("review_id", "rating", "text", "details")} for r in reviews if r.get("text")][:SAMPLE]
    return await PLACE_QC.ask(client, model, city=city, place=json.dumps({k: place.get(k) for k in keep}, ensure_ascii=False),
                              reviews=json.dumps(sample, ensure_ascii=False))


async def run(city: str) -> dict:
    name, cfg = load_config(city)
    root = data_dir() / "gmaps"
    out = root / "qc"
    client, model = _client()
    sem = asyncio.Semaphore(PLACE_QC.parallel)

    async def one(p):
        place = json.loads(p.read_text(encoding="utf-8"))
        target = out / f"{p.parent.name}.json"
        if target.exists() and json.loads(target.read_text(encoding="utf-8")).get("fetched_at") == place["fetched_at"]:
            return json.loads(target.read_text(encoding="utf-8"))
        reviews = json.loads((p.parent / "reviews.json").read_text(encoding="utf-8"))
        res = {"fid": place["fid"], "name": place.get("name"), "fetched_at": place["fetched_at"], "checked_at": now(),
               "model": model, "checks": checks(place, reviews, cfg), "llm": None}
        async with sem:
            try:
                res["llm"] = await judge(client, model, place, reviews, name)
            except Exception as e:
                res["llm_error"] = str(e).splitlines()[0][:300]
        write_json(target, res)
        return res

    results = await asyncio.gather(*(one(p) for p in sorted((root / "places").glob("*/place.json"))))
    llm = [r["llm"] for r in results if r["llm"]]
    summary = {
        "at": now(), "places": len(results),
        "verdict": dict(collections.Counter(x["verdict"] for x in llm)),
        "not_tourism": sorted(r["name"] for r in results if r["llm"] and not r["llm"]["tourism_relevant"]),
        "not_in_city": sorted(r["name"] for r in results if r["llm"] and not r["llm"]["in_city"]),
        "checks": dict(collections.Counter(i.split(":")[0] for r in results for i in r["checks"])),
        "bad_reviews": dict(collections.Counter(b["problem"] for x in llm for b in x["bad_reviews"])),
        "llm_errors": sum("llm_error" in r for r in results),
    }
    write_json(out / "summary.json", summary)
    print(f"qc {city}: {json.dumps(summary, ensure_ascii=False)}")
    return summary
