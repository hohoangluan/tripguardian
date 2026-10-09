"""Place phase, place_poi: each Maps place's own TikTok place (POI), whose page lists the videos shot there.

A video tagged with a TikTok place carries it in its item JSON (info.json "poi"). The POIs of a Maps place's
place_verify evidence videos are its candidates (most tagged first, at most CANDIDATES; administrative areas such as
the city are never one). Two Extractor reads of both names, categories and addresses (PLACE_POI_MATCH), the second
with the two places in swapped order, decide each; reads that disagree give unsure (Gemma flipped 43 of 983 places
between two identical runs). Only same_place maps, since a wrong POI would show users another place's videos;
part_of, branch, different, unsure and model errors never do. A POI is one place: when several Maps places judge it
same_place, only the one with the most videos tagged with it gets it, and none on a tie; entries the Judge
merged (judge dedup) count as one place.
Writes data/tiktok/place_poi/<city>.json: {at, model, prompt_hash, places: {fid: {name, category, address,
poi: {id, name, address, category} | null, candidates: [{...poi, videos, relation, reason}],
shared_with: [fid] when other places claimed the same POI}}}.
A candidate is judged again only when the prompt, its address or the Maps address changes.
"""

import asyncio
import collections
import json

from ...judge import merges
from ...llm import PLACE_POI_MATCH
from ..common.files import data_dir, listed, load_config, now, write_json
from .crawl import poi_of
from .place_filter import address
from .place_verify import evidence_pairs

CANDIDATES = 3  # per place, most tagged first: a place's own POI is nearly always its most tagged one
AREAS = {"Thành phố", "Quận", "Tỉnh", "Quốc gia"}  # ttTypeNameTiny of administrative areas: never one place


def _client():
    return PLACE_POI_MATCH.role.client()


def candidates(fids: set[str]) -> dict[str, list[dict]]:
    """fid -> its candidate POIs ({id, name, address, category, videos}), most tagged first."""
    videos = data_dir() / "tiktok" / "videos"
    votes: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    pois: dict[str, dict] = {}
    for video_id, fid in evidence_pairs():
        f = videos / video_id / "info.json"
        if fid not in fids or not f.exists():
            continue
        item = json.loads(f.read_text(encoding="utf-8"))
        poi = poi_of(item)
        if poi and (item["poi"].get("ttTypeNameTiny") not in AREAS):
            votes[fid][poi["id"]] += 1
            pois[poi["id"]] = poi
    return {fid: [{**pois[p], "videos": n} for p, n in c.most_common(CANDIDATES)] for fid, c in votes.items()}


async def run(city: str) -> dict:
    name, _ = load_config(city)
    places = listed(city)
    if places is None:
        raise SystemExit(f"no Maps list for {city}; run `python -m corpus gmaps list --city {city}` first")
    rows = {r["fid"]: r for r in places}
    target = data_dir() / "tiktok" / "place_poi" / f"{city}.json"
    prev = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    same_prompt = prev.get("prompt_hash") == PLACE_POI_MATCH.prompt_hash
    client, model = _client()
    sem = asyncio.Semaphore(PLACE_POI_MATCH.parallel)
    errors = [0]

    async def judge(place: dict, cand: dict, old: dict | None) -> dict | None:
        if old and old["address"] == cand["address"]:
            return {**cand, "relation": old["relation"], "reason": old["reason"]}
        maps = f"Google Maps: {place['name']} | {place.get('category') or 'unknown'} | {place.get('address') or 'unknown'}"
        tiktok = f"TikTok place: {cand['name']} | {cand.get('category') or 'unknown'} | {cand.get('address') or 'unknown'}"

        async def read(pair: str) -> dict:
            async with sem:
                return await PLACE_POI_MATCH.ask(client, model, city=name, pair=pair)

        try:
            a, b = await asyncio.gather(read(f"{maps}\n{tiktok}"), read(f"{tiktok}\n{maps}"))
        except Exception:
            errors[0] += 1
            return None  # judged next run
        if a["relation"] == b["relation"]:
            return {**cand, "relation": a["relation"], "reason": a["reason"]}
        return {**cand, "relation": "unsure", "reason": f"{a['relation']}: {a['reason']} / {b['relation']}: {b['reason']}"}

    async def one(fid: str, cands: list[dict]) -> tuple[str, dict]:
        r = rows[fid]
        place = {"name": r["name"], "category": r.get("category"), "address": address(fid)}
        old_place = (prev.get("places") or {}).get(fid) or {}
        done = ({c["id"]: c for c in old_place.get("candidates", [])}
                if same_prompt and old_place.get("address") == place["address"] else {})
        judged = [c for c in await asyncio.gather(*(judge(place, c, done.get(c["id"])) for c in cands)) if c]
        return fid, {**place, "candidates": judged}

    out = dict(await asyncio.gather(*(one(fid, c) for fid, c in candidates(set(rows)).items())))
    best = {fid: next((c for c in p["candidates"] if c["relation"] == "same_place"), None)  # most tagged same_place
            for fid, p in out.items()}
    canon = merges()  # Maps entries the Judge merged into one place claim a POI together
    claims: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for fid, c in best.items():
        if c:
            claims[c["id"]][canon.get(fid, fid)] += c["videos"]
    for fid, p in out.items():
        c = best[fid]
        rivals = claims[c["id"]].most_common() if c else []
        # one POI is one place: several Maps places claiming it are parts of it (a market's stairs, a valley's hill)
        # or unmerged duplicates, so it goes only to the place most tagged with it; a tie gives it to none
        won = c and rivals[0][0] == canon.get(fid, fid) and (len(rivals) == 1 or rivals[1][1] < rivals[0][1])
        p["poi"] = {k: c[k] for k in ("id", "name", "address", "category")} if won else None
        if c and not won:
            p["shared_with"] = sorted(f for f, b in best.items()
                                      if b and b["id"] == c["id"] and canon.get(f, f) != canon.get(fid, fid))
    write_json(target, {"at": now(), "model": model, "prompt_hash": PLACE_POI_MATCH.prompt_hash,
                        "places": dict(sorted(out.items()))})
    relations = collections.Counter(c["relation"] for p in out.values() for c in p["candidates"])
    summary = {"places": len(out), "mapped": sum(bool(p["poi"]) for p in out.values()),
               "relations": dict(relations), "llm_errors": errors[0]}
    print(f"place_poi {city}: {json.dumps(summary, ensure_ascii=False)}")
    return summary
