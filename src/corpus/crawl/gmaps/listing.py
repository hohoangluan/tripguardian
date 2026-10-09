"""Phase 3, list: search files + filter verdicts -> the phase-1 place list: every kept place with min_reviews reviews
or more (top: at most that many per category, by review-weighted rating; None: no cap).

Writes only data/gmaps/list/<city>.json: {at, stats, items:[{fid, name, url, lat, lng, category, rating, reviews, score,
queries[]}]}, best score first, and data/gmaps/list/<city>_stay.json, the lodging list in the same shape (build_stay).
Rebuilt from scratch every time, so it always matches the search files. No browser.

Dropped: places outside the city area, lodging (users enter their own; Maps' hotel lists and lodging categories),
places filter.py did not keep ("no", or not judged yet; a person's keep / drop in review overrides the model), places
with fewer than min_reviews reviews (or no rating: too little evidence the place is real and good), search records in
an older format (no end flag / rating: searched again by search.py), and extra copies of one place (Maps lists one
place under several fids: same name without accents, case, punctuation or the city name, within same_name_m of each
other; the one with the most reviews is kept). Only the name counts: different shops often share a building's point,
and a chain's branches further apart are different places.

score = Bayesian average: (v * R + m * C) / (v + m), R = rating, v = reviews, C = mean rating of the category,
m = median review count of the category. A 5.0 with 3 reviews stays near C; a 4.7 with 2,000 reviews stays near 4.7.
"""

import json
import math
import re
import statistics
import unicodedata

from ...review import decisions
from ..common.files import STAY, data_dir, load_config, now, write_json
from .tiles import in_area

KEEP = ("yes", "unsure")
KEYS = ("fid", "name", "url", "lat", "lng", "category", "rating", "reviews")
_LODGING = re.compile(r"khách sạn|nhà nghỉ|nhà khách|nhà trọ|homestay|khu nghỉ dưỡng|resort|biệt thự|villa|căn hộ|"
                      r"chỗ ở|nhà ở|hostel|motel|guest ?house|lưu trú|glamping", re.I)


def is_lodging(category: str | None) -> bool:
    return bool(category and _LODGING.search(unicodedata.normalize("NFC", category)))  # Maps sends some text as NFD


def kept_fids(filter_dir) -> set[str]:
    """Places filter.py kept, with a person's keep / drop (review) overriding the model."""
    kept = set()
    for f in filter_dir.glob("*.json") if filter_dir.exists() else []:
        res = json.loads(f.read_text(encoding="utf-8"))
        if f.name != "summary.json" and res["llm"]["relevance"] in KEEP:
            kept.add(res["fid"])
    person = decisions("place_filter")
    return (kept | {v for v, d in person.items() if d == "keep"}) - {v for v, d in person.items() if d == "drop"}


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFD", text.casefold()).replace("đ", "d")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _meters(a: dict, b: dict) -> float:
    dx = math.radians(b["lng"] - a["lng"]) * math.cos(math.radians(a["lat"]))
    return 6371000 * math.hypot(dx, math.radians(b["lat"] - a["lat"]))


def _same_place(rows: list[dict], city: str | None = None, radius_m: float = 0) -> dict[str, dict]:
    """copy fid -> kept row: a row with the same plain name (city name removed) as a row with more reviews, within
    radius_m of it or of one of its copies."""
    city_words = re.compile(rf"\b({_plain(city)}|{_plain(city).replace(' ', '')})\b" if city else r"(?!)")
    by_name: dict[str, list[dict]] = {}
    for r in {r["fid"]: r for r in rows}.values():
        name = " ".join(city_words.sub(" ", _plain(r["name"])).split())
        if name:
            by_name.setdefault(name, []).append(r)
    copies: dict[str, dict] = {}
    for group in by_name.values():
        clusters: list[list[dict]] = []  # first row = most reviews = the one kept
        for r in sorted(group, key=lambda r: -(r["reviews"] or 0)):
            near = next((c for c in clusters if any(_meters(r, x) <= radius_m for x in c)), None)
            if near:
                near.append(r)
                copies[r["fid"]] = near[0]
            else:
                clusters.append([r])
    return copies


def _scored(rows: list[dict]) -> list[dict]:
    rated = [r for r in rows if r["rating"] is not None and r["reviews"]]
    if rated:
        c = statistics.fmean(r["rating"] for r in rated)
        m = statistics.median(r["reviews"] for r in rated)
    for r in rows:
        v = r["reviews"] or 0
        r["score"] = round((v * r["rating"] + m * c) / (v + m), 4) if r["rating"] is not None and v else None
    return sorted(rows, key=lambda r: (r["score"] is None, -(r["score"] or 0), -(r["reviews"] or 0)))


def build(search_dir, area, top: int | None = 100, kept: set[str] | None = None, city: str | None = None,
          min_reviews: int = 0, same_name_m: float = 0, counts: dict[str, dict] | None = None) -> dict:
    """kept: fids filter.py kept (None: no filter). counts: fid -> {rating, reviews} read on the place page (counts.py),
    taken over the search cards'."""
    by_query: dict[str, dict[str, dict]] = {}
    lodging_fids: set[str] = set()  # Maps files a hotel with a restaurant under both: a lodging category anywhere wins
    raw = outside = lodging = 0
    for f in sorted(search_dir.glob("*.jsonl")) if search_dir.exists() else []:
        for line in f.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            if "end" not in rec or not all("rating" in r for r in rec["items"]):
                continue  # older format, searched again
            for r in rec["items"]:
                raw += 1
                if not in_area(r["lat"], r["lng"], area):
                    outside += 1
                elif rec.get("lodging") or is_lodging(r.get("category")):
                    lodging += 1
                    if is_lodging(r.get("category")):
                        lodging_fids.add(r["fid"])
                else:
                    rows = by_query.setdefault(rec["query"], {})
                    if r["fid"] not in rows or (r.get("reviews") or 0) > (rows[r["fid"]]["reviews"] or 0):
                        rows[r["fid"]] = {k: r.get(k) for k in KEYS}
    best: dict[str, dict] = {}  # a result card sometimes shows no rating / review count: the fullest sighting counts
    for rows in by_query.values():
        for fid, r in rows.items():
            if fid not in best or (r["reviews"] or 0) > (best[fid]["reviews"] or 0):
                best[fid] = r
    for fid, n in (counts or {}).items():
        if fid in best and n.get("reviews") is not None:
            best[fid] = {**best[fid], "rating": n["rating"], "reviews": n["reviews"]}
    by_query = {q: {fid: dict(best[fid]) for fid in rows} for q, rows in by_query.items()}
    candidates = set(best) - lodging_fids
    by_query = {q: {fid: r for fid, r in rows.items() if fid in candidates} for q, rows in by_query.items()}
    dropped = set() if kept is None else candidates - kept
    by_query = {q: {fid: r for fid, r in rows.items() if fid not in dropped} for q, rows in by_query.items()}
    copies = _same_place([r for rows in by_query.values() for r in rows.values()], city, same_name_m)
    by_query = {q: {copies.get(fid, r)["fid"]: dict(copies.get(fid, r)) for fid, r in rows.items()}
                for q, rows in by_query.items()}
    few = {fid for rows in by_query.values() for fid, r in rows.items()
           if min_reviews and (r["rating"] is None or (r["reviews"] or 0) < min_reviews)}
    by_query = {q: {fid: r for fid, r in rows.items() if fid not in few} for q, rows in by_query.items()}
    items: dict[str, dict] = {}
    for query in sorted(by_query):
        for r in _scored(list(by_query[query].values()))[:top]:
            it = items.setdefault(r["fid"], {**r, "queries": []})
            it["queries"].append(query)
    kept = raw - outside - lodging
    stats = {"raw": raw, "outside_area": outside, "lodging": lodging,
             "duplicates": kept - len(candidates),  # same place in several tiles or categories
             "candidates": len(candidates), "not_kept": len(dropped), "same_place": len(copies),
             "few_reviews": len(few),
             "places": len(items)}
    order = sorted(items.values(), key=lambda r: (r["score"] is None, -(r["score"] or 0)))
    return {"at": now(), "stats": stats, "items": order}


def build_stay(search_dirs, area, city: str | None = None, min_reviews: int = 0, same_name_m: float = 0,
               counts: dict[str, dict] | None = None) -> dict:
    """The lodging list (docs/CORPUS.md §Phạm vi, group `stay`): every lodging-category place in the area seen by any
    search (the stay queries of search.run_stay and the lodging the place searches met), min_reviews or more reviews,
    one row per place. Only Planning reads it; places of other categories never enter it, whatever list they were in."""
    best: dict[str, dict] = {}
    queries: dict[str, set[str]] = {}
    raw = 0
    for d in search_dirs:
        for f in sorted(d.glob("*.jsonl")) if d.exists() else []:
            for line in f.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                if "end" not in rec or not all("rating" in r for r in rec["items"]):
                    continue
                for r in rec["items"]:
                    if not is_lodging(r.get("category")) or not in_area(r["lat"], r["lng"], area):
                        continue
                    raw += 1
                    queries.setdefault(r["fid"], set()).add(rec["query"])
                    if r["fid"] not in best or (r.get("reviews") or 0) > (best[r["fid"]]["reviews"] or 0):
                        best[r["fid"]] = {k: r.get(k) for k in KEYS}
    for fid, n in (counts or {}).items():
        if fid in best and n.get("reviews") is not None:
            best[fid] = {**best[fid], "rating": n["rating"], "reviews": n["reviews"]}
    copies = _same_place(list(best.values()), city, same_name_m)
    for fid, kept in copies.items():
        queries[kept["fid"]] |= queries.pop(fid)
        best.pop(fid)
    few = {fid for fid, r in best.items() if min_reviews and (r["rating"] is None or (r["reviews"] or 0) < min_reviews)}
    rows = _scored([dict(r) for fid, r in best.items() if fid not in few])
    items = [{**r, "queries": sorted(queries[r["fid"]])} for r in rows]
    stats = {"raw": raw, "same_place": len(copies), "few_reviews": len(few), "places": len(items)}
    return {"at": now(), "stats": stats, "items": items}


def run(city: str) -> dict:
    city = city.removesuffix(STAY)  # one run writes both lists
    name, cfg = load_config(city)
    root = data_dir() / "gmaps"
    if not (root / "filter" / "summary.json").exists():
        raise SystemExit(f"no {root / 'filter'}; run `python -m corpus gmaps filter --city {city}` first")
    g = cfg.get("gmaps", {})
    counts = root / "counts" / f"{city}.json"
    counts = json.loads(counts.read_text(encoding="utf-8"))["items"] if counts.exists() else None
    lst = build(root / "search" / city, cfg.get("area"), g.get("top_per_category"), kept_fids(root / "filter"),
                name, g.get("min_reviews", 0), g.get("same_name_m", 0), counts)
    write_json(root / "list" / f"{city}.json", lst)
    print(f"list {city}: {lst['stats']}")
    stay = build_stay([root / "search" / city, root / "search" / f"{city}{STAY}"], cfg.get("area"), name,
                      cfg.get("stay", {}).get("min_reviews", 0), g.get("same_name_m", 0), counts)
    write_json(root / "list" / f"{city}{STAY}.json", stay)
    print(f"list {city}{STAY}: {stay['stats']}")
    return lst["stats"]
