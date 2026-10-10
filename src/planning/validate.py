"""Final check (docs/ARCHITECTURE.md §11): the only place that decides whether a plan passes.

It re-derives every check from the finished timeline instead of trusting what simulate() noticed, so a bug in the
scheduler cannot also hide from the check. Fail-closed: a violation is reported, never repaired here.
"""

from dataclasses import replace

from corpus.ontology import load as load_ontology
from corpus.serving import check, feature

from .conditions import hazard
from .model import DayResult, Violation
from .schedule import DayCtx, intervals_for, pin_window


def _is_physical(feature: str) -> bool:
    f = load_ontology().features.get(feature)
    return f is not None and f.group == "effort"


def blockers(violations, per_day: list[list[str]]) -> dict:
    """What stopped every variant, for the screen that sends the user back: the places involved (a violation without a
    place names its day's places) and one reason per kind / place / day, so "stuck at X" always says why."""
    places = sorted({v.place_id for v in violations if v.place_id})
    if not places:
        places = sorted({i for v in violations if v.day is not None and v.day < len(per_day) for i in per_day[v.day]})
    seen, reasons = set(), []
    for v in violations:
        if (v.kind, v.place_id, v.day) not in seen:
            seen.add((v.kind, v.place_id, v.day))
            reasons.append({"kind": v.kind, "place_id": v.place_id, "day": v.day, "minutes": v.minutes})
    return {"reason": "no_valid_variant", "places": places, "reasons": reasons}


def _released(cx: DayCtx, r: DayResult) -> DayCtx:
    """The day as the scheduler laid it out: a place whose time-of-day pin it gave up (and said so) is not held to it.
    Without this, a plan shown as valid would fail the same check at confirm."""
    if not r.unpinned:
        return cx
    return replace(cx, places={**cx.places, **{i: replace(cx.places[i], pins=()) for i in r.unpinned if i in cx.places}})


def validate(ctxs: list[DayCtx], results: list[DayResult], hard_filters: list, anchors: set,
             budget_vnd: int | None, max_leg_min: int | None, *,
             required_visits: set[str] | None = None) -> list[Violation]:
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
        if items and items[-1].end > d.end:
            out.append(Violation("day_window", d.index, None, items[-1].end - d.end, False, "the day runs past its end"))
        if items and items[0].start < d.start:
            out.append(Violation("day_window", d.index, None, d.start - items[0].start, False, "starts before the day"))
        spend = 0
        for it in items:
            if it.kind == "travel":
                need = cx.travel.leg(it.from_id, it.to_id)[0]
                if it.end - it.start < need:
                    out.append(Violation("travel", d.index, it.to_id, need - (it.end - it.start), False,
                                         "shorter than the travel time"))
                if max_leg_min and it.end - it.start > max_leg_min:
                    out.append(Violation("long_leg", d.index, it.to_id, it.end - it.start - max_leg_min, False,
                                         f"longer than {max_leg_min} min"))
            if it.kind != "visit":
                continue
            p = cx.places[it.place_id]
            if p.requested_start is not None and it.start != p.requested_start:
                out.append(Violation("requested_start", d.index, p.id, abs(it.start - p.requested_start), False,
                                     "visit does not match the requested start"))
            if p.requested_duration is not None and it.end - it.start != p.requested_duration:
                out.append(Violation("requested_duration", d.index, p.id,
                                     abs(it.end - it.start - p.requested_duration), False,
                                     "visit does not match the requested duration"))
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
                physical = _is_physical(hf["feature"])
                if physical or hf["feature"] not in p.relaxed:
                    status = "unknown"
                    if hf["op"] == "ne":
                        status = check(p.rec, hf["feature"], hf["value"])
                    elif hf["op"] == "eq":
                        evidence = feature(p.rec, hf["feature"])
                        if evidence and evidence["status"] in ("VERIFIED", "OUTDATED"):
                            if evidence["value"] != hf["value"]:
                                status = "fail"
                            elif set(evidence["distribution"]) <= {hf["value"]}:
                                status = "pass"
                    if status != "pass":
                        operator = "!=" if hf["op"] == "ne" else "=="
                        out.append(Violation("hard", d.index, p.id, 0, physical,
                                             f'{hf["feature"]} {operator} {hf["value"]}: {status}'))
        if budget_vnd and spend > budget_vnd:
            out.append(Violation("budget", d.index, None, spend - budget_vnd, False,
                                 f"{spend} VND per person against {budget_vnd}"))
    for pid in sorted(anchors - set(visited)):
        out.append(Violation("anchor", None, pid, 0, False, "an anchor is not in the plan"))
    for pid in sorted((required_visits or set()) - set(visited)):
        out.append(Violation("requested_visit", None, pid, 0, False, "a requested visit is not in the plan"))
    return out
