"""Bounded RAM entries keyed by the actual inputs of a day's computation."""

import hashlib
import json
from dataclasses import is_dataclass


def fingerprint(value) -> str:
    def encode(obj):
        return vars(obj) if is_dataclass(obj) else str(obj)
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=encode).encode()).hexdigest()


def day_key(cx, ids) -> str:
    ids = sorted(set(ids))
    nodes = sorted(set(ids) | {n for n in (cx.day.start_node, cx.day.end_node) if n is not None})
    fields = {k: v for k, v in vars(cx).items() if k not in {"places", "travel", "prefs"}}
    # Day-split weights choose membership; simulate() does not read them.
    fields["cfg"] = {k: v for k, v in vars(cx.cfg).items() if k != "weights"}
    fields["places"] = {pid: cx.places[pid] for pid in ids}
    fields["prefs"] = {pid: (cx.prefs or {}).get(pid) for pid in ids}
    fields["travel"] = travel_key(cx.travel, nodes)
    return fingerprint(fields)


def travel_key(travel, nodes) -> str:
    nodes = sorted(set(nodes) & set(travel.index))
    return fingerprint((nodes, travel.source, travel.fetched_at,
                        [[travel.leg(a, b) for b in nodes] for a in nodes]))


def put(cache: dict, key, value, limit: int):
    cache[key] = value
    while len(cache) > limit:
        cache.pop(next(iter(cache)))
    return value
