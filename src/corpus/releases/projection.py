"""An eligible, gated web projection built alongside the immutable serving artifacts."""

import json
from pathlib import Path

from ..crawl.common.files import safe_name
from ..normalize import Normalization
from ..serving import SERVED

GROUPS = ("experience", "environment", "service", "effort", "suitability")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _slim(node, quotes):
    if isinstance(node, list):
        return [_slim(x, quotes) for x in node[:3]] if node and isinstance(node[0], dict) else node
    if not isinstance(node, dict):
        return node
    return {("quotes" if k == "evidence" else k):
            ([quotes[i] for i in v if i in quotes][:2] if k == "evidence" else _slim(v, quotes))
            for k, v in node.items()}


def projection(release_id: str, city: str, records: list[dict], output_root: Path,
               source_root: Path, normalization: Normalization) -> dict:
    by_place = {}
    canonical = normalization.manifest["redirects"]
    for _, doc in normalization.documents():
        pid = canonical.get(doc["place_fid"], doc["place_fid"])
        quotes = by_place.setdefault(pid, {})
        for o in doc["observations"] + doc["details"]:
            quotes[o["id"]] = {"text": o["span"]["quote"][:240], "date": o.get("observed_at"), "source": o["source_type"]}
    clips = _read(source_root / "tiktok" / "clips" / f"{city}.json").get("places") or {}
    places = []
    for rec in records:
        if rec["status"] not in SERVED:
            continue
        pid = rec["id"]
        intel = _read(output_root / "intel" / "places" / f"{safe_name(pid)}.json")
        raw = _read(source_root / "gmaps" / "places" / safe_name(pid) / "place.json")
        identity = rec["identity"]
        category = identity.get("category_group")
        group = "food" if category in ("cafe", "restaurant", "dessert", "food", "bar") else "shop" if category in ("market", "shop") else "stay" if category == "stay" else "other" if category == "other" else "sight"
        quotes = by_place.get(pid, {})
        features = []
        for section in GROUPS:
            for fid, feature in rec.get(section, {}).items():
                sig = intel["features"][fid]
                confidence = feature.get("confidence") or {}
                features.append({"id": fid, "value": feature["value"], "status": feature["status"],
                                 "rawStatus": sig["status"], "distribution": feature["distribution"], "n": feature["n"],
                                 "agreement": confidence.get("agreement"), "freshnessDays": confidence.get("freshness_days"),
                                 "sourceTypes": confidence.get("source_types") or [], "bySource": sig.get("by_source") or {},
                                 "byContext": feature.get("by_context") or {}, "mentionRate": feature.get("mention_rate"),
                                 "trend": (sig.get("trend") or {}).get("direction", "insufficient"), "authority": sig.get("authority"),
                                 "quotes": [quotes[i] for i in feature.get("evidence") or [] if i in quotes][:3]})
        op = intel.get("operation") or {}
        videos = [{"id": v["video_id"], "url": v["url"], "handle": v.get("author_id"),
                   "desc": (v.get("desc") or "")[:220], "local": True} for v in clips.get(pid, [])]
        if not videos:
            mapping = _read(source_root / "tiktok" / "place_filter" / f"{safe_name(pid)}.json").get("videos")
            videos = [{"id": v["video_id"], "url": v.get("url") or "", "handle": None,
                       "desc": (v.get("desc") or "")[:220]} for v in mapping if (v.get("llm") or {}).get("relevance") == "yes"][:6] if isinstance(mapping, list) else []
        place = {"id": pid, "name": identity["name"], "category": identity.get("category"), "group": group,
                 "lat": identity.get("lat"), "lng": identity.get("lng"), "address": identity.get("address"),
                 "mapsUrl": identity.get("url") or raw.get("url"), "rating": raw.get("score"), "reviewCount": raw.get("reviews"),
                 "hoursText": raw.get("hours") or [], "googleStatus": raw.get("status"), "attributes": raw.get("attributes") or [],
                 "kind": "experience", "asOf": intel.get("as_of"), "voices": intel.get("voices"), "coverage": intel.get("coverage") or {},
                 "hours": op.get("hours"), "closure": op.get("closure"), "priceRange": op.get("price_range"),
                 "crowdByTime": op.get("crowd_by_time"), "ratingTrend": intel.get("rating_trend"), "features": features,
                 "details": _slim(rec.get("details") or {}, quotes), "videos": videos}
        places.append(place)
    return {"corpusReleaseId": release_id, "city": city, "asOf": max((p["asOf"] for p in places), default=None),
            "places": places, "review": [], "decisions": [], "system": {}, "build": {"places": len(places)}}
