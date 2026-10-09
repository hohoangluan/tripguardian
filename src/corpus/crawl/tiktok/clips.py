"""Place phase, clips: the verified videos users play on each place card -> data/tiktok/clips/<city>.json.

A place's candidates are its place_verify evidence videos (evidence_pairs: model "yes", a person's keep / drop wins)
whose clip is on disk, from search (place_crawl) or the place page (poi_crawl) alike. They are ranked as poi_crawl
ranks a place page (poi_crawl.score on info.json, with the place's Maps and TikTok names), one per author, and the
top `clips_per_place` kept: {at, places: {fid: [{video_id, url, author_id, desc, score}]}}. Rebuilt from the files
every run; scripts/free_tiktok_clips.py never deletes a clip listed here.
"""

import collections
import json

from ..common.files import data_dir, listed, load_config, now, write_json
from .place_verify import evidence_pairs
from .poi_crawl import name_keys, score


def picked(city: str) -> set[str]:
    """Every video_id some place shows (empty before the first run)."""
    f = data_dir() / "tiktok" / "clips" / f"{city}.json"
    return {v["video_id"] for vs in json.loads(f.read_text(encoding="utf-8"))["places"].values() for v in vs} \
        if f.exists() else set()


def run(city: str) -> dict:
    _, cfg = load_config(city)
    n = cfg["tiktok"]["clips_per_place"]
    root = data_dir() / "tiktok"
    names = {r["fid"]: [r["name"]] for r in listed(city) or []}
    poi = root / "place_poi" / f"{city}.json"
    for fid, p in (json.loads(poi.read_text(encoding="utf-8"))["places"] if poi.exists() else {}).items():
        if p["poi"] and fid in names:
            names[fid].append(p["poi"]["name"])
    by_place: dict[str, list[str]] = collections.defaultdict(list)
    for video_id, fid in evidence_pairs():
        if fid in names and (root / "videos" / video_id / "video.mp4").exists():
            by_place[fid].append(video_id)
    out = {}
    for fid, ids in sorted(by_place.items()):
        keys, rows = name_keys(*names[fid]), []
        for video_id in ids:
            d = root / "videos" / video_id
            s = score(json.loads((d / "info.json").read_text(encoding="utf-8")), keys)
            if s is None:
                continue
            v = json.loads((d / "video.json").read_text(encoding="utf-8"))
            rows.append({"video_id": video_id, "url": v["video_url"], "author_id": v.get("author_id"),
                         "desc": v.get("caption") or "", "score": s})
        best, authors = [], set()
        for r in sorted(rows, key=lambda r: -r["score"]):
            if r["author_id"] not in authors and len(best) < n:
                authors.add(r["author_id"])
                best.append(r)
        if best:
            out[fid] = best
    write_json(root / "clips" / f"{city}.json", {"at": now(), "places": out})
    summary = {"places": len(out), "clips": sum(map(len, out.values())),
               "full": sum(len(v) >= n for v in out.values())}
    print(f"clips {city}: {json.dumps(summary)}")
    return summary
