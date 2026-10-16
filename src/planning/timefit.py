"""Soft suitability of the entire visit interval, separate from opening hours and popularity."""

from dataclasses import dataclass

from corpus.serving import feature
from requirements import category_for

from .details import night_road, timing_delta
from .settings import fmt, to_min

REASON_TEXT = {"preferred_period": "Ưu tiên khung giờ bạn đã chọn", "sun_time_unknown": "Chưa có giờ bình minh / hoàng hôn để chấm",
               "night_activity": "Ưu tiên hoạt động buổi tối", "daylight_photography": "Ưu tiên ánh sáng ban ngày để chụp ảnh",
               "light_activity": "Ưu tiên hoạt động nhẹ buổi sáng hoặc chiều", "midday_break": "Ưu tiên nghỉ và uống nước giữa trưa",
               "morning_energy": "Ưu tiên điểm quan trọng hoặc hoạt động tốn sức vào buổi sáng",
               "best_time": "Người đã đi khuyên nên tới vào buổi này", "avoid_time": "Người đã đi khuyên tránh buổi này",
               "night_road": "Đi xe máy về sau hoàng hôn trên đường tối nguy hiểm",
               "light_snack": "Ăn nhẹ buổi chiều"}


@dataclass(frozen=True)
class TimeRule:
    windows: tuple[tuple[int, int], ...]
    weight: float
    reason: str
    source: str
    evidence: tuple = ()


def _merge(windows) -> tuple[tuple[int, int], ...]:
    merged = []
    for a, b in sorted(windows):
        if b <= a:
            continue
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return tuple(merged)


def period_windows(period: str, ctx) -> tuple[tuple[int, int], ...]:
    cfg = ctx.cfg.time_suitability
    if period in {"sunrise", "sunset"}:
        if ctx.sun is None:
            return ()
        base = ctx.sun[period == "sunset"]
        a, b = cfg["sun_offsets"][period]
        return ((max(0, base + a), min(1440, base + b)),)
    if period == "daytime" and ctx.sun is not None:
        return ((ctx.sun[0], ctx.sun[1]),)
    window = cfg["periods"].get(period)
    return ((to_min(window[0]), to_min(window[1])),) if window else ()


def _firm(place, fid: str, value: str = "present") -> bool:
    f = feature(place.rec, fid)
    return bool(f and f["status"] in {"VERIFIED", "OUTDATED"} and f["value"] == value
                and set(f["distribution"]) <= {value})


def windows_for(place, ctx) -> tuple[TimeRule, ...]:
    """User windows override estimates. A timed feature by itself does not prove what the user will do there."""
    cfg = ctx.cfg.time_suitability
    if not cfg.get("enabled", False):
        return ()
    group = category_for(place.rec)

    def can_do(activity):
        if activity in (None, place.activity):
            return True
        if place.activity_explicit:
            return False
        if activity == "walking":
            return group in {"nature", "garden_farm"}
        if activity == "photography":
            return ctx.purpose == "photo" and (group in {"nature", "garden_farm"} or _firm(place, "photo_spot"))
        return activity == "nightlife" and group == "bar"

    matches = [p for p in ctx.time_preferences if p.get("place_id") in (None, place.id) and can_do(p.get("activity"))]
    if matches:
        specificity = lambda p: 2 * bool(p.get("place_id")) + bool(p.get("activity"))
        best = max(map(specificity, matches))
        chosen = [p for p in matches if specificity(p) == best]
        windows = _merge(w for p in chosen for w in period_windows(p["period"], ctx))
        return (TimeRule(windows, max(p.get("weight", 1) for p in chosen),
                         "preferred_period" if windows else "sun_time_unknown", "user",
                         tuple(e for p in chosen for e in p.get("evidence") or ())),)
    activity = place.activity
    reason, periods = None, []
    if activity == "nightlife" or (group == "bar" and activity != "eating"):
        reason, periods = "night_activity", ["evening"]
    elif place.meal_kind == "light" and (not place.activity_explicit or place.activity in {"eating", "coffee"}):
        reason, periods = "light_snack", ["afternoon"]      # an activity the user chose (photography ...) keeps its own rule
    elif place.kind == "meal":
        return ()                         # meal_windows already schedule the selected eating activity
    elif activity == "photography" or (ctx.purpose == "photo" and
            (group in {"nature", "garden_farm"} or _firm(place, "setting", "outdoor"))):
        if _firm(place, "setting", "indoor"):
            return ()
        reason, periods = "daylight_photography", ["daytime"]
    elif activity == "walking" or group == "garden_farm":
        reason, periods = "light_activity", ["morning", "afternoon"]
    elif activity == "coffee":
        reason, periods = "midday_break", ["midday"]
    elif place.role == "anchor" or _firm(place, "hiking") or _firm(place, "adventure_activity"):
        reason, periods = "morning_energy", ["morning"]
    if not periods:
        return ()
    return (TimeRule(_merge(w for period in periods for w in period_windows(period, ctx)),
                     cfg["heuristic_weight"], reason, "heuristic"),)


def visit_score(place, start: int, end: int, ctx, *, _rules: tuple[TimeRule, ...] | None = None) -> tuple[float, dict]:
    """Penalty in comparable planning minutes. Neither this score nor its estimates can relax a constraint."""
    rules = windows_for(place, ctx) if _rules is None else _rules
    duration = max(1, end - start)
    penalty = 0.0
    reasons = []
    for rule in rules:
        overlap = sum(max(0, min(end, b) - max(start, a)) for a, b in rule.windows)
        deficit = 1 - overlap / duration if rule.windows else 0.0
        penalty += ctx.cfg.time_suitability["penalty_min"] * rule.weight * deficit
        reasons.append({"reason": rule.reason, "source": rule.source,
                        "text": REASON_TEXT[rule.reason],
                        "windows": [[fmt(a), fmt(b)] for a, b in rule.windows],
                        "fit": round(1 - deficit, 3) if rule.windows else None,
                        "evidence": list(rule.evidence)})
    from .traits import visit_minutes
    expected = visit_minutes(place, ctx.cfg, ctx.pace, ctx.prefs)
    shortened = max(0, expected - (end - start))
    if ctx.cfg.time_suitability.get("enabled", False):
        penalty += ctx.cfg.time_suitability.get("duration_loss_min", 0) * shortened
        delta = timing_delta(place, start, ctx.cfg, end=end)
        if delta:
            penalty += delta
            reasons.append({"reason": "best_time" if delta < 0 else "avoid_time", "source": "reviews",
                            "text": REASON_TEXT["best_time" if delta < 0 else "avoid_time"], "windows": [], "fit": None,
                            "evidence": []})
        if night_road(place, ctx.mobility, end, ctx.sun):
            penalty += ctx.cfg.time_suitability.get("night_road_penalty", 0.0)
            reasons.append({"reason": "night_road", "source": "reviews", "text": REASON_TEXT["night_road"], "windows": [],
                            "fit": None, "evidence": []})
    detail = {"place_id": place.id, "activity": place.activity, "visit": [fmt(start), fmt(end)],
              "penalty": round(penalty, 3), "shortened_min": shortened, "reasons": reasons,
              "source": rules[0].source if rules else None}
    return penalty, detail


def period_load(ids: list[str], ctx) -> float:
    """Estimated excess demand for shared windows. Used for splitting days, never as an admission check."""
    groups = {}
    for pid in ids:
        rules = windows_for(ctx.places[pid], ctx)
        for rule in rules:
            if not rule.windows:
                continue
            entry = groups.setdefault(rule.windows, [0, 0.0])
            from .traits import visit_minutes
            entry[0] += visit_minutes(ctx.places[pid], ctx.cfg, ctx.pace, ctx.prefs) + ctx.cfg.buffer_min[ctx.pace]
            entry[1] = max(entry[1], rule.weight)
    return sum(max(0, demand - sum(max(0, min(b, ctx.day.end) - max(a, ctx.day.start)) for a, b in windows)) * weight
               for windows, (demand, weight) in groups.items())


def split_competing(clusters: list[list[str]], ctxs: list) -> list[list[str]]:
    """Let a day split move neighbouring places apart when all days would overload their preferred windows."""
    return [part for cluster in clusters for part in
            ([[pid] for pid in cluster] if len(cluster) > 1 and all(period_load(cluster, cx) > 0 for cx in ctxs)
             else [cluster])]


def describe(ctxs: list, results: list) -> list[dict]:
    return [{"day": cx.day.index + 1, "penalty": round(r.time_penalty, 3), "estimated": True,
             "places": list(r.time_details), "overload_min": round(period_load(list(r.order), cx), 1)}
            for cx, r in zip(ctxs, results)]
