"""Stable weekly allocation with bounded, deterministic load and type balancing."""

from collections import Counter
from math import ceil

from .geo import km, point, to_min

CHUNK_DAYS = 7


def place_type(c):
    return "meal" if c.role == "meal" else c.rec["identity"].get("category_group") or "unknown"


def assign_chunks(chosen, previous, days, cfg):
    groups = [days[i:i + CHUNK_DAYS] for i in range(0, len(days), CHUNK_DAYS)]
    mapping = {c.id: previous[c.id] for c in chosen
               if type(previous.get(c.id)) is int and 0 <= previous[c.id] < len(groups)}
    members = [[c for c in chosen if mapping.get(c.id) == k] for k in range(len(groups))]
    counts = [Counter(place_type(c) for c in group) for group in members]
    capacities = [max(1, sum(max(0, d.end - d.start) for d in group)) for group in groups]

    def load(c):
        return ((c.rec["operation"].get("visit_minutes") or {}).get("typical") or 60) + cfg.intra_leg_min

    loads = [sum(load(c) for c in group) for group in members]
    for c in chosen:
        if c.id in mapping:
            continue
        hours = c.rec["operation"].get("hours")
        # Unknown/outdated hours never become evidence of closure.
        eligible = [k for k, group in enumerate(groups) if not hours or hours.get("status") != "VERIFIED"
                    or any(d.weekday is None or any(to_min(a) < d.end and to_min(b) > d.start
                                                   for a, b in hours["value"].get(d.weekday, [])) for d in group)]
        candidates = eligible or list(range(len(groups)))
        p = point(c.rec)

        def score(k):
            peers = [point(x.rec) for x in members[k] if point(x.rec)]
            centre = (sum(x[0] for x in peers) / len(peers), sum(x[1] for x in peers) / len(peers)) if peers else None
            distance = min(km(p, centre) / max(cfg.far_km, 1), 1) if p and centre else 0
            # Per-day counts support partial final weeks; type balance outweighs geographic ties.
            return (counts[k][place_type(c)] / len(groups[k]) + loads[k] / capacities[k]
                    + 0.1 * distance, len(members[k]) / len(groups[k]), k)

        k = min(candidates, key=score)
        mapping[c.id] = k
        members[k].append(c)
        counts[k][place_type(c)] += 1
        loads[k] += load(c)
    return mapping


def describe_chunks(chosen, mapping, days):
    return [{"id": k, "start_day": k * CHUNK_DAYS + 1, "end_day": min((k + 1) * CHUNK_DAYS, len(days)),
             "places": [c.id for c in chosen if mapping.get(c.id) == k],
             "type_counts": dict(Counter(place_type(c) for c in chosen if mapping.get(c.id) == k))}
            for k in range(ceil(len(days) / CHUNK_DAYS))]


def coverage(chosen, si, days, feas, cfg, free_time):
    full = max(1, to_min(cfg.day_end) - to_min(cfg.day_start))
    target = ceil(sum(max(0, d.end - d.start) / full for d in days) * cfg.per_day[si.pace.level or "normal"])
    selected = sum(c.role == "experience" for c in chosen)
    return {"status": "unknown" if si.context.days is None else "sparse" if selected < target / 2 else "enough",
            "selected_experiences": selected, "target_experiences": target,
            "free_minutes_estimate": max(0, feas["slack"]) if feas.get("slack") is not None else None,
            "free_time_accepted": free_time}
