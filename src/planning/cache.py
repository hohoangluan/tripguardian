"""Bounded RAM entries keyed by the actual inputs of a day's computation."""

import hashlib
import json
from dataclasses import is_dataclass


def fingerprint(value) -> str:
    def encode(obj):
        return vars(obj) if is_dataclass(obj) else str(obj)
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=encode).encode()).hexdigest()


_BY_ID: dict = {}          # id(frozen object) -> (object, fingerprint): Settings and Place are frozen and never mutated
_BY_ID_MAX = 8192


def _frozen_fp(obj, encode) -> str:
    """The fingerprint of a frozen dataclass, computed once per object: a Place carries its whole serving record
    and Settings every config table, which made serializing them most of a day key's cost. The object is held in the
    entry, so its id is never reused while the entry lives."""
    hit = _BY_ID.get(id(obj))
    if hit is not None and hit[0] is obj:
        return hit[1]
    if len(_BY_ID) >= _BY_ID_MAX:
        _BY_ID.clear()
    fp = fingerprint(encode(obj))
    _BY_ID[id(obj)] = (obj, fp)
    return fp


def _cfg_fields(cfg) -> dict:
    # Day-split weights choose membership; simulate() does not read them.
    return {k: v for k, v in vars(cfg).items() if k != "weights"}


def day_key(cx, ids) -> str:
    ids = sorted(set(ids))
    nodes = sorted(set(ids) | {n for n in (cx.day.start_node, cx.day.end_node) if n is not None})
    fields = {k: v for k, v in vars(cx).items() if k not in {"places", "travel", "prefs"}}
    fields["cfg"] = _frozen_fp(cx.cfg, _cfg_fields)
    fields["places"] = {pid: _frozen_fp(cx.places[pid], vars) for pid in ids}
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
