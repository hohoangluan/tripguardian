"""⑥ Diversity and shortlist size (docs/PLACE_DECISION.md §9): one representative per near-duplicate group, picked by
MMR; the group's other places become its alternatives."""

import math

from corpus.serving import mmr

from .model import Cand


def display_group(c: Cand, cfg) -> str:
    if c.role == "meal":
        return "meal"
    g = c.rec["identity"].get("category_group")
    return next((k for k, gs in cfg.display_groups.items() if g in gs), "sights")


def sizes(si, days_n: int, n_anchor_exp: int, cfg) -> dict[str, int]:
    pace = si.pace.level or "normal"
    exp = max(1, days_n * cfg.per_day[pace] - n_anchor_exp)
    return {"experience": math.ceil(exp * cfg.spare_factor),
            "meal": math.ceil(days_n * cfg.meals_per_day * cfg.spare_factor)}


def pick(pool: list[Cand], k: int, cfg) -> tuple[list[Cand], dict[str, list[Cand]]]:
    if k <= 0 or not pool:
        return [], {}
    ranked = sorted(pool, key=lambda c: (-c.score, c.id))
    head = ranked[: k * cfg.pool_factor]
    order = mmr([c.rec for c in head], {c.id: c.score for c in head}, min(len(head), 2 * k))
    by = {c.id: c for c in pool}
    reps, alts, leader = [], {}, {}
    for i in order:
        g = by[i].rec.get("near_duplicate_group")
        if g is not None and g in leader:
            continue
        if len(reps) < k:
            reps.append(by[i])
            if g is not None:
                leader[g] = i
    for c in ranked:
        g = c.rec.get("near_duplicate_group")
        if g in leader and c.id != leader[g]:
            alts.setdefault(leader[g], []).append(c)
    return reps, {i: v[:3] for i, v in alts.items()}
