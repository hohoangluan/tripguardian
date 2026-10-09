"""⑤ Ranking (docs/PLACE_DECISION.md §8). Every part is kept on the candidate to explain and debug the score."""

from bisect import bisect_left

from corpus.serving import feature

from .model import Cand

STATUS_W = {"VERIFIED": 1.0, "OUTDATED": 0.7, "UNCERTAIN": 0.5}
FULL_N = 3  # authors for full confidence in a feature


def conf(f: dict) -> float:
    return f["confidence"]["agreement"] * min(1.0, f["n"] / FULL_N) * STATUS_W[f["status"]]


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
        if (f is None or f["status"] == "UNCERTAIN") and w > 0:
            missing += w
        if f is None:
            continue
        if _contextual(f, ctx) == val:
            contrib = w * conf(f)
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


def score(cands: list[Cand], si, profile, cfg) -> None:
    ws = wants(si, profile)
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
                   "price": -round(profile.price_sensitivity * _price_norm(c.rec, cfg), 4)}
        c.score = round(sum(cfg.weights[k] * v for k, v in c.parts.items()), 4)
        c.matches = sorted(matches, key=lambda m: (-m[2], m[0]))
