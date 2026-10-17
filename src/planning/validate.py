"""Final check (docs/ARCHITECTURE.md §11): the only place that decides whether a plan passes.

It re-derives every check from the finished timeline instead of trusting what simulate() noticed, so a bug in the
scheduler cannot also hide from the check. Fail-closed: a violation is reported, never repaired here.
"""

from dataclasses import replace

from requirements import allowed, hard_result

from .conditions import hazard
from .feature_ontology import ontology
from .model import DayResult, Violation
from .roles import takes_meal_slot
from .schedule import DayCtx, intervals_for, meal_floor, meals_needed, pin_window
from .cache import day_key, fingerprint, put, travel_key


def _is_physical(feature: str) -> bool:
    f = ontology().features.get(feature)
    return f is not None and f.group == "effort"


def _released(cx: DayCtx, r: DayResult) -> DayCtx:
    """The day as the scheduler laid it out: a place whose time-of-day pin it gave up (and said so) is not held to it.
    Without this, a plan shown as valid would fail the same check at confirm."""
    return release(cx, r.unpinned)


def release(cx: DayCtx, ids) -> DayCtx:
    """The day with the given places no longer held to their time of day."""
    if not ids:
        return cx
    return replace(cx, places={**cx.places, **{i: replace(cx.places[i], pins=()) for i in ids if i in cx.places}})


def validate(ctxs: list[DayCtx], results: list[DayResult], hard_filters: list, anchors: set,
             budget_vnd: int | None, max_leg_min: int | None, *, day_cache: dict | None = None,
             cache_limit: int = 128) -> list[Violation]:
    if day_cache is not None:
        out, visited = [], {}
        for cx, result in zip(ctxs, results):
            day_visited = {i.place_id for i in result.items if i.kind == "visit"}
            travel_nodes = {node for i in result.items if i.kind == "travel" for node in (i.from_id, i.to_id)
                            if node is not None}
            key = fingerprint((day_key(cx, day_visited), travel_key(cx.travel, travel_nodes), result,
                               hard_filters, budget_vnd, max_leg_min))
            if key not in day_cache:
                put(day_cache, key, validate([cx], [result], hard_filters, set(), budget_vnd, max_leg_min), cache_limit)
            out.extend(day_cache[key])
            for pid in day_visited:
                if pid in visited:
                    out.append(Violation("duplicate", cx.day.index, pid, 0, False, "the place is scheduled twice"))
                visited[pid] = cx.day.index
        for pid in sorted(anchors - set(visited)):
            out.append(Violation("anchor", None, pid, 0, False, "an anchor is not in the plan"))
        return out
    out: list[Violation] = []
    visited: dict = {}
    for cx, r in zip(ctxs, results):
        cx = _released(cx, r)
        d = cx.day
        items = sorted(r.items, key=lambda i: (i.start, i.end))
        for a, b in zip(items, items[1:]):
            if b.start < a.end:
                out.append(Violation("overlap", d.index, b.place_id or a.place_id, a.end - b.start, False,
                                     f"{a.kind} and {b.kind} overlap"))
        for a, b, kind, label, _ in d.busy:         # the user's fixed times are theirs (user hard)
            for it in items:
                if it.kind in {"visit", "travel"} and it.start < b and a < it.end:
                    out.append(Violation("busy", d.index, it.place_id or it.to_id, min(b, it.end) - max(a, it.start),
                                         False, f"overlaps {label}"))
        last_end = max((it.end for it in items), default=None)
        if d.depart_by is not None and last_end is not None and last_end > d.depart_by:     # whatever the window says
            out.append(Violation("departure", d.index, None, last_end - d.depart_by, True, "misses the departure"))
        cap = (cx.cfg.realistic or {}).get("drive_day_min")
        drive = sum(cx.travel.leg(i.from_id, i.to_id)[0] for i in items if i.kind == "travel")
        if cap and drive > cap:
            out.append(Violation("drive_day", d.index, None, drive - cap, False, f"over {cap} min of driving"))
        if items and items[-1].end > d.end:
            out.append(Violation("day_window", d.index, None, items[-1].end - d.end, False, "the day runs past its end"))
        if items and items[0].start < d.start:
            out.append(Violation("day_window", d.index, None, d.start - items[0].start, False, "starts before the day"))
        spend = 0
        meal_slots = set()
        for it in items:
            if it.kind == 'meal_free':
                window = cx.cfg.meal_windows.get(it.name)
                if window and window[0] <= it.start <= window[1] and it.end - it.start >= meal_floor(it.name, cx):
                    if it.name in meal_slots:
                        out.append(Violation('meal_window', d.index, None, 0, False, 'the meal is scheduled twice'))
                    meal_slots.add(it.name)
                else:
                    out.append(Violation('meal_window', d.index, None, 0, False, 'invalid free meal block'))
            if it.kind == "travel":
                need = cx.travel.leg(it.from_id, it.to_id)[0]
                if it.end - it.start < need:
                    out.append(Violation("travel", d.index, it.to_id, need - (it.end - it.start), False,
                                         "shorter than the travel time"))
                if max_leg_min and need > max_leg_min:      # the road, not the buffer that rides on it
                    out.append(Violation("long_leg", d.index, it.to_id, need - max_leg_min, False,
                                         f"longer than {max_leg_min} min"))
            if it.kind != "visit":
                continue
            p = cx.places[it.place_id]
            if cx.require_meals and it.end - it.start < p.visit["short"]:
                out.append(Violation("visit_duration", d.index, p.id, p.visit["short"] - (it.end - it.start), False,
                                     "visit shorter than the minimum estimate"))
            if takes_meal_slot(p):
                names = list(cx.cfg.meal_windows)[:cx.cfg.meals_per_day]
                slot = next((name for name in names if name not in meal_slots
                             and cx.cfg.meal_windows[name][0] <= it.start <= cx.cfg.meal_windows[name][1]), None)
                if slot is None:
                    out.append(Violation('meal_window', d.index, p.id, 0, False, 'no distinct meal window for this visit'))
                else:
                    meal_slots.add(slot)
            if not any(o <= it.start and it.end <= c for o, c in intervals_for(p, cx)):
                out.append(Violation("hours", d.index, p.id, 0, False, "visit outside the opening hours"))
            if why := hazard(p, cx.cond):
                out.append(Violation("hazard", d.index, p.id, 0, False, f"hazard that day: {why}"))
            lo, hi = pin_window(p, cx)
            if not lo <= it.start <= hi:
                out.append(Violation("timed", d.index, p.id, 0, False, "off the time of day its feature needs"))
            if p.id in visited:
                out.append(Violation("duplicate", d.index, p.id, 0, False, "the place is scheduled twice"))
            visited[p.id] = d.index
            spend += p.cost_vnd or 0
            for hf in hard_filters:
                if hf["feature"] not in p.relaxed \
                        and not allowed(p.rec, hf, p.activity, p.kind):
                    verdict = hard_result(p.rec, hf, p.activity, p.kind)[0]
                    out.append(Violation("hard", d.index, p.id, 0, _is_physical(hf["feature"]),
                                         f'{hf["feature"]} {"==" if hf["op"] == "eq" else "!="} {hf["value"]}: {verdict}'))
        if cx.require_meals and any(it.kind == "visit" for it in items):
            for name in meals_needed(items, cx):
                out.append(Violation('meal_missing', d.index, None, 0, False, f'missing {name}'))
        if budget_vnd and spend > budget_vnd:
            out.append(Violation("budget", d.index, None, spend - budget_vnd, False,
                                 f"{spend} VND per person against {budget_vnd}"))
    for pid in sorted(anchors - set(visited)):
        out.append(Violation("anchor", None, pid, 0, False, "an anchor is not in the plan"))
    return out
