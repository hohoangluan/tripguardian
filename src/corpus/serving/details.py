"""The `details` block of a serving record (docs/CORPUS.md §5): intel clusters of free-text details -> what Place
Decision, Planning and the Web may show. Pure functions; thresholds in config/serving.yaml `details`.

A cluster is served from `min_authors` independent authors, or one authoritative source (the place's own site). Its
status is VERIFIED when the precision of its kind passed the label gate (or the place itself says it), else UNCERTAIN
(`unmeasured_precision`); a kind with enough labels that did not pass the gate is not served at all. Nothing is
guessed: no data gives an empty list or null.

place_block() works from one place's intel; finish() adds what needs every record: which phrase makes a place known
for something (rare among its category group), quieter / busier look-alikes and the walk to the night market.
"""

import collections
import math
import re
import statistics
from functools import cache

import yaml

from ..aggregate.estimates import NOT_TICKET, TICKET
from ..crawl.common.files import ROOT

SEASONS = ROOT / "config" / "seasons.yaml"
LISTS = ("order", "avoid", "activity", "photo_spot", "access", "booking", "bring", "situation")
PARKING = re.compile(r"gửi xe|giữ xe|đậu xe|đỗ xe|bãi xe|parking", re.I)
GATE_MIN_N = 30  # labels before a kind is judged (corpus.review.labels)
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
WORSE_FIRST = ("bad", "conditional", "good")  # a tie between verdicts takes the more cautious one
AUDIENCES = ("adult", "child", "senior")


@cache
def seasons() -> list[dict]:
    """config/seasons.yaml rows {match, months, source}: months of a season a source names without a month."""
    return yaml.safe_load(SEASONS.read_text(encoding="utf-8")).get("seasons") or []


def _status(cluster: dict, label: dict | None, min_authors: int) -> tuple[str, str | None] | None:
    """(status, reason) of a cluster, or None when it is not served."""
    if cluster["n"] < min_authors and not cluster["authority"]:
        return None
    if label and label["correct"] + label["wrong"] >= GATE_MIN_N and not label["gate"]:
        return None
    if cluster["authority"] or (label and label["gate"]):
        return "VERIFIED", None
    return "UNCERTAIN", "unmeasured_precision"


def item(cluster: dict, kind: str, quality: dict, cfg: dict) -> dict | None:
    """One served cluster as {text, n, status, reason, evidence} plus the numbers its quotes stated."""
    got = _status(cluster, quality.get((f"detail.{kind}", "*")), cfg["min_authors"])
    if got is None:
        return None
    out = {"text": cluster["text"], "n": cluster["n"], "status": got[0], "reason": got[1],
           "evidence": cluster["evidence"][:5]}
    for key in ("amount_vnd", "audience", "unit", "min_people"):
        if cluster.get(key) is not None:
            out[key] = cluster[key]
    if cluster.get("months"):
        out["months"] = sorted(int(m) for m in cluster["months"])
    if cluster.get("days"):
        out["days"] = sorted(cluster["days"], key=lambda d: DAYS.index(d))
    if len(cluster.get("hours") or ()) == 1:
        out["hour"] = cluster["hours"][0]
    return out


def served(intel: dict, kind: str, quality: dict, cfg: dict) -> list[tuple[dict, dict]]:
    """(cluster, item) of the served clusters of a kind, biggest first."""
    out = [(c, i) for c in (intel.get("details") or {}).get(kind, []) if (i := item(c, kind, quality, cfg))]
    return sorted(out, key=lambda x: (-x[0]["n"], x[0]["text"].casefold()))


def _cost(intel: dict, quality: dict, cfg: dict, entry_free: bool) -> dict | None:
    fees = served(intel, "fee", quality, cfg)
    tickets = (intel.get("operation") or {}).get("tickets_vnd") or {}
    entry = {a: ({"vnd": int(statistics.median_low(tickets[a])), "source": "official"} if tickets.get(a) else None)
             for a in AUDIENCES}
    parking, extras, per_party = None, [], []
    official_only = all(e is None or e["source"] == "official" for e in entry.values())
    for c, i in fees:
        text = c["text"]
        if PARKING.search(text):
            parking = parking or i
        elif TICKET.search(text) and not NOT_TICKET.search(text) and c.get("unit") in (None, "person"):
            a = c.get("audience") if c.get("audience") in AUDIENCES else "adult"  # a bare "vé" is the usual adult ticket
            if entry[a] is None and c.get("amount_vnd"):
                entry[a] = {"vnd": c["amount_vnd"], "source": "official" if c["authority"] else "reviews"}
                official_only &= bool(c["authority"])
            continue
        elif c.get("unit") in ("group", "vehicle"):
            per_party.append(i)
        else:
            extras.append(i)
        official_only &= bool(c["authority"])
    if entry_free and entry["adult"] is None:
        entry["adult"] = {"vnd": 0, "source": "reviews"}
        official_only = False
    if not (any(entry.values()) or parking or extras or per_party):
        return None
    total = None
    if entry["adult"] is not None:
        base = entry["adult"]["vnd"] + (parking or {}).get("amount_vnd", 0)
        total = {"base": base, "with_extras": base + sum(x.get("amount_vnd", 0) for x in extras)}
    return {"entry": entry, "parking": parking, "extras": extras[:cfg["max_items"]],
            "per_party": per_party[:cfg["max_items"]], "total_vnd": total,
            "kind": "fact" if total and official_only else "estimate"}


def _window(intel: dict, kind: str, quality: dict, cfg: dict) -> dict:
    rows = served(intel, kind, quality, cfg)
    by_tod, hours = collections.Counter(), set()
    for c, _ in rows:
        by_tod.update(c.get("time_of_day") or {})
        hours.update(c.get("hours") or ())
    return {"by_time_of_day": dict(by_tod), "hours": sorted(hours), "items": [i for _, i in rows][:cfg["max_items"]]}


def _months(intel: dict, kind: str, cfg: dict) -> list[int]:
    """Months at least min_authors authors named for the kind (every cluster counts, served or not: months are
    summed over phrasings)."""
    count = collections.Counter()
    for c in (intel.get("details") or {}).get(kind, []):
        for m, n in (c.get("months") or {}).items():
            count[int(m)] += n
    return sorted(m for m, n in count.items() if n >= cfg["min_authors"])


def _last_entry(intel: dict, quality: dict, cfg: dict) -> dict | None:
    official = (intel.get("operation") or {}).get("last_entry")
    if official:
        return {"time": official, "source": "official"}
    for c, _ in served(intel, "last_entry", quality, cfg):
        if len(c.get("hours") or ()) == 1:
            return {"time": c["hours"][0], "source": "official" if c["authority"] else "reviews"}
    return None


def _fit(intel: dict, quality: dict, cfg: dict) -> dict:
    by_who = collections.defaultdict(list)
    for c in (intel.get("details") or {}).get("fit", []):
        if c.get("who"):
            by_who[c["who"]].append(c)
    label = quality.get(("detail.fit", "*"))
    out = {}
    for who, clusters in sorted(by_who.items()):
        total = {"n": sum(c["n"] for c in clusters), "authority": any(c["authority"] for c in clusters)}
        got = _status(total, label, cfg["min_authors"])
        if got is None:
            continue
        dist = collections.Counter()
        for c in clusters:
            dist.update(c.get("verdicts") or {})
        top = max(WORSE_FIRST, key=lambda v: (dist[v], -WORSE_FIRST.index(v)))
        ranked = sorted(clusters, key=lambda c: (-c["n"], c["text"].casefold()))
        out[who] = {"value": top, "distribution": dict(dist), "n": total["n"], "reasons": [c["text"] for c in ranked][:cfg["max_items"]],
                    "status": got[0], "evidence": [e for c in ranked for e in c["evidence"]][:5]}
    return out


def place_block(intel: dict, quality: dict, cfg: dict, entry_fee: dict | None = None) -> dict:
    """The `details` block of one place. entry_fee: its served `entry_fee` feature (free entry gives a total of 0)."""
    cfg = cfg or {}
    quality = quality or {}
    free = bool(entry_fee and entry_fee["value"] == "free" and entry_fee["status"] in ("VERIFIED", "OUTDATED"))
    known = [(i, c["text"]) for c, i in served(intel, "known_for", quality, cfg)]
    return {
        "known_for": {"headline": None, "more": []},
        "_known_for": known,
        **{kind: [i for _, i in served(intel, kind, quality, cfg)][:cfg["max_items"]] for kind in LISTS},
        "cost": _cost(intel, quality, cfg, free),
        "timing": {"best_time": _window(intel, "best_time", quality, cfg),
                   "avoid_time": _window(intel, "avoid_time", quality, cfg),
                   "best_months": _months(intel, "best_time", cfg), "avoid_months": _months(intel, "avoid_time", cfg),
                   "schedule": [i for _, i in served(intel, "schedule", quality, cfg)][:cfg["max_items"]],
                   "last_entry": _last_entry(intel, quality, cfg)},
        "fit": _fit(intel, quality, cfg),
        "relations": {"quieter": [], "busier": []},
        "walk_to_night_market_min": None,
    }


def _tokens(text: str, stop: frozenset) -> frozenset:
    return frozenset(w for w in re.findall(r"\w+", text.casefold()) if w not in stop)


def _same(a: frozenset, b: frozenset, jaccard: float) -> bool:
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= jaccard or a <= b or b <= a


def _known_for(records: list[dict], cfg: dict) -> None:
    """headline / more by rarity: score = n * log(places of the category group / (1 + other places of the group that
    have a matching phrase)); a phrase every place has scores 0 and is no headline."""
    stop = frozenset(cfg["stopwords"])
    by_group = collections.defaultdict(list)
    for r in records:
        by_group[r["identity"].get("category_group")].append(r)
    for group in by_group.values():
        index = collections.defaultdict(set)  # token -> positions of records with a candidate holding it
        cands = [[(i, text, _tokens(text, stop)) for i, text in r["details"]["_known_for"]] for r in group]
        for pos, cs in enumerate(cands):
            for _, _, toks in cs:
                for t in toks:
                    index[t].add(pos)
        for pos, r in enumerate(group):
            scored = []
            for i, text, toks in cands[pos]:
                near = {p for t in toks for p in index[t]} - {pos}
                others = sum(any(_same(toks, o, cfg["cluster_jaccard"]) for _, _, o in cands[p]) for p in near)
                score = i["n"] * math.log(len(group) / (1 + others))
                if score > 0:
                    scored.append((-score, text.casefold(), i))
            scored.sort(key=lambda x: x[:2])
            r["details"]["known_for"] = {"headline": scored[0][2] if scored else None,
                                         "more": [x[2] for x in scored[1:1 + cfg["known_for_more"]]]}
    for r in records:
        r["details"].pop("_known_for", None)


def _crowded(r: dict) -> float | None:
    dist = (r.get("environment", {}).get("crowd") or {}).get("distribution")
    total = sum(dist.values()) if dist else 0
    return dist.get("high", 0) / total if total else None


def _relations(records: list[dict], cfg: dict) -> None:
    groups = collections.defaultdict(list)
    for r in records:
        if r.get("near_duplicate_group") is not None:
            groups[r["near_duplicate_group"]].append(r)
    for members in groups.values():
        for a in members:
            ca, va = _crowded(a), (a["provenance"].get("voices") or 0)
            for b in members:
                cb, vb = _crowded(b), (b["provenance"].get("voices") or 0)
                if a is b or ca is None or cb is None:
                    continue
                if vb > va and cb > ca:
                    a["details"]["relations"]["busier"].append(b["id"])
                elif vb < va and cb < ca:
                    a["details"]["relations"]["quieter"].append(b["id"])
    for r in records:
        for k, ids in r["details"]["relations"].items():
            r["details"]["relations"][k] = sorted(ids)[:cfg["max_items"]]


def _walk(records: list[dict], cfg: dict) -> None:
    from .groups import km  # groups imports record, which imports this module
    market = next((r for r in records if r["id"] == cfg["night_market_fid"]), None)
    for r in records:
        r["details"]["walk_to_night_market_min"] = None
        if market is None or r is market:
            continue
        a, b = r["identity"], market["identity"]
        if None in (a.get("lat"), a.get("lng"), b.get("lat"), b.get("lng")):
            continue
        minutes = int(km(a, b) * 1000 * cfg["walk_road_factor"] / cfg["walk_m_per_min"] + 0.5)
        if minutes <= cfg["walk_max_min"]:
            r["details"]["walk_to_night_market_min"] = minutes


def _season_months(records: list[dict], rows: list[dict]) -> None:
    for r in records:
        t = r["details"]["timing"]
        for kind, months in (("best_time", "best_months"), ("avoid_time", "avoid_months")):
            texts = [i["text"].casefold() for i in t[kind]["items"]]
            extra = {m for row in rows if any(row["match"].casefold() in x for x in texts) for m in row["months"]}
            t[months] = sorted(set(t[months]) | extra)


def finish(records: list[dict], cfg: dict, rows: list[dict] | None = None) -> None:
    """What needs every record (after near_duplicate_groups): known_for, relations, the walk, and the months of the
    seasons in config/seasons.yaml (rows; default: the file)."""
    _known_for(records, cfg)
    _relations(records, cfg)
    _walk(records, cfg)
    _season_months(records, seasons() if rows is None else rows)
