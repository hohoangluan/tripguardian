"""Optional changes backed by real candidates and an independently validated trial. Never edits a plan."""

from dataclasses import replace

from requirements import allowed, category_for

from .places import build_places
from .schedule import simulate
from .settings import fmt
from .timefit import period_load, period_windows, windows_for
from .validate import validate

PERIOD_TEXT = {"morning": "buổi sáng", "midday": "giữa trưa", "afternoon": "buổi chiều", "evening": "buổi tối"}
GROUPS = {"morning": {"museum", "religious", "attraction", "nature", "garden_farm"},
          "midday": {"cafe", "spa", "dessert", "restaurant"}, "afternoon": {"garden_farm", "nature"},
          "evening": {"bar"}}


def _gaps(a: int, b: int, items) -> list[tuple[int, int]]:
    cursor, out = a, []
    for item in sorted(items, key=lambda i: i.start):
        if item.kind == "wait" or item.end <= a or item.start >= b:
            continue
        lo, hi = max(a, item.start), min(b, item.end)
        if lo > cursor:
            out.append((cursor, lo))
        cursor = max(cursor, hi)
    if cursor < b:
        out.append((cursor, b))
    return out


def _suited(place, period: str, cx) -> bool:
    if place.kind == "meal":
        return period in {"midday", "evening"}
    rules = windows_for(place, cx)
    if rules:
        return any(max(a, o) < min(b, c) for rule in rules for a, b in rule.windows
                   for o, c in period_windows(period, cx))
    return category_for(place.rec) in GROUPS[period]


def recommend(ctxs: list, results: list, decision: dict, by_id: dict) -> list[dict]:
    if not ctxs or not ctxs[0].cfg.time_suitability.get("enabled", False):
        return []
    cfg = ctxs[0].cfg
    tc = decision["trip_context"]
    hard = tc.get("hard_filters") or []
    selected = {pid for r in results for pid in r.order}
    pool = [p for p in decision.get("backup_pool") or [] if p["id"] not in selected]
    activities = dict(tc.get("activities") or {})
    for entry in pool:
        source = next((cx.places.get(entry.get("for")) for cx in ctxs if entry.get("for") in cx.places), None)
        if source and source.activity:
            activities.setdefault(entry["id"], source.activity)
    candidates, _ = build_places({"confirmed": pool, "trip_context": {**tc, "activities": activities}}, by_id, cfg)
    out = []
    for cx, result in zip(ctxs, results):
        excess = period_load(list(result.order), cx)
        if excess:
            out.append({"kind": "overload", "day": cx.day.index + 1, "optional": True,
                        "text": "Nhiều hoạt động tranh cùng khung giờ ưu tiên. Có thể chuyển bớt sang ngày khác hoặc chọn ít nơi hơn.",
                        "estimated_excess_min": round(excess, 1), "alternatives": []})
        for period in PERIOD_TEXT:
            gaps = [(max(a, cx.day.start), min(b, cx.day.end)) for a, b in period_windows(period, cx)]
            gaps = [gap for a, b in gaps for gap in _gaps(a, b, result.items)
                    if gap[1] - gap[0] >= cfg.time_suitability["recommendation_gap_min"]]
            if not gaps:
                continue
            alternatives = []
            for candidate in sorted(candidates, key=lambda p: p.id):
                if candidate.id not in cx.travel.index or not _suited(candidate, period, cx):
                    continue
                if any(not allowed(candidate.rec, hf, candidate.activity, candidate.kind) for hf in hard):
                    continue
                trial_cx = replace(cx, places={**cx.places, candidate.id: candidate})
                for position in range(len(result.order) + 1):
                    order = list(result.order)
                    order.insert(position, candidate.id)
                    trial = simulate(order, trial_cx)
                    item = next(i for i in trial.items if i.kind == "visit" and i.place_id == candidate.id)
                    if not any(a <= item.start and item.end <= b for a, b in gaps):
                        continue
                    trial_results = [trial if old is result else old for old in results]
                    trial_ctxs = [trial_cx if old is cx else old for old in ctxs]
                    anchors = {c["id"] for c in decision["confirmed"] if c.get("role") == "anchor"}
                    if validate(trial_ctxs, trial_results, hard, anchors, tc["context"].get("budget_vnd"),
                                (tc.get("pace") or {}).get("max_leg_min")):
                        continue
                    alternatives.append({"id": candidate.id, "name": candidate.name, "activity": candidate.activity,
                                         "trial_visit": [fmt(item.start), fmt(item.end)], "requires_relayout": True,
                                         "cost_unknown": candidate.cost_vnd is None})
                    break
                if len(alternatives) >= cfg.time_suitability["recommendations_per_gap"]:
                    break
            out.append({"kind": "gap", "day": cx.day.index + 1, "period": period, "optional": True,
                        "windows": [[fmt(a), fmt(b)] for a, b in gaps], "alternatives": alternatives,
                        "text": f"Còn khoảng trống {PERIOD_TEXT[period]}; bạn có thể nghỉ hoặc chọn thêm hoạt động."})
    return out
