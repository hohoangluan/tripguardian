"""⑨ Combination feasibility (docs/P3_PLACE_DECISION.md §13): the chosen places as one group, rough and
deterministic. Every conflict carries fixes whose `action` is a POST /act payload (None: shown, not clickable)."""

from collections import defaultdict
from itertools import combinations

from corpus.serving import feature

from .cards import feature_label, value_label
from .geo import fmt, km, minutes, point, to_min
from .model import Cand, day_visit


def _visit(c: Cand, cfg) -> int:
    vm = day_visit(c.rec, cfg)
    return vm["typical"] if vm else 60


def _cost_vnd(c: Cand) -> int:
    op = c.rec["operation"]
    p = op.get("price_per_person")
    lo = (p["value"].get("min_vnd") or 0) if p else 0
    hi = (p["value"].get("max_vnd") or lo) if p else 0
    fee = (op.get("entry_fee") or {}).get("typical_vnd") or 0
    return int((lo + hi) / 2 + fee)


def _areas(chosen: list[Cand]) -> dict[str, tuple[tuple[float, float], list[Cand]]]:
    acc = defaultdict(list)
    for c in chosen:
        if p := point(c.rec):
            acc[c.rec["identity"].get("area") or c.id].append((c, p))
    return {a: ((sum(p[0] for _, p in xs) / len(xs), sum(p[1] for _, p in xs) / len(xs)), [c for c, _ in xs])
            for a, xs in acc.items()}


def _top_experience(rec: dict) -> str | None:
    exp = rec.get("experience") or {}
    return max(exp, key=lambda f: (exp[f]["n"], f)) if exp else None


def _timed(c: Cand, wanted_timed: set[str], is_anchor: bool, cfg) -> set[str]:
    """Buckets that hold timed_share of the time-of-day mentions of a timed feature the user wants (or the anchor's
    top experience)."""
    top, out = _top_experience(c.rec), set()
    for fid in cfg.timed_features:
        f = feature(c.rec, fid)
        if not f or f["value"] != "present" or not (fid in wanted_timed or (is_anchor and fid == top)):
            continue
        counts = defaultdict(float)
        for k, d in f["by_context"].items():
            if k.startswith("time_of_day="):
                counts[k.split("=", 1)[1]] += sum(d.values())
        total, acc = sum(counts.values()), 0.0
        for b, n in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
            out.add(b)
            acc += n
            if acc / total >= cfg.timed_share:
                break
    return out


def _windows_on(rec: dict, days) -> list[tuple[int, int]]:
    h = rec["operation"].get("hours")
    if not h or not h["value"]:
        return []
    keys = [d.weekday for d in days if d.weekday] or list(h["value"])
    return sorted({(to_min(a), to_min(b)) for k in keys for a, b in h["value"].get(k, [])})


def _night_only(rec: dict, days, cfg) -> bool:
    ws = _windows_on(rec, days)
    return bool(ws) and all(a >= to_min(cfg.night_open) for a, _ in ws)


def need_buckets(c: Cand, wanted_timed: set[str], is_anchor: bool, days, cfg) -> frozenset[str] | None:
    need = _timed(c, wanted_timed, is_anchor, cfg)
    if _night_only(c.rec, days, cfg):
        need |= {"evening", "night"}
    return frozenset(need) if need and need <= set(cfg.narrow_buckets) else None


def supply(days, arrive: int | None, cfg) -> dict[str, int]:
    """One slot per narrow bucket per day, except before the arrival on day 1 and after leaving on the last day."""
    out = {b: 0 for b in cfg.narrow_buckets}
    for d in days:
        for b in cfg.narrow_buckets:
            s, e = map(to_min, cfg.buckets[b])
            if d.index == 0 and e <= (arrive if arrive is not None else d.start):
                continue
            if d.index == len(days) - 1 and s >= d.end:
                continue
            out[b] += 1
    return out


def _drop_fix(c: Cand, effect: str) -> dict:
    return {"label": f"Bỏ {c.name}", "effect": effect, "action": {"type": "drop", "place_id": c.id}}


def _window_conflict(chosen, needs, days, arrive, removable, cfg) -> list[dict]:
    sup, worst = supply(days, arrive, cfg), None
    for r in range(1, len(cfg.narrow_buckets) + 1):
        for bs in combinations(cfg.narrow_buckets, r):
            who = [c for c in chosen if c.id in needs and needs[c.id] <= set(bs)]
            cap = sum(sup[b] for b in bs)
            if len(who) > cap and (worst is None or len(who) - cap > worst[0]):
                worst = (len(who) - cap, bs, who, cap)
    if worst is None:
        return []
    _, bs, who, cap = worst
    ids = {c.id for c in who}
    label = " hoặc ".join(cfg.labels["time"][b] for b in bs)
    fixes = [_drop_fix(c, f"Còn {len(who) - 1} nơi cho {cap} buổi") for c in removable if c.id in ids][:1]
    fixes.append({"label": "Thêm 1 ngày cho chuyến", "effect": "Sửa số ngày ở bước Hiểu chuyến đi", "action": None})
    return [{"id": "time_windows:" + "+".join(bs), "check": "time_windows", "physical": True,
             "title": f"{len(who)} nơi cần {label}, chuyến chỉ có {cap} buổi như vậy",
             "rule": "Săn mây, hoàng hôn, nhạc sống hay nơi chỉ mở buổi tối chỉ đi được đúng buổi đó.",
             "places": sorted(ids), "fixes": fixes}]


def _window_warnings(chosen, wanted_timed, anchors, days, cfg) -> list[str]:
    out = []
    for c in chosen:
        timed = _timed(c, wanted_timed, c.id in anchors, cfg)
        ws = _windows_on(c.rec, days)
        if not timed or not ws:
            continue
        spans = [tuple(map(to_min, cfg.buckets[b])) for b in timed]
        if not any(a < e and s < b for a, b in ws for s, e in spans):
            hours = "; ".join(f"{fmt(a)}–{fmt(b)}" for a, b in ws[:2])
            label = " hoặc ".join(cfg.labels["time"][b] for b in sorted(timed))
            out.append(f"{c.name}: giờ mở cửa ({hours}) không trùng {label}")
    return out


def room(chosen: list[Cand], days, needed: int, pace: str, cfg) -> dict:
    """How much of the trip's usable time the picks fill, as an optional hint (never a requirement).
    usable = each day's window (the arrival day from checkin_at, the last day until checkout_at) minus the meals that
    fall inside it; one more place costs its visit + buffer + a short leg, but never less than a full day at this
    pace spreads over per_day places, so free time is left free. free = usable minus that paced use; filled: the picks
    use fill_share of the usable time."""
    meals = [to_min(t) for t in cfg.meal_at]
    usable = sum(max(0, d.end - d.start - cfg.meal_min * sum(1 for m in meals if d.start <= m < d.end)) for d in days)
    exp = [c for c in chosen if c.role == "experience"]
    visit = sum(_visit(c, cfg) for c in exp) / len(exp) if exp else cfg.day_visit["typical_max"] / 2
    full_day = to_min(cfg.day_end) - to_min(cfg.day_start) - cfg.meal_min * len(meals)
    per_place = round(max(visit + cfg.buffer_min[pace] + cfg.intra_leg_min, full_day / cfg.per_day[pace]))
    used = max(needed, len(exp) * per_place)  # a picked place takes its paced share even when its visit is short
    free = max(0, usable - used)
    more = free // per_place
    return {"usable": usable, "free": free, "more": more, "filled": used >= usable * cfg.fill_share or more == 0}


def evaluate(chosen: list[Cand], si, days, known_days: bool, anchors: set[str], locked: set[str], ctrs,
             wanted_timed: set[str], cfg) -> dict:
    pace = si.pace.level or "normal"
    mob = si.context.mobility
    center = ctrs[0][1]
    conflicts, warnings = [], []
    removable = sorted((c for c in chosen if c.id not in locked and c.id not in anchors), key=lambda c: (c.score, c.id))

    areas = _areas(chosen)
    area_min = {a: minutes(km(center, cen), mob, cfg) for a, (cen, _) in areas.items()}
    visit = sum(_visit(c, cfg) for c in chosen)
    buffer = cfg.buffer_min[pace] * len(chosen)
    travel = cfg.intra_leg_min * len(chosen) + sum(2 * m for m in area_min.values())
    needed = visit + buffer + travel
    available = sum(max(0, d.end - d.start) for d in days)
    if known_days and needed > available:
        conflicts.append({"id": "time", "check": "time", "physical": True,
                          "title": f"Cần khoảng {needed} phút, chuyến có {available} phút",
                          "rule": "Tổng thời gian tham quan, đi lại (ước tính) và nghỉ vượt thời gian của chuyến.",
                          "places": [], "fixes": [_drop_fix(c, f"Bớt khoảng {_visit(c, cfg) + cfg.buffer_min[pace] + cfg.intra_leg_min} phút")
                                                  for c in removable[:2]]})

    for c in chosen:
        if any(x["reason"] == "closed_all_trip_days" and x["result"] == "fail" for x in c.checks):
            fixes = [_drop_fix(c, "Giải phóng thời gian cho nơi khác")]
            if c.id in locked or c.id in anchors:
                fixes.insert(0, {"label": "Chuyển vào danh sách mong muốn",
                                 "effect": "Giữ để đi dịp khác, không xếp vào chuyến này",
                                 "action": {"type": "wishlist", "place_id": c.id}})
            conflicts.append({"id": f"hours:{c.id}", "check": "hours", "physical": True,
                              "title": f"{c.name} đóng cửa mọi ngày của chuyến", "rule": "Theo giờ mở cửa trên Google.",
                              "places": [c.id], "fixes": fixes})
        if "hours_unknown" in c.warnings:
            warnings.append(f"{c.name}: chưa có giờ mở cửa, kiểm tra trước khi đi")
        elif "hours_outdated" in c.warnings:
            warnings.append(f"{c.name}: giờ mở cửa có thể đã đổi, kiểm tra lại trước chuyến")
        if c.missing:
            warnings.append(f"{c.name}: chưa có trong dữ liệu, mọi thông tin chưa xác minh")

    if known_days:
        needs = {c.id: n for c in chosen if (n := need_buckets(c, wanted_timed, c.id in anchors, days, cfg))}
        arrive = to_min(si.context.checkin_at) if si.context.checkin_at else None
        conflicts += _window_conflict(chosen, needs, days, arrive, removable, cfg)
    warnings += _window_warnings(chosen, wanted_timed, anchors, days, cfg)

    far = {a: m for a, m in area_min.items() if km(center, areas[a][0]) > cfg.far_km}
    if known_days and len(far) > len(days):
        worst = max(far, key=lambda a: (far[a], a))
        conflicts.append({"id": "far_areas", "check": "far_areas", "physical": False,
                          "title": f"{len(far)} khu cách xa cho {len(days)} ngày",
                          "rule": f"Mỗi ngày nên đi nhiều nhất một khu cách điểm xuất phát hơn {cfg.far_km} km.",
                          "places": sorted(c.id for a in far for c in areas[a][1]),
                          "fixes": [_drop_fix(c, f"Bớt khoảng {2 * far[worst]} phút đi lại nếu bỏ hết khu này")
                                    for c in removable if c in areas[worst][1]][:2]})

    exp = [c for c in chosen if c.role == "experience"]
    cap = len(days) * cfg.per_day_max[pace]
    if known_days and len(exp) > cap:
        conflicts.append({"id": "per_day", "check": "per_day", "physical": False,
                          "title": f"{len(exp)} nơi trải nghiệm, nhịp {cfg.labels['pace'][pace]} hợp với tối đa {cap}",
                          "rule": "Số nơi mỗi ngày theo nhịp độ bạn chọn.", "places": [c.id for c in exp],
                          "fixes": [_drop_fix(c, "Bớt một nơi") for c in removable if c.role == "experience"][:2]})

    budget = si.context.budget_vnd
    priced = [(c, v) for c in chosen if (v := _cost_vnd(c))]
    if budget and priced and not known_days:
        warnings.append("Chưa biết số ngày nên chưa kiểm chi phí")
    elif budget and priced:
        per_day = sum(v for _, v in priced) / len(days)
        if per_day > budget * cfg.budget_slack:
            top = sorted(((c, v) for c, v in priced if c in removable), key=lambda x: (-x[1], x[0].id))
            conflicts.append({"id": "budget", "check": "budget", "physical": False,
                              "title": f"Chi phí ước tính khoảng {round(per_day / 1000)}k/người/ngày, ngân sách {budget // 1000}k",
                              "rule": "Tính từ khoảng giá trên Google và giá vé ước tính.",
                              "places": [c.id for c, _ in priced],
                              "fixes": [_drop_fix(c, f"Bớt khoảng {v // 1000}k/người") for c, v in top[:2]]})
    elif priced:
        warnings.append("Chưa biết ngân sách của bạn nên chưa kiểm chi phí")

    for c in chosen:
        for x in c.checks:
            if x["kind"] != "hard" or x["result"] == "pass":
                continue
            fl, vl = feature_label(x["feature"], cfg).lower(), value_label(x["value"], cfg)
            if x["result"] == "unknown":
                warnings.append(f"{c.name}: chưa xác minh được {fl}, tự kiểm tra trước chuyến")
                continue
            conflicts.append({"id": f"relax:{c.id}:{x['feature']}", "check": "relax", "physical": False,
                              "title": f"{c.name}: {fl} ({vl})" if x["op"] == "ne" else f"{c.name}: không phải {vl}",
                              "rule": f"Bạn đặt điều kiện {fl} khác {vl}." if x["op"] == "ne" else f"Bạn cần {fl} là {vl}.",
                              "places": [c.id],
                              "fixes": [{"label": "Vẫn giữ, bỏ điều kiện này cho riêng nơi này",
                                         "effect": "Chỉ áp cho nơi này trong chuyến này",
                                         "action": {"type": "relax", "place_id": c.id, "feature": x["feature"]}},
                                        _drop_fix(c, "Giữ đúng điều kiện của bạn")]})

    if known_days and needed > available * cfg.infeasible_ratio:
        status = "infeasible"
    elif conflicts:
        status = "partial"
    elif not known_days:
        status = "unknown"
    else:
        status = "feasible"
    return {"status": status, "known_days": known_days,
            "totals": {"places": len(chosen), "visit": visit, "buffer": buffer, "travel": travel, "needed": needed,
                       "available": available},
            "room": room(chosen, days, needed, pace, cfg) if known_days else None,
            "slack": available - needed if known_days else None, "conflicts": conflicts, "warnings": warnings}
