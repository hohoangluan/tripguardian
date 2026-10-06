"""Aggregate (docs/CORPUS.md §5), code only: every source's observations of a place -> one intel file.

Reads data/*/observations/*.json and data/*/photo_observations/*.json without knowing the source, writes data/intel/places/<fid_dir>.json and removes
every other file there (a place that has no observation file now): the folder is one build. Observation files of an
older ontology version still count until observe re-runs them (values the ontology dropped are left out);
`observation_versions` and the summary's `stale_files` say how many. Per feature:
votes (one per author; an author who gave k different values gives each 1/k), context breakdown, confidence parts,
trend of the newer half of the dated evidence against the older half. A value declared by an authoritative source
(Maps attributes) is served without a person when no other source contradicts it; a contradiction makes it uncertain.
`mention_rate` = people who named the feature / the place's `voices` (authors whose words were read): a value
named by 1 of 200 reviewers is weak evidence even at agreement 1.0.
Targeted samples (observation `sample`: Maps' lowest / highest rated reviews, keyword hits; corpus.observe.TARGETED)
count only for effort and facts of the place (corpus.observe.targeted_ok), with their authors (`voices_targeted`)
added to those features' mention-rate denominator; never for opinions, and their stars never for rating_trend.
Labels (a person's, else the Judge model's, corpus.review) are applied first: an observation labelled wrong is
left out. Measured quality (docs/CORPUS.md §6): `quality` = the label precision of the top value
(review.label_stats); `checked` counts the top value's authors whose claims were labelled correct; `servable` = the
value may be served by itself: declared by an authoritative source, its precision passed the label gate, every
author of it was checked correct, or a person accepted it. Only a value that widens a choice (`verify: always`, not a
caution value) with unchecked authors `needs_review` (not served); a conflict with an authoritative source is served
uncertain. A person's `disable` (decisions.jsonl kind feature_review, id "<fid>#<feature>") makes the feature
`disabled` and never servable, `accept` clears needs_review, `report` / `refresh` set it.
Who speaks: a business about itself (author "<source>:owner:...", its Maps photos and its TikTok account) only
counts for what it can show or state as the operator (OWNER_FEATURES, effort only as "present"), never for quality,
crowd or suitability; Maps photos whose poster could not be read share one voice per place. Two Maps entries the
Judge found to be one place (corpus.judge.merges) are aggregated as the canonical one; the other gets no file.
`estimates` (estimates.py): category group, visit time range and entry fee in VND, each with its source.
Place facts (popular times, price, hours, closure, tickets) pass through as `operation`; a place's own website
(source "official") wins over Maps for hours and entry fee (merge_hours, estimates), disagreeing days kept, name / category / location as `identity`, popular times also summed up by day type x time of day. Conflicts are kept as distributions, never flattened.
"""

import collections
import json
from datetime import date

from ..crawl.common.files import data_dir, now, safe_name, write_json
from ..observe import CONTEXT_KEYS, TARGETED, targeted_ok
from ..ontology import UNKNOWN, Feature, Ontology, load as load_ontology
from ..judge import merges
from ..review import decisions, label_key, label_stats, label_verdicts
from .estimates import estimates

AGREEMENT_MIN = 0.6
TREND_MIN = 5  # authors on each side
TREND_DELTA = 0.2  # change in the share of the top value
RATING_DELTA = 0.5  # stars
COMPLETE_FEATURES, COMPLETE_N = 3, 3
# Effort that people name only when it is there (user, 2026-10-06): a place nobody calls steep, a long walk or a rough
# road -- in any review, video or photo -- is served as `absent`; one person naming it (a claim the Judge did not call
# wrong) is enough to serve `present`. Even where these are real only ~1.5-3.6% of reviewers name them, so silence
# is weak evidence; the user accepted that and leaves the correction to travellers' feedback on the place.
SILENCE_FEATURES = ("steep_or_stairs", "long_walk", "rough_road_access")
SILENCE_MIN_MENTIONS = 1  # authors naming `present`
AUTHORITATIVE = {"gmaps_attribute", "official_page"}
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
               "tiktok_caption": "video", "tiktok_frame": "video", "tiktok_comment": "comment",
               "gmaps_photo": "photo", "official_page": "official"}


# what a business's own photos and videos can show, or what it states as the operator; never quality, crowd,
# noise, cleanliness or suitability (effort features only as "present": a business admitting stairs or a rough road)
OWNER_FEATURES = {"scenic_view", "cloud_hunting", "sunset_view", "photo_spot", "nature", "flower_garden",
                  "heritage_architecture", "cozy_decor", "live_music", "adventure_activity", "hiking", "animals",
                  "local_specialty_food", "hands_on_workshop", "pick_your_own", "cultural_show", "camping",
                  "tasting_available", "costume_rental", "setting", "outdoor_seating", "spacious", "small_space",
                  "parking", "entry_fee", "booking_needed", "vegetarian_options", "cash_only"}


def _who(o: dict) -> str:
    if not o.get("author") and o["source_type"] == "gmaps_photo":
        return f"gmaps:anon:{o['place_fid']}"  # poster not read: one voice for all such photos of the place
    return o.get("author") or o["id"]


def owner(o: dict) -> bool:
    return ":owner:" in (o.get("author") or "")


def usable(o: dict, feat: Feature, verdicts: dict[str, str]) -> bool:
    """Not labelled wrong (or unsure on a second look), not a targeted sample (lowest / highest rated, keyword hits) speaking to an opinion whose
    share it would skew, and not a business vouching for itself beyond what it can show."""
    if verdicts.get(label_key(o["source_id"], o["feature"], o["value"], o["span"]["quote"])) in ("wrong", "unsure_again"):
        return False
    if o.get("sample") in TARGETED and not targeted_ok(feat):
        return False
    if owner(o):
        return o["feature"] in OWNER_FEATURES or (feat.group == "effort" and o["value"] == "present")
    return True


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


def feature_signal(feat: Feature, obs: list[dict], as_of: date, voices: int = 0,
                   verdicts: dict[str, str] | None = None) -> dict:
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
    voters = {_who(o) for o in unique if o["value"] == t}
    verdicts = verdicts or {}
    checked = {_who(o) for o in unique if o["value"] == t and o["source_type"] not in AUTHORITATIVE
               and verdicts.get(label_key(o["source_id"], o["feature"], o["value"], o["span"]["quote"])) == "correct"}
    people_t = {_who(o) for o in unique if o["value"] == t and o["source_type"] not in AUTHORITATIVE}
    all_checked = bool(people_t) and checked >= people_t
    if authority or conflict:
        needs_review = False  # declared and undisputed, or disputed: served uncertain with both sides kept
    else:
        needs_review = (feat.verify == "always" and t not in feat.caution_values and not all_checked) or (
            feat.verify == "always" and t in feat.caution_values and len(voters) < 2 and not all_checked)
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
        "checked": {"authors": len(checked), "of": len(people_t), "all": all_checked},
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


def merge_hours(maps: dict | None, official: dict | None) -> dict:
    """Official hours win for the days the site names, Maps' for the others; a day both state differently is kept in
    `hours_conflict` (Maps' value) so the record can say the hours are not settled."""
    if not official:
        return {"hours": maps, "hours_source": "maps" if maps else None, "hours_conflict": None}
    conflict = {d: v for d, v in (maps or {}).items() if d in official and official[d] != v}
    return {"hours": {**(maps or {}), **official}, "hours_source": "official", "hours_conflict": conflict or None}


def silence_signal() -> dict:
    """The signal of a SILENCE_FEATURES feature nobody named: `absent`, with no evidence behind it."""
    return {"n": 0, "distribution": {}, "top_value": "absent", "status": "signal", "authority": None, "by_context": {},
            "by_source": {}, "mention_rate": 0.0,
            "confidence": {"independent_sources": 0, "agreement": None, "freshness_days": None, "source_types": []},
            "trend": None, "needs_review": False, "checked": {"authors": 0, "of": 0, "all": False},
            "observation_ids": []}


def inferred(sig: dict, how: str, quality: dict | None, decision: str | None) -> dict:
    """A SILENCE_FEATURES signal served by the rule, not by the label gate (`inferred` = "silence" | "mentioned"). A
    person's or a traveller's report still holds it back (judge sets needs_review) and a disable still removes it."""
    sig = judge(sig, quality, decision)
    if sig.get("status") != "disabled":
        sig["servable"], sig["inferred"] = True, how
    return sig


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
        sig["servable"] = bool(sig["authority"] or decision == "accept" or (quality and quality["gate"])
                               or (sig.get("checked") or {}).get("all"))
    return sig


def aggregate_place(files: list[dict], ont: Ontology, quality: dict | None = None,
                    reviewed: dict[str, str] | None = None, verdicts: dict[str, str] | None = None) -> dict:
    """quality: (feature, value) -> label stats row; reviewed: feature -> a person's latest feature_review decision;
    verdicts: label content key -> latest label (person over Judge)."""
    verdicts = verdicts or {}
    as_of = max(date.fromisoformat(f["as_of"]) for f in files)
    by_feature = collections.defaultdict(list)
    for f in files:
        for o in f["observations"]:
            if ont.valid(o["feature"], o["value"]) and usable(o, ont.features[o["feature"]], verdicts):
                by_feature[o["feature"]].append(o)
    voices = sum(f.get("voices") or 0 for f in files)
    voices_targeted = sum(f.get("voices_targeted") or 0 for f in files)  # count only where targeted samples count
    quality, reviewed = quality or {}, reviewed or {}
    features = {}
    for fid in ont.features:
        if fid in by_feature:
            feat = ont.features[fid]
            sig = feature_signal(feat, by_feature[fid], as_of,
                                 voices + voices_targeted if targeted_ok(feat) else voices, verdicts)
            features[fid] = judge(sig, quality.get((fid, sig["top_value"])), reviewed.get(fid))
    for fid in SILENCE_FEATURES:
        said = [o for f in files for o in f["observations"] if o["feature"] == fid and ont.valid(fid, o["value"])
                and verdicts.get(label_key(o["source_id"], fid, o["value"], o["span"]["quote"])) != "wrong"]
        if not said:
            if voices:  # someone's words were read and none named it
                features[fid] = inferred(silence_signal(), "silence", None, reviewed.get(fid))
            continue
        if features.get(fid, {}).get("servable"):
            continue
        if (len({_who(o) for o in said if o["value"] == "present"}) >= SILENCE_MIN_MENTIONS
                and all(o["value"] == "present" for o in said)):  # "có" and "không" both said: a real conflict
            feat = ont.features[fid]
            sig = feature_signal(feat, said, as_of, voices + voices_targeted if targeted_ok(feat) else voices, verdicts)
            features[fid] = inferred(sig, "mentioned", quality.get((fid, "present")), reviewed.get(fid))
    ratings = [r for f in files for r in f.get("ratings", []) if r.get("sample") not in TARGETED]
    proposed = collections.defaultdict(list)
    for f in files:
        for p in f.get("proposed", []):
            proposed[p["label"].strip().casefold()].append(p.get("author"))
    facts, official = {}, {}
    for f in files:
        for k, v in (f.get("place_facts") or {}).items():
            if v is not None:
                (official if f.get("source") == "official" else facts).setdefault(k, v)
    hours = merge_hours(facts.get("hours"), official.get("hours"))
    identity = {}
    for f in files:
        for k, v in (f.get("place") or {}).items():
            if v is not None:
                identity.setdefault(k, v)
    return {
        "place_fid": files[0]["place_fid"],
        "merged": sorted({f["place_fid"] for f in files} - {files[0]["place_fid"]}),
        "place_name": next((f["place_name"] for f in files if f.get("place_name")), None),
        "as_of": as_of.isoformat(), "ontology_version": ont.version, "identity": identity, "voices": voices,
        "voices_targeted": voices_targeted,
        "features": features, "coverage": coverage(features, ont),
        "operation": {"price_range": facts.get("price"), **hours, "closure": facts.get("closure"),
                      "crowd_by_time": crowd_by_time(facts.get("popular_times")),
                      "popular_times": facts.get("popular_times")},
        "estimates": estimates(identity.get("category"), features, [o for os in by_feature.values() for o in os],
                               (facts.get("tickets") or {}).get("usd"), official.get("tickets_vnd"),
                               facts.get("time_spent")),
        "rating_trend": rating_trend(ratings) if ratings else None,
        "proposed_features": sorted(({"label": k, "count": len(v), "authors": len(set(v))} for k, v in proposed.items()),
                                    key=lambda x: (-x["count"], x["label"])),
    }


def run(city: str) -> dict:
    """city is accepted for a uniform CLI; observations are already per place."""
    ont = load_ontology()
    root = data_dir()
    files, inputs, stale = collections.defaultdict(list), collections.defaultdict(list), 0
    canonical = merges()
    for p in sorted([*root.glob("*/observations/*.json"), *root.glob("*/photo_observations/*.json")]):
        f = json.loads(p.read_text(encoding="utf-8"))
        stale += f.get("ontology_version") != ont.version
        fid = canonical.get(f["place_fid"], f["place_fid"])
        files[fid].append(f)
        inputs[fid].append(p.relative_to(root).as_posix())
    for fid in files:  # the canonical entry's own files first: its name, place facts and identity win
        files[fid].sort(key=lambda f: f["place_fid"] != fid)
    status = collections.Counter()
    out = root / "intel" / "places"
    quality = {(r["feature"], r["value"]): {k: r[k] for k in ("precision", "lower", "correct", "wrong", "gate")}
               for r in label_stats()["rows"] if r["correct"] + r["wrong"]}
    reviewed = collections.defaultdict(dict)
    for item, d in decisions("feature_review").items():
        place_fid, _, feature = item.partition("#")
        if d != "undo":
            reviewed[place_fid][feature] = d
    verdicts = label_verdicts()
    for fid, fs in files.items():
        if fs[0]["place_fid"] != fid:  # only a merged entry's files: the canonical one has no evidence of its own
            fs = [{**fs[0], "place_fid": fid, "observations": [], "place": {}, "place_facts": {}, "voices": 0,
                   "ratings": [], "proposed": []}] + fs
        intel = aggregate_place(fs, ont, quality, reviewed.get(fid), verdicts)
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
