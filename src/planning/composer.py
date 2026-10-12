"""Bounded deterministic subset proposals; the scheduler and validator remain the feasibility oracle."""

import math
from collections import Counter
from dataclasses import asdict
from statistics import median

from corpus.serving import feature
from requirements import applicable

from .backup import backups
from .build import itinerary, schedule_trip, travel_load
from .days import crowd_risk, repeats
from .objectives import metrics
from .robustness import robustness
from .schedule import pin_window
from .timefit import describe as time_description
from .traits import exposure, kind_group, preference

PRESETS = ("low_cost", "diverse", "least_travel")
LABELS = {"low_cost": "Tiết kiệm", "diverse": "Trải nghiệm tốt nhất", "least_travel": "Gọn tuyến"}
DEFINITIONS = {
    "low_cost": "Giảm chi phí ước tính, giữ ít nhất 70% giá trị của danh sách bạn chọn.",
    "diverse": "Đáp ứng mong muốn, đa dạng, ở mỗi nơi đủ lâu và có độ vững ít nhất Khả thi.",
    "least_travel": "Ưu tiên đi được nhiều nơi; cùng số nơi thì dành nhiều thời gian ở nơi hơn trên đường.",
}
TRADEOFFS = {
    "low_cost": "Có thể bỏ nơi đắt hoặc chấp nhận đi xa hơn để giữ phần có giá trị với bạn.",
    "diverse": "Có thể ít nơi hơn, tốn tiền hoặc đi lại nhiều hơn để mỗi trải nghiệm có đủ thời gian.",
    "least_travel": "Có thể ít đa dạng hơn và rút thời gian ghé xuống mức ngắn của ước lượng.",
}


def selection_utilities(trip) -> dict[str, float]:
    selected = {c["id"]: c for c in trip.decision.get("confirmed", [])}
    soft = trip.decision.get("trip_context", {}).get("soft_weights") or []
    result = {}
    for pid, c in selected.items():
        raw = c.get("utility")
        if isinstance(raw, (int, float)) and math.isfinite(raw):
            result[pid] = max(0.001, float(raw))
        elif pid in trip.by_place:
            result[pid] = 1.0 + preference(trip.by_place[pid], soft)
        else:
            result[pid] = 1.0
    return result


def utilities(trip) -> dict[str, float]:
    result = selection_utilities(trip)
    soft = trip.decision.get("trip_context", {}).get("soft_weights") or []
    for pid, p in trip.by_place.items():
        if pid not in result:
            result[pid] = 1.0 + preference(p, soft)
    return result


def must_places(trip) -> set[str]:
    tc = trip.decision["trip_context"]
    return {c["id"] for c in trip.decision["confirmed"] if c.get("role") in {"anchor", "locked"}} | \
        {a["place_id"] for a in tc.get("anchors") or [] if a.get("priority") == "must"}


def _wishes(trip, sched) -> dict:
    wishes = [w for w in trip.decision["trip_context"].get("soft_weights") or [] if w.get("weight", 0) > 0]
    seen = set()
    wishes = [w for w in wishes if not ((w["feature"], w["value"]) in seen
              or seen.add((w["feature"], w["value"])))]
    met, unmet, unknown = [], [], []
    visit_at = {it.place_id: (cx, result, it) for cx, result in zip(sched.ctxs, sched.results)
                for it in result.items if it.kind == "visit"}
    for wish in wishes:
        fid, matched, evidence, timing_unknown = wish["feature"], False, False, False
        for pid, p in trip.by_place.items():
            fact = feature(p.rec, fid)
            if not applicable(p.rec, wish, p.activity, p.kind) or not fact or fact.get("status") != "VERIFIED":
                continue
            evidence = True
            if fact.get("value") != wish["value"] or pid not in visit_at:
                continue
            cx, result, item = visit_at[pid]
            # The original wish, not the post-_unpin Place copy, defines whether timing is part of this wish.
            if fid not in p.pins:
                matched = True
                continue
            pin = cx.cfg.pins.get(fid)
            if pin is None:
                timing_unknown = True
                continue
            if pin["anchor"] == "clock":
                lo, hi = pin["from"], pin["to"]
            elif cx.sun is None:
                timing_unknown = True
                continue
            else:
                base = cx.sun[0] if pin["anchor"] == "sunrise" else cx.sun[1]
                lo, hi = base + pin["from_min"], base + pin["to_min"]
            if pid not in result.unpinned and lo <= item.start <= hi:
                matched = True
        entry = {"feature": fid, "value": wish["value"]}
        (met if matched else unknown if timing_unknown or not evidence else unmet).append(entry)
    return {"met": met, "unmet": unmet, "unknown": unknown, "total": len(wishes),
            "coverage": len(met) / len(wishes) if wishes else None}


def profile_metrics(trip, sched) -> dict:
    """Measurements on the actual timeline, also used after the user's edits."""
    m = metrics(sched.ctxs, sched.results)
    visits = [(cx, it) for cx, r in zip(sched.ctxs, sched.results) for it in r.items if it.kind == "visit"]
    kept = {it.place_id for _, it in visits}
    values = utilities(trip)
    sel_values = selection_utilities(trip)
    sel_total = sum(sel_values.values())
    retained_sel = sum(sel_values[pid] for pid in kept if pid in sel_values)
    value_share = retained_sel / sel_total if sel_total > 0 else 1.0
    visit_min = sum(it.end - it.start for _, it in visits)
    loss = sum(max(0, cx.places[it.place_id].visit[cx.cfg.visit_key[cx.pace]] - (it.end - it.start))
               for cx, it in visits)
    counts = Counter()
    for pid in kept:
        p = trip.by_place.get(pid) or next((cx.places[pid] for cx in sched.ctxs if pid in cx.places), None)
        if p and kind_group(p):
            counts[kind_group(p)] += 1
    visited = set((trip.decision.get("trip_context", {}).get("novelty") or {}).get("visited") or [])
    novelty = (trip.decision.get("trip_context", {}).get("novelty") or {}).get("level")
    known_prices = {}
    for p in trip.by_place.values():
        if p.cost_vnd is not None:
            known_prices.setdefault(kind_group(p), []).append(p.cost_vnd)
    imputed, unestimated = 0, 0
    for pid in kept:
        p = trip.by_place.get(pid) or next((cx.places[pid] for cx in sched.ctxs if pid in cx.places), None)
        if p and p.cost_vnd is None:
            prices = known_prices.get(kind_group(p))
            if prices:
                imputed += median(prices)
            else:
                unestimated += 1
    mobility = trip.decision.get("trip_context", {}).get("context", {}).get("mobility")
    rate = trip.cfg.composer.get("transport_vnd_per_min", {}).get(mobility)
    transport = round(m["travel_min"] * rate) if isinstance(rate, (int, float)) and rate >= 0 else None
    wish = _wishes(trip, sched)
    duration = visit_min + m["travel_min"]
    m.update({"places": len(kept), "visit_min": visit_min, "duration_loss_min": loss,
              "visit_density": visit_min / duration if duration else 0,
              "categories_covered": len(counts), "diversity": len(counts) + sum(math.sqrt(n) for n in counts.values()),
              "novelty_share": len(kept - visited) / len(kept) if kept and novelty else None,
              "wish_coverage": wish["coverage"], "wishes": wish,
              "value_share": value_share,
              "utility": sum(values.get(pid, 1.0) for pid in kept),
              "utility_source": "decision_score" if kept <= set(sel_values) and all(c.get("utility") is not None for c in
                                                        trip.decision.get("confirmed", [])) else "selection_and_preferences",
              "transport_cost_vnd": transport,
              "estimated_cost_vnd": round(m["cost_vnd"] + imputed + (transport or 0)),
              "cost_unestimated": unestimated, "cost_basis": "partial" if m["cost_unknown"] or transport is None else "estimated",
              "meals_included": False})
    return m


def profile_violations(trip, sched, preset) -> list[dict]:
    out = [asdict(v) for v in sched.violations]
    cfg = trip.cfg.composer
    cap = trip.cfg.per_day[trip.pace] if preset == "diverse" else cfg["per_day_max"][trip.pace]
    for cx, result in zip(sched.ctxs, sched.results):
        count = sum(cx.places[pid].kind == "experience" for pid in result.order)
        load = sum(max(0, it.end - it.start) for it in result.items)
        if count > cap:
            out.append({"kind": "profile_count", "day": cx.day.index, "place_id": None, "minutes": 0,
                        "physical": False, "detail": f"{count} experience places exceed the pace limit {cap}"})
        available = cx.day.end - cx.day.start
        if load > cfg["rho"] * available:
            out.append({"kind": "profile_load", "day": cx.day.index, "place_id": None,
                        "minutes": math.ceil(load - cfg["rho"] * available), "physical": False,
                        "detail": "the proposal has insufficient spare time"})
        if preset == "diverse":
            long_legs = sum(it.kind == "travel" and it.end - it.start > trip.cfg.long_leg_min for it in result.items)
            if long_legs > 1:
                out.append({"kind": "profile_travel", "day": cx.day.index, "place_id": None, "minutes": 0,
                            "physical": False, "detail": "more than one long leg in the experience day"})
    if preset == "diverse" and robustness(sched.ctxs, sched.results, trip.travel.source)["level"] == "fragile":
        out.append({"kind": "profile_robustness", "day": None, "place_id": None, "minutes": 0,
                    "physical": False, "detail": "the experience proposal is fragile"})
    return out


def render_profile(trip, sched, preset, *, baseline=None) -> dict:
    m = profile_metrics(trip, sched)
    kept = sorted({pid for r in sched.results for pid in r.order})
    violations = profile_violations(trip, sched, preset)
    if preset == "low_cost" and m["value_share"] + 1e-9 < trip.cfg.composer["alpha"]:
        violations.append({"kind": "profile_value", "day": None, "place_id": None, "minutes": 0,
                           "physical": False, "detail": "insufficient retained selection value"})
    values = utilities(trip)
    unplaced = {p.id: p.reason for p in trip.unplaced}
    dropped = [{"place_id": c["id"], "name": c.get("name") or c["id"],
                "reason": "unplaced" if c["id"] in unplaced else "pricey" if preset == "low_cost" else
                "far" if preset == "least_travel" else "crowded",
                "text": (f"Chưa thể xếp nơi này: {unplaced[c['id']]} (thiếu dữ liệu lịch trình)." if c["id"] in unplaced
                         else "Chừa thời gian cho các nơi hợp ưu tiên của phương án này."),
                "saved_min": trip.by_place[c["id"]].visit[trip.cfg.visit_key[trip.pace]] if c["id"] in trip.by_place else None,
                "saved_vnd": trip.by_place[c["id"]].cost_vnd if c["id"] in trip.by_place else None,
                "regret": values.get(c["id"]), "source": "data" if c["id"] in unplaced else "plan"}
               for c in trip.decision["confirmed"] if c["id"] not in kept]
    tc = trip.decision["trip_context"]
    context = tc["context"]
    budget, pace = context.get("budget_vnd"), (tc.get("pace") or {}).get("level")
    why = (f"Bạn đặt ngân sách {budget:,} VND/người/ngày." if preset == "low_cost" and budget else
           "Bạn chọn nhịp thong thả." if preset == "diverse" and pace == "slow" else
           "Bạn muốn đi nhiều nơi." if preset == "least_travel" and pace == "packed" else
           "Phương án này giúp bạn so sánh ưu tiên; chưa suy đoán điều bạn thích.")
    base = baseline or {}
    baseline_complete = not trip.unplaced
    delta = {"places": len(kept) - len(trip.decision["confirmed"]),
             "travel_min": m["travel_min"] - base["travel_min"] if baseline_complete and "travel_min" in base else None,
             "cost_vnd": m["cost_vnd"] - base["cost_vnd"] if baseline_complete and "cost_vnd" in base else None}
    days = [cx.day for cx in sched.ctxs]
    definition = DEFINITIONS[preset]
    if preset == "low_cost":
        definition = f"Giảm chi phí ước tính, giữ ít nhất {trip.cfg.composer['alpha']:.0%} giá trị danh sách bạn chọn."
    return {"id": f"profile-{preset}", "objective": preset, "preset": preset, "label": LABELS[preset],
            "definition": definition, "why": why, "tradeoff": TRADEOFFS[preset],
            "status": "unavailable" if violations else "available", "confirmable": not violations,
            "unavailable_reason": "; ".join(v["detail"] for v in violations) if violations else None,
            "kept": kept, "dropped_by_plan": dropped, "delta_vs_selection": delta,
            "metrics": m, "score": [m["estimated_cost_vnd"], m["travel_min"]] if preset == "low_cost" else
            [-m["wish_coverage"] if m["wish_coverage"] is not None else 0, -m["diversity"]] if preset == "diverse" else
            [-m["places"], -m["visit_density"]], "violations": violations,
            "itinerary": itinerary(days, sched.results), "travel_load": travel_load(days, sched.results),
            "time_suitability": time_description(sched.ctxs, sched.results), "recommendations": [],
            "robustness": robustness(sched.ctxs, sched.results, trip.travel.source),
            "backups": backups(sched.ctxs, sched.results, trip.decision, trip.by_id), "warnings": sched.warnings,
            "lodging": {"id": None, "name": None, "price_vnd": None},
            "_results": sched.results, "_ctxs": sched.ctxs,
            "_home": trip.days[0].start_node if trip.days else None}


def _quality(trip, kept, preset, values) -> tuple:
    selected = [trip.by_place[i] for i in sorted(kept)]
    prices = [p.cost_vnd for p in selected if p.cost_vnd is not None]
    unknown = sum(p.cost_vnd is None for p in selected)
    if preset == "low_cost":
        # Unknown prices cannot win by masquerading as zero-cost places.
        return (-unknown, -sum(prices), sum(values[i] for i in kept))
    if preset == "least_travel":
        return (len(kept), sum(values[i] for i in kept))
    soft = trip.decision["trip_context"].get("soft_weights") or []
    wishes = {(w["feature"], w["value"]) for w in soft if w.get("weight", 0) > 0 and any(
        (feature(p.rec, w["feature"]) or {}).get("value") == w["value"] and
        (feature(p.rec, w["feature"]) or {}).get("status") == "VERIFIED" and applicable(p.rec, w, p.activity, p.kind)
        for p in selected)}
    kinds = Counter(kind_group(p) for p in selected if kind_group(p))
    visited = set((trip.decision["trip_context"].get("novelty") or {}).get("visited") or [])
    novelty = (trip.decision["trip_context"].get("novelty") or {}).get("level")
    bonus = 0 if novelty in (None, "familiar", "known") else len(kept - visited)
    risk = sum(exposure(p) == "exposed" for p in selected) + sum(p.hours_status in {"UNCERTAIN", "OUTDATED"}
                                                                              for p in selected)
    return (len(wishes), len(kinds) + sum(math.sqrt(n) for n in kinds.values()), bonus,
            -sum(n - 1 for n in Counter(p.dup_group for p in selected if p.dup_group is not None).values()),
            -risk, sum(values[i] for i in kept))


def _detour(trip, pid, kept) -> float:
    others = sorted(set(kept) - {pid})
    if not others:
        return 0
    return min(trip.travel.leg(pid, q)[0] + trip.travel.leg(q, pid)[0] for q in others)


def _select(trip, preset, protected, banned):
    cfg, values = trip.cfg.composer, utilities(trip)
    kept = set(trip.by_place) - banned | (protected & set(trip.by_place))
    cap = trip.cfg.per_day[trip.pace] if preset == "diverse" else cfg["per_day_max"][trip.pace]

    def worst(candidates):
        if preset == "least_travel":
            return max(candidates, key=lambda pid: (_detour(trip, pid, kept) +
                       trip.by_place[pid].visit[trip.cfg.visit_key[trip.pace]], -values[pid], pid))
        return max(candidates, key=lambda pid: (_quality(trip, kept - {pid}, preset, values), pid))

    # Batch first: avoid repeatedly routing dense selections already above the weekly count limit.
    for start in range(0, len(trip.days), trip.cfg.chunk_days):
        week = start // trip.cfg.chunk_days
        days = min(trip.cfg.chunk_days, len(trip.days) - start)
        members = {pid for pid in kept if len(trip.days) <= trip.cfg.chunk_days or trip.chunk_assignments.get(pid) == week}
        while sum(trip.by_place[pid].kind == "experience" for pid in members) > cap * days:
            optional = {pid for pid in members - protected if trip.by_place[pid].kind == "experience"}
            if not optional:
                break
            pid = worst(optional)
            kept.remove(pid)
            members.remove(pid)
    attempts = 0

    def layout(ids):
        nonlocal attempts
        attempts += 1
        return schedule_trip(trip, trip.cfg.objective_weights[preset], kept=ids, allow_shrink=preset != "diverse")

    sched = layout(kept)
    while attempts < cfg["search_limit"]:
        violations = profile_violations(trip, sched, preset)
        if not violations:
            break
        affected_days = {v["day"] for v in violations if v.get("day") is not None}
        candidates = {pid for k in affected_days for pid in sched.per_day[k]} if affected_days else set(kept)
        candidates &= kept - protected
        if not candidates:
            break
        pid = worst(candidates)
        kept.remove(pid)
        sched = layout(kept)

    if not profile_violations(trip, sched, preset) and preset == "low_cost":
        # Compare actual scheduled totals, including directed travel when a rate is configured. A missing rate is
        # unknown rather than a free ride; venue imputation comes only from the same kind of known prices.
        floor = cfg["alpha"] * sum(values.values())
        while attempts < cfg["search_limit"]:
            current_cost = profile_metrics(trip, sched)["estimated_cost_vnd"]
            best = None
            for pid in sorted(kept - protected):
                if sum(values[i] for i in kept - {pid}) + 1e-9 < floor or attempts >= cfg["search_limit"]:
                    continue
                trial = layout(kept - {pid})
                if profile_violations(trip, trial, preset):
                    continue
                trial_cost = profile_metrics(trip, trial)["estimated_cost_vnd"]
                savings = current_cost - trial_cost
                if savings <= 0:
                    continue
                rank = (savings / max(values[pid], 0.001), savings, -values[pid], pid)
                if best is None or rank > best[0]:
                    best = (rank, pid, trial)
            if best is None:
                break
            _, pid, sched = best
            kept.remove(pid)

    # Refill from the selection, checking every addition. Limits apply to complete scheduler trials.
    optional = set(trip.by_place) - kept - banned
    while optional and attempts < cfg["search_limit"] and not profile_violations(trip, sched, preset):
        if preset == "least_travel":
            pid = min(optional, key=lambda i: (_detour(trip, i, kept) + trip.by_place[i].visit["short"], -values[i], i))
        else:
            pid = max(optional, key=lambda i: (_quality(trip, kept | {i}, preset, values), i))
        optional.remove(pid)
        if preset == "low_cost" and sum(values[i] for i in kept) >= cfg["alpha"] * sum(values.values()):
            break
        trial = layout(kept | {pid})
        if not profile_violations(trip, trial, preset):
            kept.add(pid)
            sched = trial

    # A bounded one-for-one refinement can replace a poor fit while keeping the validated subset size stable.
    # Scheduler trials, including rejected candidates, all consume the configured global budget.
    def quality(current):
        m = profile_metrics(trip, current)
        if preset == "low_cost":
            return (-m["estimated_cost_vnd"], m["utility"])
        if preset == "least_travel":
            return (m["places"], m["visit_density"], m["utility"])
        return (m["wish_coverage"] or 0, m["diversity"], m["novelty_share"] or 0,
                -m["duration_loss_min"], -m["repeats"], m["utility"])

    while attempts < cfg["search_limit"] and not profile_violations(trip, sched, preset):
        current_quality = quality(sched)
        best = None
        for drop in sorted(kept - protected):
            for add in sorted(set(trip.by_place) - kept - banned):
                if attempts >= cfg["search_limit"]:
                    break
                trial = layout((kept - {drop}) | {add})
                if profile_violations(trip, trial, preset):
                    continue
                candidate_quality = quality(trial)
                rank = (candidate_quality, add, drop)
                if candidate_quality > current_quality and (best is None or rank > best[0]):
                    best = (rank, drop, add, trial)
        if best is None:
            break
        _, drop, add, sched = best
        kept.remove(drop)
        kept.add(add)
    return sched


def compose(trip, *, force: bool = False, must=(), banned=()) -> dict | None:
    """Return three explained priorities for a tight selection, else retain the legacy objectives."""
    original = schedule_trip(trip, trip.cfg.objective_weights["least_travel"])
    original_metrics = profile_metrics(trip, original)
    rob = robustness(original.ctxs, original.results, trip.travel.source)
    feasibility = trip.decision.get("feasibility") or {}
    totals = feasibility.get("totals") or {}
    available = totals.get("available")
    needed = totals.get("needed")
    actual_available = sum(cx.day.end - cx.day.start for cx in original.ctxs)
    actual_load = sum(max(0, i.end - i.start) for r in original.results for i in r.items)
    ratio = needed / available if available and needed is not None else actual_load / actual_available if actual_available else 0
    binding = [c["check"] for c in feasibility.get("conflicts") or [] if c.get("check") in
               {"time", "per_day", "far_areas", "time_windows", "budget"}]
    missing = [p.id for p in trip.unplaced]
    if not force and not binding and ratio < trip.cfg.composer["tight_ratio"] and not original.violations \
            and rob["level"] != "fragile":
        return None
    # Non-overload missing-place failures remain the legacy fail-closed result.
    if not force and not binding and missing and all(v.kind == "anchor" for v in original.violations):
        return None
    protected = must_places(trip) | set(must)
    banned = set(banned) - protected
    keep_all_violations = [asdict(v) for v in original.violations]
    keep_all_violations.extend({"kind": "unplaced", "day": None, "place_id": pid, "minutes": 0,
                                "physical": False, "detail": f"confirmed place cannot be planned: {reason}"}
                               for pid, reason in ((p.id, p.reason) for p in trip.unplaced))
    # A severe-day hazard is a physical scheduling boundary, not an overload signal that
    # subset selection may silently solve. Keep the legacy fail-closed result so the
    # caller reports the hazard and the affected places back to Decision.
    if any(v.kind == "hazard" for v in original.violations):
        return None
    days = [cx.day for cx in original.ctxs]
    keep_all = {
        "id": "keep_all",
        "label": "Giữ tất cả",
        "objective": "keep_all",
        "preset": None,
        "definition": "Giữ lại toàn bộ các nơi bạn đã chọn trong danh sách ban đầu.",
        "why": "Lịch gốc đối chiếu toàn bộ các nơi đã chọn.",
        "tradeoff": "Có thể vi phạm thời gian, quá tải hoặc thiếu thời gian đệm.",
        "status": "available" if not keep_all_violations else "unavailable",
        "confirmable": not keep_all_violations,
        "unavailable_reason": "; ".join(v["detail"] for v in keep_all_violations) if keep_all_violations else None,
        "kept": sorted(c["id"] for c in trip.decision.get("confirmed", [])),
        "dropped_by_plan": [],
        "violations": keep_all_violations,
        "unplaced": [{"place_id": p.id, "reason": p.reason} for p in trip.unplaced],
        "metrics": original_metrics,
        "score": [-original_metrics.get("places", len(trip.decision.get("confirmed", []))), original_metrics.get("travel_min", 0)],
        "robustness": rob,
        "itinerary": itinerary(days, original.results),
        "travel_load": travel_load(days, original.results),
        "time_suitability": time_description(original.ctxs, original.results),
        "recommendations": [],
        "warnings": original.warnings,
        "backups": backups(original.ctxs, original.results, trip.decision, trip.by_id),
        "lodging": {"id": None, "name": None, "price_vnd": None},
        "_results": original.results,
        "_ctxs": original.ctxs,
        "_home": trip.days[0].start_node if trip.days else None,
    }
    variants = [render_profile(trip, _select(trip, preset, protected, banned), preset, baseline=original_metrics)
                for preset in PRESETS]
    for variant in variants:
        missing_must = protected - set(variant["kept"])
        if missing_must:
            variant["violations"] += [{"kind": "anchor", "day": None, "place_id": pid, "minutes": 0,
                                       "physical": False, "detail": "a required place cannot be scheduled"}
                                      for pid in sorted(missing_must)]
            variant.update(status="unavailable", confirmable=False,
                           unavailable_reason="Không xếp được nơi bắt buộc: " + ", ".join(sorted(missing_must)))
        variant["same_as"] = [v["id"] for v in variants if v is not variant and
                              v["kept"] == variant["kept"] and v["itinerary"] == variant["itinerary"]]
    level = "overloaded" if ratio > 1 or original.violations else "tight"
    overload = {"level": level, "estimated": True, "needed": needed if needed is not None else actual_load,
                "available": available if available is not None else actual_available,
                "binding": sorted(set(binding) | {v.kind for v in original.violations}),
                "selection_places": len(trip.decision["confirmed"]), "keep_all_valid": keep_all["confirmable"],
                "text": "Lịch giữ tất cả chưa hợp lệ; xem ba hướng dưới đây." if original.violations else
                        "Danh sách này khá chặt; xem ba hướng để chọn cái giá bạn chấp nhận."}
    order = {"solid": 0, "feasible": 1, "fragile": 2}
    tc = trip.decision["trip_context"]
    pace = (tc.get("pace") or {}).get("level")
    preferred = "low_cost" if tc["context"].get("budget_vnd") else "diverse" if pace == "slow" or \
        (tc.get("novelty") or {}).get("level") in {"new", "explore", "try_new"} or len(tc.get("soft_weights") or []) >= 3 else \
        "least_travel" if pace == "packed" or (tc["context"].get("days") or 3) <= 2 or \
        (tc.get("pace") or {}).get("max_leg_min") is not None else None
    variants.sort(key=lambda v: (v["status"] != "available", v["preset"] != preferred if preferred else False,
                                 order[v["robustness"]["level"]], PRESETS.index(v["preset"])))
    valid = [v for v in variants if v["status"] == "available"]
    comparison = [{"variant": v["id"], "objective": v["preset"], "label": v["label"], **v["metrics"],
                   "delta_vs_selection": v["delta_vs_selection"], "robustness": v["robustness"]["level"]} for v in variants]
    return {"ok": bool(valid), "variants": variants, "keep_all": keep_all, "overload": overload,
            "comparison": comparison, "warnings": list(trip.warnings) + [{"code": "selection_overload", "text": overload["text"]}],
            "back_to_decision": None if valid else {"reason": "required_places_do_not_fit", "places": sorted(protected)},
            "violations": [], "chosen": None}
