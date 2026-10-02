"""Final check (docs/ARCHITECTURE.md §11): the only place that decides whether a plan passes.

It re-derives every check from the finished timeline instead of trusting what simulate() noticed, so a bug in the
scheduler cannot also hide from the check. Fail-closed: a violation is reported, never repaired here.
"""

from corpus.ontology import load as load_ontology
from corpus.serving import check

from .model import DayResult, Violation
from .schedule import DayCtx, intervals_for, pin_window


def _is_physical(feature: str) -> bool:
    f = load_ontology().features.get(feature)
    return f is not None and f.group == "effort"


def validate(ctxs: list[DayCtx], results: list[DayResult], hard_filters: list, anchors: set,
             budget_vnd: int | None, max_leg_min: int | None) -> list[Violation]:
    out: list[Violation] = []
    visited: dict = {}
    dup_groups: dict = {}
    for cx, r in zip(ctxs, results):
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
            if not any(o <= it.start and it.end <= c for o, c in intervals_for(p, cx)):
                out.append(Violation("hours", d.index, p.id, 0, False, "visit outside the opening hours"))
            lo, hi = pin_window(p, cx)
            if not lo <= it.start <= hi:
                out.append(Violation("timed", d.index, p.id, 0, False, "off the time of day its feature needs"))
            if p.id in visited:
                out.append(Violation("duplicate", d.index, p.id, 0, False, "the place is scheduled twice"))
            visited[p.id] = d.index
            if p.dup_group is not None and dup_groups.setdefault(p.dup_group, p.id) != p.id:
                out.append(Violation("duplicate", d.index, p.id, 0, False,
                                     f"near duplicate of {dup_groups[p.dup_group]}"))
            spend += p.cost_vnd or 0
            for hf in hard_filters:
                if hf["op"] == "ne" and hf["feature"] not in p.relaxed \
                        and check(p.rec, hf["feature"], hf["value"]) == "fail":
                    out.append(Violation("hard", d.index, p.id, 0, _is_physical(hf["feature"]),
                                         f'{hf["feature"]} != {hf["value"]}'))
        if budget_vnd and spend > budget_vnd:
            out.append(Violation("budget", d.index, None, spend - budget_vnd, False,
                                 f"{spend} VND per person against {budget_vnd}"))
    for pid in sorted(anchors - set(visited)):
        out.append(Violation("anchor", None, pid, 0, False, "an anchor is not in the plan"))
    return out
