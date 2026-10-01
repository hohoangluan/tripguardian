"""Aggregate (docs/specs/CORPUS_SPEC.md §5), code only: every source's observations of a place -> one intel file.

Reads data/*/observations/*.json without knowing the source, writes data/intel/places/<fid_dir>.json. Per feature:
votes (one per author; an author who gave k different values gives each 1/k), context breakdown, confidence parts,
trend of the newer half of the dated evidence against the older half. A value declared by an authoritative source
(Maps attributes) is served without a person when no other source contradicts it; a contradiction makes it uncertain.
Place facts (popular times, price) pass through as `operation`, popular times also summed up by day type x time of day. Conflicts are kept as distributions, never flattened.
"""

import collections
import json
from datetime import date

from ..crawl.common.files import data_dir, now, safe_name, write_json
from ..observe import CONTEXT_KEYS
from ..ontology import UNKNOWN, Feature, Ontology, load as load_ontology

AGREEMENT_MIN = 0.6
TREND_MIN = 5  # authors on each side
TREND_DELTA = 0.2  # change in the share of the top value
RATING_DELTA = 0.5  # stars
COMPLETE_FEATURES, COMPLETE_N = 3, 3
AUTHORITATIVE = {"gmaps_attribute"}
WEEKEND = ("sat", "sun")
DAY_ORDER = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")


def time_of_day(hour: int) -> str:
    """Same buckets as the ontology context time_of_day."""
    for name, lo, hi in (("early_morning", 4, 5), ("morning", 6, 10), ("noon", 11, 13), ("afternoon", 14, 16),
                         ("evening", 17, 20)):
        if lo <= hour <= hi:
            return name
    return "night"
SOURCE_KIND = {"gmaps_review": "provider", "gmaps_details": "provider", "tiktok_segment": "video",
               "tiktok_comment": "comment"}


def _who(o: dict) -> str:
    return o.get("author") or o["id"]


def _num(x: float):
    x = round(x, 3)
    return int(x) if x == int(x) else x


def votes(obs: list[dict]) -> dict:
    by_author = collections.defaultdict(set)
    for o in obs:
        by_author[_who(o)].add(o["value"])
    out = collections.Counter()
    for values in by_author.values():
        for v in values:
            out[v] += 1 / len(values)
    return {v: _num(c) for v, c in out.items()}


def authors(obs: list[dict]) -> int:
    return len({_who(o) for o in obs})


def top(dist: dict, order: tuple[str, ...]) -> str:
    return max(dist, key=lambda v: (dist[v], -order.index(v)))


def _age(as_of: date, day: str) -> int:
    return (as_of - date.fromisoformat(day)).days


def split_by_date(items: list[dict]) -> tuple[list[dict], list[dict], str | None]:
    """Older and newer half of the dated items, cut at the median date so both halves never share a date.

    Relative, not a fixed window: the crawl keeps the newest reviews, so a busy place has all of them in the last
    weeks and a fixed window would leave its older side empty.
    """
    dated = sorted((x for x in items if x.get("observed_at")), key=lambda x: x["observed_at"])
    if not dated:
        return [], [], None
    cut = dated[len(dated) // 2]["observed_at"]
    return [x for x in dated if x["observed_at"] < cut], [x for x in dated if x["observed_at"] >= cut], cut


def trend(obs: list[dict], top_value: str) -> dict:
    older, recent, cut = split_by_date(obs)
    res = {"split_at": cut, "recent": votes(recent), "older": votes(older), "direction": "insufficient"}
    nr, no = authors(recent), authors(older)
    if nr >= TREND_MIN and no >= TREND_MIN:
        d = res["recent"].get(top_value, 0) / nr - res["older"].get(top_value, 0) / no
        res["direction"] = "rising" if d >= TREND_DELTA else "falling" if d <= -TREND_DELTA else "stable"
    return res


def feature_signal(feat: Feature, obs: list[dict], as_of: date) -> dict:
    unique = list({(_who(o), o["value"], tuple(o["context"][k] for k in CONTEXT_KEYS)): o for o in obs}.values())
    dist, n = votes(unique), authors(unique)
    t = top(dist, feat.values)
    agreement = round(dist[t] / n, 3)
    by_context = {}
    for k in CONTEXT_KEYS:
        groups = collections.defaultdict(list)
        for o in unique:
            if o["context"][k] != UNKNOWN:
                groups[o["context"][k]].append(o)
        for c in sorted(groups):
            by_context[f"{k}={c}"] = votes(groups[c])
    dates = [o["observed_at"] for o in unique if o.get("observed_at")]
    declared = {o["value"] for o in unique if o["source_type"] in AUTHORITATIVE}
    authority = next(iter(declared)) if len(declared) == 1 else None
    conflict = bool(declared) and bool({o["value"] for o in unique if o["source_type"] not in AUTHORITATIVE} - declared
                                       or len(declared) > 1)
    voters = len({_who(o) for o in unique if o["value"] == t})
    if authority and not conflict:
        needs_review = False
    else:
        needs_review = feat.verify == "always" and (conflict or t not in feat.caution_values or voters < 2)
    return {
        "n": n, "distribution": dist, "top_value": t,
        "status": "uncertain" if conflict or agreement < AGREEMENT_MIN else "signal",
        "authority": authority,
        "by_context": by_context,
        "by_source": dict(collections.Counter(o["source_type"] for o in obs)),
        "confidence": {"independent_sources": n, "agreement": agreement,
                       "freshness_days": _age(as_of, max(dates)) if dates else None,
                       "source_types": sorted({SOURCE_KIND.get(o["source_type"], o["source_type"]) for o in unique})},
        "trend": trend(unique, t),
        "needs_review": needs_review,
        "observation_ids": [o["id"] for o in obs],
    }


def rating_trend(ratings: list[dict]) -> dict:
    old, new, cut = split_by_date(ratings)
    older, recent = [r["stars"] for r in old], [r["stars"] for r in new]
    mean = lambda xs: round(sum(xs) / len(xs), 2) if xs else None  # noqa: E731
    res = {"split_at": cut, "recent_mean": mean(recent), "recent_n": len(recent), "older_mean": mean(older), "older_n": len(older),
           "direction": "insufficient"}
    if len(recent) >= TREND_MIN and len(older) >= TREND_MIN:
        d = res["recent_mean"] - res["older_mean"]
        res["direction"] = "rising" if d >= RATING_DELTA else "falling" if d <= -RATING_DELTA else "stable"
    return res


def crowd_by_time(popular_times: dict | None) -> dict | None:
    """Mean relative busyness (100 = the place's own peak) by weekday / weekend x time of day; 0 = closed, left out."""
    if not popular_times:
        return None
    sums = collections.defaultdict(list)
    cells = []
    for day in DAY_ORDER:
        for hour, pct in sorted(((int(h), p) for h, p in (popular_times.get(day) or {}).items())):
            if pct:
                sums[("weekend" if day in WEEKEND else "weekday", time_of_day(hour))].append(pct)
                cells.append((pct, -DAY_ORDER.index(day), -hour, day, hour))
    out = {"weekday": {}, "weekend": {}}
    for (dt, tod), xs in sums.items():
        out[dt][tod] = round(sum(xs) / len(xs))
    best = max(cells) if cells else None
    out["peak"] = {"day": best[3], "hour": best[4], "pct": best[0]} if best else None
    return out


def coverage(features: dict, ont: Ontology) -> dict:
    out = {}
    for g in ont.groups:
        ns = [s["n"] for fid, s in features.items() if ont.features[fid].group == g]
        out[g] = "NONE" if not ns else "COMPLETE" if sum(n >= COMPLETE_N for n in ns) >= COMPLETE_FEATURES else "PARTIAL"
    return out


def aggregate_place(files: list[dict], ont: Ontology) -> dict:
    as_of = max(date.fromisoformat(f["as_of"]) for f in files)
    by_feature = collections.defaultdict(list)
    for f in files:
        for o in f["observations"]:
            if ont.valid(o["feature"], o["value"]):
                by_feature[o["feature"]].append(o)
    features = {fid: feature_signal(ont.features[fid], by_feature[fid], as_of) for fid in ont.features if fid in by_feature}
    ratings = [r for f in files for r in f.get("ratings", [])]
    proposed = collections.defaultdict(list)
    for f in files:
        for p in f.get("proposed", []):
            proposed[p["label"].strip().casefold()].append(p.get("author"))
    facts = {}
    for f in files:
        for k, v in (f.get("place_facts") or {}).items():
            if v is not None:
                facts.setdefault(k, v)
    return {
        "place_fid": files[0]["place_fid"],
        "place_name": next((f["place_name"] for f in files if f.get("place_name")), None),
        "as_of": as_of.isoformat(), "ontology_version": ont.version,
        "features": features, "coverage": coverage(features, ont),
        "operation": {"price_range": facts.get("price"), "crowd_by_time": crowd_by_time(facts.get("popular_times")),
                      "popular_times": facts.get("popular_times")},
        "rating_trend": rating_trend(ratings) if ratings else None,
        "proposed_features": sorted(({"label": k, "count": len(v), "authors": len(set(v))} for k, v in proposed.items()),
                                    key=lambda x: (-x["count"], x["label"])),
    }


def run(city: str) -> dict:
    """city is accepted for a uniform CLI; observations are already per place."""
    ont = load_ontology()
    root = data_dir()
    files, inputs, stale = collections.defaultdict(list), collections.defaultdict(list), 0
    for p in sorted(root.glob("*/observations/*.json")):
        f = json.loads(p.read_text(encoding="utf-8"))
        if f.get("ontology_version") != ont.version:
            stale += 1
            continue
        files[f["place_fid"]].append(f)
        inputs[f["place_fid"]].append(p.relative_to(root).as_posix())
    status = collections.Counter()
    for fid, fs in files.items():
        intel = aggregate_place(fs, ont)
        status.update(f"{k}={v}" for k, v in intel["coverage"].items())
        write_json(root / "intel" / "places" / f"{safe_name(fid)}.json", {**intel, "inputs": inputs[fid], "built_at": now()})
    summary = {"at": now(), "places": len(files), "stale_files": stale, "coverage": dict(sorted(status.items()))}
    write_json(root / "intel" / "summary.json", summary)
    print(f"aggregate {city}: {json.dumps(summary, ensure_ascii=False)}")
    return summary
