"""⑤ Ranking (docs/P3_PLACE_DECISION.md §8). Every part is kept on the candidate to explain and debug the score."""

import math
from bisect import bisect_left
from functools import cache

from corpus.ontology import load as load_ontology
from corpus.serving import feature

from .diversify import display_group
from .model import Cand

STATUS_W = {"VERIFIED": 1.0, "OUTDATED": 0.7, "UNCERTAIN": 0.5}
STRONG_N = 30  # independent authors at which a feature counts in full
SALIENT_RATE = 0.03  # share of a place's authors at which an experience says what it is (config/serving.yaml)


def strength(n: int) -> float:
    """How much n independent authors weigh: a log scale that saturates at STRONG_N (1 -> 0.2, 3 -> 0.4, 10 -> 0.7),
    so "83 người nhắc" outranks "3 người nhắc" and one author is still something."""
    return min(1.0, math.log1p(max(0, n)) / math.log1p(STRONG_N))


def conf(f: dict, experience: bool = False) -> float:
    """How much one feature counts: authors (log scale), their agreement and the status. An undisputed value whose
    extractor precision is only unmeasured is settled by many authors. An experience few of a place's authors
    mention (below SALIENT_RATE) is not what the place is about and counts that much less."""
    agree, w = f["confidence"]["agreement"], STATUS_W[f["status"]]
    if f["status"] == "UNCERTAIN" and f.get("reason") == "unmeasured_precision":
        w += (1 - w) * agree * strength(f["n"])
    rate = f.get("mention_rate")
    salience = min(1.0, rate / SALIENT_RATE) if experience and rate is not None else 1.0
    return agree * strength(f["n"]) * w * salience


@cache
def _experience(fid: str) -> bool:
    f = load_ontology().features.get(fid)
    return f is not None and f.group == "experience"


def wants(si, profile) -> list[tuple[str, str, dict | None, int]]:
    """(feature, value, context, weight) the ranking looks for: Search Input, then the session's own additions."""
    out = [(w.feature, w.value, w.context, w.weight) for w in si.soft_weights if w.weight != 0]
    return out + [(s.feature, s.value, None, s.weight) for s in profile.soft]


def _contextual(f: dict, ctx: dict | None) -> str:
    for k, v in (ctx or {}).items():
        d = f["by_context"].get(f"{k}={v}")
        if d:
            return max(d, key=d.get)
    return f["value"]


def preference(rec: dict, ws) -> tuple[float, float, list[tuple]]:
    """(preference fit, uncertainty, matches). No evidence adds 0, never a minus; it counts as uncertainty."""
    total = sum(abs(w) for *_, w in ws)
    if not total:
        return 0.0, 0.0, []
    fit = missing = 0.0
    matches = []
    for fid, val, ctx, w in ws:
        f = feature(rec, fid)
        if f is None and w > 0:
            missing += w
        elif f is not None and f["status"] == "UNCERTAIN" and w > 0:  # many agreeing authors are not uncertain
            missing += w * (1 - f["confidence"]["agreement"] * strength(f["n"]))
        if f is None:
            continue
        if _contextual(f, ctx) == val:
            contrib = w * conf(f, _experience(fid))
            fit += contrib
            matches.append((fid, val, round(contrib, 4), f["n"]))
    return fit / total, missing / total, matches


def preference_fit(rec: dict, soft_weights: list[dict]) -> tuple[float, list[tuple]]:
    """Public: how one serving record matches a trip's soft wishes (Search Input soft_weights as dicts), as
    (fit in -1..1, matches). Used outside Decision (companion's nearby picks) without building candidates."""
    ws = [(w["feature"], w["value"], w.get("context"), w["weight"]) for w in soft_weights if w.get("weight")]
    fit, _, matches = preference(rec, ws)
    return fit, matches


def _price_norm(rec: dict, cfg) -> float:
    p = rec["operation"].get("price_per_person")
    if not p:
        return 0.0
    v = p["value"]
    lo = v.get("min_vnd") or 0
    mid = (lo + (v.get("max_vnd") or lo)) / 2
    return min(1.0, mid / cfg.price_ref_vnd)


def liked_groups(si) -> tuple[str, ...]:
    """Display groups the trip names as its main interest ("thích cà phê" -> chill); empty when Trip did not say."""
    return tuple(getattr(si, "liked_groups", None) or ())


def stars(score: float, full: float, cfg) -> float:
    """Score on the trip's fixed ceiling `full`, 0..5 and not snapped to whole or half stars; the neighbours never
    move it. Two decimals only keep the JSON free of float noise."""
    return round(max(0.0, min(5.0, score / full * 5)), 2)


def fit_level(n: float | None, cfg) -> str | None:
    return next((label for low, label in cfg.stars["levels"] if n >= low), None) if n is not None else None


def score(cands: list[Cand], si, profile, cfg) -> None:
    ws = wants(si, profile)
    liked = set(liked_groups(si))
    # What the user steers: nearness, taste (when the trip has any) and the liked group. nov / exp / pop only nudge.
    full = cfg.weights["ctx"] + (cfg.weights["pref"] if ws else 0.0) + (cfg.weights["like"] if liked else 0.0)
    avoid = (profile.crowd_tolerance or si.pace.crowd_tolerance) == "avoid"
    voices = sorted(c.rec["provenance"].get("voices") or 0 for c in cands)
    top = max(1, len(voices) - 1)
    visited = set(si.novelty.visited) | set(profile.visited)
    nov_of = {"new": -1.0, "familiar": 0.3}
    for c in cands:
        pref, unc, matches = preference(c.rec, ws)
        pop = min(1.0, bisect_left(voices, c.rec["provenance"].get("voices") or 0) / top)
        exp = si.context.experience
        c.parts = {"ctx": c.fit, "pref": round(pref, 4),
                   "nov": nov_of.get(si.novelty.level, 0.0) if c.id in visited else 0.0,
                   "exp": pop if exp == "first" else 1 - pop if exp == "returning" else 0.0,
                   "pop": round(pop, 4), "unc": -round(unc, 4),
                   "price": -round(profile.price_sensitivity * _price_norm(c.rec, cfg), 4),
                   "crowd": -round(c.crowd, 4) if avoid else 0.0,
                   "like": 1.0 if display_group(c, cfg) in liked else 0.0}
        c.score = round(sum(cfg.weights[k] * v for k, v in c.parts.items()), 4)
        c.stars = stars(c.score, full, cfg) if ws or liked else None
        c.matches = sorted(matches, key=lambda m: (-m[2], m[0]))
