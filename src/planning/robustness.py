"""Robustness (docs/PLANNING.md ⓕ, docs/ARCHITECTURE.md §12): solid / feasible / fragile.

Fixed perturbations from config, never random. Each scenario re-runs the chosen order of every day and counts the
places that no longer fit: a visit outside its hours, or one after which the day's end point cannot be reached in
time. Buffers are what absorbs a delay, so a delay they swallow loses nothing. A plan that travels on a rough matrix
is capped at feasible: rough minutes cannot prove it solid.
"""

import math
from dataclasses import replace

from .schedule import DayCtx, simulate
from .traits import exposure
from .travel import Travel

LEVEL_LABEL = {"solid": "Vững", "feasible": "Khả thi", "fragile": "Mong manh"}
VISIT_KEYS = ("short", "typical", "long")


def _scaled_travel(travel: Travel, pct: int) -> Travel:
    legs = [[(m if mode == "none" else math.ceil(m * (100 + pct) / 100), mode) for m, mode in row]
            for row in travel.legs]
    return Travel(travel.ids, legs, travel.source, travel.fetched_at, travel.rough_pairs)


def _perturbed(cx: DayCtx, sc: dict) -> DayCtx:
    if sc.get("start_min"):
        cx = replace(cx, day=replace(cx.day, start=cx.day.start + sc["start_min"]))
    if sc.get("visit_pct"):
        pct = sc["visit_pct"]
        cx = replace(cx, places={i: replace(p, visit={**p.visit, **{k: math.ceil(p.visit[k] * (100 + pct) / 100)
                                                                     for k in VISIT_KEYS if k in p.visit}})
                                 for i, p in cx.places.items()})
    if sc.get("travel_pct"):
        cx = replace(cx, travel=_scaled_travel(cx.travel, sc["travel_pct"]))
    return cx


def lost_places(order: tuple, cx: DayCtx) -> list[str]:
    """The stops of one day that no longer fit when the day runs as cx says."""
    if not order:
        return []
    r = simulate(list(order), cx)
    bad = {v.place_id for v in r.violations if v.kind == "hours"}
    end_node = cx.day.end_node
    for it in r.items:
        if it.kind == "visit":
            back = cx.travel.leg(it.place_id, end_node)[0] if end_node else 0
            if it.end + back > cx.day.end:
                bad.add(it.place_id)
    return [i for i in order if i in bad]


def _describe(sc: dict) -> str:
    if sc.get("rain"):
        return "mưa vào ngày dự báo mưa"
    if sc.get("start_min"):
        return f'xuất phát trễ {sc["start_min"]} phút'
    if sc.get("visit_pct"):
        return f'mỗi nơi ở lâu hơn {sc["visit_pct"]}%'
    return f'di chuyển chậm hơn {sc["travel_pct"]}%'


def robustness(ctxs: list[DayCtx], results: list, travel_source: str) -> dict:
    cfg = ctxs[0].cfg
    rob = cfg.robustness
    forecast = any(cx.rain is not None for cx in ctxs)
    scenarios, skipped = [], []
    for sc in rob["scenarios"]:
        if sc.get("rain"):
            if not forecast:
                skipped.append(sc["id"])
                continue
            lost = [i for cx, r in zip(ctxs, results) if cx.rain is not None and cx.rain >= cfg.rain_high
                    for i in r.order if exposure(cx.places[i]) == "exposed"]
        else:
            lost = [i for cx, r in zip(ctxs, results) for i in lost_places(r.order, _perturbed(cx, sc))]
        scenarios.append({"id": sc["id"], "tier": sc["tier"], "text": _describe(sc), "lost": lost})
    if all(len(s["lost"]) <= rob["solid_max_lost"] for s in scenarios):
        level = "solid"
    elif all(len(s["lost"]) <= rob["feasible_max_lost"] for s in scenarios if s["tier"] == "small"):
        level = "feasible"
    else:
        level = "fragile"
    names = {i: p.name for cx in ctxs for i, p in cx.places.items()}
    reasons = [f'{s["text"]}: mất {len(s["lost"])} nơi ({", ".join(names[i] for i in s["lost"])})'
               for s in scenarios if s["lost"]]
    travels = any(i.kind == "travel" for r in results for i in r.items)
    if level == "solid" and travel_source == "rough" and travels:
        level = "feasible"
        reasons.append("Thời gian di chuyển là ước lượng thô nên không kết luận Vững.")
    if not reasons:
        reasons.append("Chịu được mọi kịch bản nhiễu đã thử.")
    if skipped:
        reasons.append("Chưa biết thời tiết: chưa thử kịch bản mưa.")
    return {"level": level, "label": LEVEL_LABEL[level], "reasons": reasons, "scenarios": scenarios,
            "breaking": [s["id"] for s in scenarios if s["lost"]], "skipped": skipped}
