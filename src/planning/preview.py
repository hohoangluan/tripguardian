"""Bounded preview resources and stable scheduling across selection changes."""
from concurrent.futures import Future
from copy import copy, deepcopy
from dataclasses import asdict, is_dataclass, replace
from datetime import datetime
import hashlib
import json
import threading
import time


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def configuration_key(cfg):
    return fingerprint(asdict(cfg) if is_dataclass(cfg) else vars(cfg))


def source_deadline(value, deadline, ttl):
    """Disk-cache hits retain their original freshness, including weather keyed by date."""
    if ttl is None:
        return deadline
    if isinstance(value, dict):
        fetched = value.get('fetched_at')
        if isinstance(fetched, str):
            try:
                stamp = datetime.fromisoformat(fetched)
                if stamp.tzinfo is not None:
                    remaining = max(0, stamp.timestamp() + ttl - time.time())
                    deadline = min(deadline, time.monotonic() + remaining)
            except ValueError:
                pass
        values = value.values()
    elif isinstance(value, (list, tuple)):
        values = value
    else:
        return deadline
    for nested in values:
        deadline = source_deadline(nested, deadline, ttl)
    return deadline


def decision_dependencies(decision):
    """Presentation logs, wishlist and coarse feasibility do not affect the schedule."""
    return {'trip_context': decision['trip_context'],
            'confirmed': sorted(decision['confirmed'], key=lambda p: p['id']),
            'backup_pool': decision.get('backup_pool') or []}


class Resources:
    """Coalesce identical I/O; timestamps never move on cache hits."""
    def __init__(self, limit=64):
        self.limit = limit
        self.lock = threading.RLock()
        self.values = {}
        self.flights = {}
        self.matrices = {}

    def get(self, key, ttl, build, deadlines=None, *, source_ttl=None):
        with self.lock:
            hit = self.values.get(key)
            if hit and time.monotonic() < hit[0]:
                if deadlines is not None:
                    deadlines.append(hit[0])
                return hit[1]
            future = self.flights.get(key)
            owner = future is None
            if owner:
                future = self.flights[key] = Future()
        if not owner:
            at, value = future.result()
            if deadlines is not None:
                deadlines.append(at)
            return value
        try:
            at = time.monotonic()
            value = build()
            expires = source_deadline(value, at + ttl, source_ttl)
            with self.lock:
                self.values[key] = (expires, value)
                while len(self.values) > self.limit:
                    self.values.pop(next(iter(self.values)))
            future.set_result((expires, value))
            if deadlines is not None:
                deadlines.append(expires)
            return value
        except BaseException as error:
            future.set_exception(error)
            raise
        finally:
            with self.lock:
                self.flights.pop(key, None)

    def matrix(self, points, mode, cfg, provider, ttl, deadlines=None):
        coords = tuple(tuple(p) for p in points)
        namespace = (mode, provider, configuration_key(cfg))
        source_ttl = getattr(cfg, 'ttl_s', {}).get('osrm')
        with self.lock:
            for (ns, known), (at, result) in list(self.matrices.items()):
                if time.monotonic() >= at:
                    self.matrices.pop((ns, known), None)
                    continue
                if ns == namespace and set(coords) <= set(known):
                    if deadlines is not None:
                        deadlines.append(at)
                    indices = [known.index(p) for p in coords]
                    return {**result, 'minutes': [[result['minutes'][i][j] for j in indices] for i in indices]}
        key = ('matrix', namespace, coords)
        def fetch():
            at = time.monotonic()
            result = provider(points, mode, cfg)
            expires = source_deadline(result, at + ttl, source_ttl)
            with self.lock:
                self.matrices[(namespace, coords)] = (expires, result)
                while len(self.matrices) > self.limit:
                    self.matrices.pop(next(iter(self.matrices)))
            return result
        return self.get(key, ttl, fetch, deadlines, source_ttl=source_ttl)


def detached(base, decision):
    """A session may mutate its base; it never owns the cached preview objects."""
    out = copy(base)
    out.trip = replace(base.trip, decision=decision, routes=dict(base.trip.routes))
    out.variants = deepcopy(base.variants)
    out.comparison = deepcopy(base.comparison)
    out.warnings = deepcopy(base.warnings)
    out.lodging_candidates = deepcopy(base.lodging_candidates)
    out.added = set(base.added)
    return out


def incremental_schedule(trip, previous, weights):
    """Keep days stable, try full visits on every day, then fall back to the complete solver."""
    from .build import Schedule, pull_early, relocate_days, route_key
    from .route import order_day
    from .validate import validate
    if len(previous) != len(trip.ctxs):
        return None
    ctxs = [replace(cx, cfg=replace(trip.cfg, weights={**trip.cfg.weights, **weights})) for cx in trip.ctxs]
    members = [[i for i in r.order if i in trip.by_place] for r in previous]
    before = {i for r in previous for i in r.order}
    tc = trip.decision['trip_context']
    hard, budget = tc.get('hard_filters') or [], tc['context'].get('budget_vnd')
    max_leg = (tc.get('pace') or {}).get('max_leg_min')

    def layout(ids, cx, shrink=False):
        cx, _ = pull_early(cx, ids, trip.by_place, trip.travel)
        key = route_key(ids, cx, shrink=shrink)
        if key not in trip.routes:
            trip.routes[key] = order_day(ids, cx, shrink=shrink)
        result = trip.routes[key]
        failures = validate([cx], [result], hard, set(), budget, max_leg)
        return cx, result, failures

    for pid in sorted(set(trip.by_place) - before):
        candidates = []
        for day, ids in enumerate(members):
            cx, result, failures = layout([*ids, pid], ctxs[day])
            if not failures:
                _, old, _ = layout(ids, ctxs[day])
                candidates.append(((result.travel_min - old.travel_min,
                                    result.timing_penalty, len(ids), day), day, cx))
        if not candidates:
            return None
        _, day, cx = min(candidates, key=lambda c: c[0])
        members[day].append(pid)
        ctxs[day] = cx
    members, ctxs = relocate_days(members, ctxs, trip, hard, budget, max_leg)
    results = []
    for day, ids in enumerate(members):
        cx, result, failures = layout(ids, ctxs[day])
        if failures:
            return None
        ctxs[day] = cx
        results.append(result)
    anchors = {p['id'] for p in trip.decision['confirmed'] if p.get('role') == 'anchor'}
    violations = validate(ctxs, results, hard, anchors, budget, max_leg)
    if violations:
        return None
    return Schedule(members, results, ctxs, [], [])
