"""Aggregate (docs/specs/CORPUS_SPEC.md §5), code only: every source's observations of a place -> one intel file.

Reads data/*/observations/*.json without knowing the source, writes data/intel/places/<fid_dir>.json and removes
every other file there (a place that has no observation file now): the folder is one build. Observation files of an
older ontology version still count until observe re-runs them (values the ontology dropped are left out);
`observation_versions` and the summary's `stale_files` say how many. Per feature:
votes (one per author; an author who gave k different values gives each 1/k), context breakdown, confidence parts,
trend of the newer half of the dated evidence against the older half. A value declared by an authoritative source
(Maps attributes) is served without a person when no other source contradicts it; a contradiction makes it uncertain.
`mention_rate` = people who named the feature / the place's `voices` (authors whose words were read): a value
named by 1 of 200 reviewers is weak evidence even at agreement 1.0.
Measured quality (docs/specs/CORPUS_SPEC.md §6): `quality` = the gold-label precision of the top value (review.label_stats);
`servable` = the value may be served by itself: declared by an authoritative source, or its precision passed the label
gate, or a person accepted it; a person's `disable` (decisions.jsonl kind feature_review, id "<fid>#<feature>") makes
the feature `disabled` and never servable, `accept` clears needs_review, `report` / `refresh` set it.
Place facts (popular times, price, hours, closure) pass through as `operation`, name / category / location as `identity`, popular times also summed up by day type x time of day. Conflicts are kept as distributions, never flattened.
"""

import collections
import json
from datetime import date

from ..crawl.common.files import data_dir, now, safe_name, write_json
from ..observe import CONTEXT_KEYS
from ..ontology import UNKNOWN, Feature, Ontology, load as load_ontology
from ..review import decisions, label_stats

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
SOURCE_KIND = {"gmaps_review": "provider", "gmaps_details": "provider", "gmaps_attribute": "provider", "tiktok_segment": "video",
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


def feature_signal(feat: Feature, obs: list[dict], as_of: date, voices: int = 0) -> dict:
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
    people = [o for o in unique if o["source_type"] not in AUTHORITATIVE]  # dated by when someone said it
    dates = [o["observed_at"] for o in people if o.get("observed_at")]
    declared = {o["value"] for o in unique if o["source_type"] in AUTHORITATIVE}
    conflict = bool(declared) and bool({o["value"] for o in people} - declared or len(declared) > 1)
    authority = next(iter(declared)) if len(declared) == 1 and not conflict else None
    voters = len({_who(o) for o in unique if o["value"] == t})
    if conflict:
        needs_review = True  # a declared value someone disputes goes to a person, whatever the feature
    elif authority:
        needs_review = False
    else:
        needs_review = feat.verify == "always" and (t not in feat.caution_values or voters < 2)
    return {
        "n": n, "distribution": dist, "top_value": t,
        "status": "uncertain" if conflict or agreement < AGREEMENT_MIN else "signal",
        "authority": authority,
        "by_context": by_context,
        "by_source": dict(collections.Counter(o["source_type"] for o in obs)),
        "mention_rate": round(min(1.0, len({_who(o) for o in people}) / voices), 3) if voices else None,
        "confidence": {"independent_sources": n, "agreement": agreement,
                       "freshness_days": _age(as_of, max(dates)) if dates else None,
                       "source_types": sorted({SOURCE_KIND.get(o["source_type"], o["source_type"]) for o in unique})},
        "trend": trend(people, t),
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


def judge(sig: dict, quality: dict | None, decision: str | None) -> dict:
    """Adds quality / servable / review_decision to one feature signal (see the module docstring)."""
    sig["quality"] = quality
    sig["review_decision"] = decision
    if decision == "accept":
        sig["needs_review"] = False
    elif decision in ("report", "refresh"):
        sig["needs_review"] = True
    if decision == "disable":
        sig["status"], sig["servable"] = "disabled", False
    else:
        sig["servable"] = bool(sig["authority"] or decision == "accept" or (quality and quality["gate"]))
    return sig


def aggregate_place(files: list[dict], ont: Ontology, quality: dict | None = None,
                    reviewed: dict[str, str] | None = None) -> dict:
    """quality: (feature, value) -> label stats row; reviewed: feature -> a person's latest feature_review decision."""
    as_of = max(date.fromisoformat(f["as_of"]) for f in files)
    by_feature = collections.defaultdict(list)
    for f in files:
        for o in f["observations"]:
            if ont.valid(o["feature"], o["value"]):
                by_feature[o["feature"]].append(o)
    voices = sum(f.get("voices") or 0 for f in files)
    quality, reviewed = quality or {}, reviewed or {}
    features = {}
    for fid in ont.features:
        if fid in by_feature:
            sig = feature_signal(ont.features[fid], by_feature[fid], as_of, voices)
            features[fid] = judge(sig, quality.get((fid, sig["top_value"])), reviewed.get(fid))
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
    identity = {}
    for f in files:
        for k, v in (f.get("place") or {}).items():
            if v is not None:
                identity.setdefault(k, v)
    return {
        "place_fid": files[0]["place_fid"],
        "place_name": next((f["place_name"] for f in files if f.get("place_name")), None),
        "as_of": as_of.isoformat(), "ontology_version": ont.version, "identity": identity, "voices": voices,
        "features": features, "coverage": coverage(features, ont),
        "operation": {"price_range": facts.get("price"), "hours": facts.get("hours"), "closure": facts.get("closure"),
                      "crowd_by_time": crowd_by_time(facts.get("popular_times")),
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
        stale += f.get("ontology_version") != ont.version
        files[f["place_fid"]].append(f)
        inputs[f["place_fid"]].append(p.relative_to(root).as_posix())
    status = collections.Counter()
    out = root / "intel" / "places"
    quality = {(r["feature"], r["value"]): {k: r[k] for k in ("precision", "lower", "correct", "wrong", "gate")}
               for r in label_stats()["rows"] if r["correct"] + r["wrong"]}
    reviewed = collections.defaultdict(dict)
    for item, d in decisions("feature_review").items():
        place_fid, _, feature = item.partition("#")
        if d != "undo":
            reviewed[place_fid][feature] = d
    for fid, fs in files.items():
        intel = aggregate_place(fs, ont, quality, reviewed.get(fid))
        status.update(f"{k}={v}" for k, v in intel["coverage"].items())
        write_json(out / f"{safe_name(fid)}.json", {**intel, "inputs": inputs[fid], "built_at": now(),
                                                    "observation_versions": sorted({f.get("ontology_version") for f in fs})})
    built = {f"{safe_name(fid)}.json" for fid in files}
    removed = 0
    for p in out.glob("*.json") if out.exists() else []:
        if p.name not in built:  # a place without observations now: derived, rebuilt from evidence
            p.unlink()
            removed += 1
    summary = {"at": now(), "places": len(files), "stale_files": stale, "removed": removed,
               "coverage": dict(sorted(status.items()))}
    write_json(root / "intel" / "summary.json", summary)
    print(f"aggregate {city}: {json.dumps(summary, ensure_ascii=False)}")
    return summary
