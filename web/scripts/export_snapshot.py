"""Export a read-only UI snapshot of the Da Lat corpus for the web prototype.

Reads the pipeline outputs (data/intel, data/gmaps, data/tiktok) and writes web/public/data/snapshot.json.
Sources stay separate in the output: Google facts, review signals and TikTok videos are distinct fields.
Run from the repo root after `python -m corpus aggregate --city dalat`:

    python web/scripts/export_snapshot.py
"""

import json
import random
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
OUT = ROOT / "web" / "public" / "data" / "snapshot.json"

OUTDATED_DAYS = 365
SAMPLE_RATE = 0.05
MIN_INVENTORY_REVIEWS = 80

SIGHT = ("Điểm thu hút", "Đỉnh núi", "Vườn", "Trang trại", "Công viên", "Hồ", "Thác", "Chùa", "Nhà thờ", "Bảo tàng",
         "Di tích", "Khu du lịch", "Thiền viện", "Đồi", "Rừng", "Làng", "Nhà ga", "Quảng trường", "Đài quan sát",
         "Khu bảo tồn", "Cánh đồng", "Thung lũng", "Khu vui chơi", "Công trình", "Địa điểm lịch sử", "Đền", "Tu viện")
FOOD = ("Quán cà phê", "Cà phê", "Nhà hàng", "Trà", "Tiệm bánh", "Món", "Quán bar", "Khu ăn uống", "Quán ăn", "Cửa hàng ăn",
        "Quán", "Bánh", "Lẩu", "Kem", "Cửa hàng cà phê", "Cửa hàng bán đồ tráng miệng")
SHOP = ("Chợ", "Cửa hàng", "Trung tâm mua sắm", "Siêu thị")


def read(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def group_of(category: str | None) -> str:
    c = category or ""
    for prefix, g in (("Cửa hàng bán đồ tráng miệng", "food"), ("Cửa hàng cà phê", "food"), ("Cửa hàng ăn", "food")):
        if c.startswith(prefix):
            return g
    if any(c.startswith(s) for s in SIGHT):
        return "sight"
    if any(c.startswith(s) for s in FOOD):
        return "food"
    if any(c.startswith(s) for s in SHOP):
        return "shop"
    return "other"


def fid_dir(fid: str) -> str:
    return fid.replace(":", "_")


def gmaps_place(fid: str) -> dict:
    p = DATA / "gmaps" / "places" / fid_dir(fid) / "place.json"
    return read(p) if p.exists() else {}


CLIPS = DATA / "tiktok" / "clips" / "dalat.json"  # `python -m corpus tiktok clips`: verified clips on our server
_clips: dict = {}


def videos_for(fid: str) -> list[dict]:
    """The place's verified clips on our server (local: played from /media/tiktok), else its caption-matched TikTok
    videos (played in TikTok's embed)."""
    if not _clips:
        _clips["places"] = read(CLIPS)["places"] if CLIPS.exists() else {}
    if _clips["places"].get(fid):
        return [{"id": v["video_id"], "url": v["url"], "handle": v.get("author_id"),
                 "desc": (v.get("desc") or "").strip()[:220], "local": True} for v in _clips["places"][fid]]
    p = DATA / "tiktok" / "place_filter" / f"{fid_dir(fid)}.json"
    if not p.exists():
        return []
    vids = read(p).get("videos")
    out = []
    for v in vids if isinstance(vids, list) else []:
        if (v.get("llm") or {}).get("relevance") != "yes":
            continue
        url = v.get("url") or ""
        handle = url.split("/@")[1].split("/")[0] if "/@" in url else None
        out.append({"id": v["video_id"], "url": url, "handle": handle, "desc": (v.get("desc") or "").strip()[:220]})
    return out[:6]


def quotes_by_obs(fid: str) -> dict:
    p = DATA / "gmaps" / "observations" / f"{fid_dir(fid)}.json"
    if not p.exists():
        return {}
    out = {}
    for o in read(p)["observations"]:
        q = ((o.get("span") or {}).get("quote") or "").strip()
        if (o.get("span") or {}).get("field") == "details":
            q = q.splitlines()[-1] if q else q
        out[o["id"]] = {"text": q, "date": o.get("observed_at"), "source": o["source_type"],
                        "context": o.get("context") or {}}
    return out


def ui_status(sig: dict) -> str:
    if sig["needs_review"]:
        return "NEEDS_REVIEW"
    if sig["status"] == "uncertain" or (sig["n"] < 2 and not sig["authority"]):
        return "UNCERTAIN"
    fresh = sig["confidence"]["freshness_days"]
    if fresh is not None and fresh > OUTDATED_DAYS:
        return "OUTDATED"
    return "VERIFIED"


def export_feature(fid_feature: str, sig: dict, quotes: dict) -> dict:
    qs, seen = [], set()
    for oid in sig["observation_ids"]:
        q = quotes.get(oid)
        if not q or not q["text"] or q["text"] in seen or len(q["text"]) < 6:
            continue
        seen.add(q["text"])
        qs.append({"text": q["text"][:240], "date": q["date"], "source": q["source"]})
    qs.sort(key=lambda q: (-len(q["text"]) if len(q["text"]) < 140 else 0, q["date"] or ""), reverse=False)
    return {
        "id": fid_feature,
        "value": sig["top_value"],
        "distribution": sig["distribution"],
        "n": sig["n"],
        "agreement": sig["confidence"]["agreement"],
        "freshnessDays": sig["confidence"]["freshness_days"],
        "sourceTypes": sig["confidence"]["source_types"],
        "bySource": sig["by_source"],
        "byContext": sig["by_context"],
        "mentionRate": sig["mention_rate"],
        "trend": sig["trend"]["direction"],
        "authority": sig["authority"],
        "status": ui_status(sig),
        "rawStatus": sig["status"],
        "quotes": qs[:3],
    }


def base_place(fid: str, g: dict) -> dict:
    return {
        "id": fid,
        "name": g.get("name"),
        "category": g.get("category"),
        "group": group_of(g.get("category")),
        "lat": g.get("lat"),
        "lng": g.get("lng"),
        "address": g.get("address"),
        "mapsUrl": g.get("url"),
        "rating": g.get("score"),
        "reviewCount": g.get("reviews"),
        "hoursText": g.get("hours") or [],
        "googleStatus": g.get("status"),
        "attributes": g.get("attributes") or [],
    }


def recent_errors(limit: int = 40) -> list[dict]:
    """Newest pipeline errors across sources, each tagged with its source and stage."""
    out = []
    for path, source, stage in ((DATA / "gmaps" / "errors.jsonl", "gmaps", None), (DATA / "gmaps" / "observe_errors.jsonl", "gmaps", "observe"),
                                (DATA / "tiktok" / "errors.jsonl", "tiktok", None)):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            if not line.strip():
                continue
            e = json.loads(line)
            out.append({"at": e.get("at"), "source": source, "stage": e.get("stage") or stage,
                        "ref": e.get("id") or e.get("place"), "error": (e.get("error") or "")[:200]})
    out.sort(key=lambda e: e["at"] or "", reverse=True)
    return out[:limit]


def main() -> None:
    random.seed(11)
    places, review = [], []
    intel_dir = DATA / "intel" / "places"
    intel_ids = set()
    as_of = None
    for f in sorted(intel_dir.glob("*.json")):
        d = read(f)
        fid = d["place_fid"]
        intel_ids.add(fid)
        as_of = max(as_of or d["as_of"], d["as_of"])
        g = gmaps_place(fid)
        quotes = quotes_by_obs(fid)
        feats = [export_feature(k, v, quotes) for k, v in d["features"].items()]
        p = base_place(fid, g) | {
            "name": d["place_name"],
            "category": d["identity"].get("category") or g.get("category"),
            "group": group_of(d["identity"].get("category") or g.get("category")),
            "lat": d["identity"].get("lat", g.get("lat")),
            "lng": d["identity"].get("lng", g.get("lng")),
            "kind": "experience",
            "asOf": d["as_of"],
            "voices": d["voices"],
            "coverage": d["coverage"],
            "hours": d["operation"].get("hours"),
            "closure": d["operation"].get("closure"),
            "priceRange": d["operation"].get("price_range"),
            "crowdByTime": d["operation"].get("crowd_by_time"),
            "ratingTrend": d.get("rating_trend"),
            "features": feats,
            "proposed": d.get("proposed_features") or [],
            "videos": videos_for(fid),
        }
        places.append(p)
        for ft in feats:
            sample = ft["status"] == "VERIFIED" and random.random() < SAMPLE_RATE
            # Queue content per docs/CORPUS.md §7: UNCERTAIN values are auto-published, not queued.
            if ft["status"] == "NEEDS_REVIEW" or sample:
                kind = ("conflict" if ft["rawStatus"] == "uncertain"
                        else "permissive_check" if ft["id"] in ("kids", "elderly") else "judge_flag")
                review.append({"id": f"{fid}#{ft['id']}", "kind": kind, "placeId": fid, "feature": ft["id"],
                               "value": ft["value"], "sample": sample})
        for pr in p["proposed"]:
            if pr.get("authors", 0) >= 2:
                review.append({"id": f"{fid}#proposed:{pr['label']}", "kind": "proposed_feature", "placeId": fid,
                               "feature": pr["label"], "value": f"{pr['authors']} người nhắc", "sample": False})

    inventory = 0
    for f in sorted((DATA / "gmaps" / "places").glob("*/place.json")):
        g = read(f)
        if g["fid"] in intel_ids or not g.get("lat"):
            continue
        grp = group_of(g.get("category"))
        if grp == "other" or (g.get("reviews") or 0) < MIN_INVENTORY_REVIEWS:
            continue
        places.append(base_place(g["fid"], g) | {"kind": "inventory", "features": [], "videos": videos_for(g["fid"])})
        inventory += 1

    decisions = []
    dp = DATA / "review" / "decisions.jsonl"
    if dp.exists():
        for line in dp.read_text(encoding="utf-8").splitlines()[-60:]:
            if line.strip():
                decisions.append(json.loads(line))

    system = {"observe": read(DATA / "gmaps" / "observe_summary.json") if (DATA / "gmaps" / "observe_summary.json").exists() else None,
              "errors": recent_errors(), "videos": sum(1 for _ in (DATA / "tiktok" / "videos").glob("*/video.json")),
              "gmapsPlaces": sum(1 for _ in (DATA / "gmaps" / "places").glob("*/place.json"))}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    snap = {"asOf": as_of or date.today().isoformat(), "city": "dalat", "places": places, "review": review,
            "decisions": decisions, "system": system,
            "build": json.loads((DATA / "intel" / "summary.json").read_text(encoding="utf-8"))}
    OUT.write_text(json.dumps(snap, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(places)} places ({len(intel_ids)} with evidence, {inventory} inventory), {len(review)} review items -> {OUT}")


if __name__ == "__main__":
    main()
