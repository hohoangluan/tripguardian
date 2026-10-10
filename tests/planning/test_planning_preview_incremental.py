"""Preview dependencies, concurrency and stable incremental scheduling without network."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import threading
from types import SimpleNamespace

from plan_fixtures import CFG, FakeLive, decision, fake_matrix, fixed_sun, no_geocode, rec
from planning.engine import Engine
from datetime import UTC


def make_engine(records, **kwargs):
    return Engine(records, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode,
                  matrix_fn=fake_matrix, sun_fn=fixed_sun, lodging_fn=lambda *a: [],
                  background=False, **kwargs)


def test_logs_and_selection_order_do_not_rebuild_the_same_schedule(monkeypatch):
    records = [rec('a', 11.9, 108.4), rec('b', 11.91, 108.41)]
    e = make_engine(records)
    d = decision(['a', 'b'])
    first = e.preview(d)
    calls, original = [], e._build_base
    monkeypatch.setattr(e, '_build_base', lambda d: calls.append(d) or original(d))
    d['decision_log'] = [{'action': 'select'}]
    d['feasibility'] = {'status': 'feasible'}
    d['confirmed'].reverse()
    assert e.preview(d) == first
    assert not calls


def test_concurrent_identical_previews_build_once(monkeypatch):
    e = make_engine([rec('a', 11.9, 108.4)])
    d = decision(['a'])
    entered, release = threading.Event(), threading.Event()
    calls, original = [], e._build_base
    def build(d):
        calls.append(d)
        entered.set()
        assert release.wait(5)
        return original(d)
    monkeypatch.setattr(e, '_build_base', build)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(e.preview, deepcopy(d)) for _ in range(4)]
        assert entered.wait(5)
        release.set()
        results = [f.result(timeout=5) for f in futures]
    assert len(calls) == 1
    assert all(r == results[0] for r in results)


def test_dropping_a_place_reuses_matrix_and_unaffected_days(monkeypatch):
    records = [rec('a', 11.9, 108.4, area='south'), rec('b', 11.91, 108.41, area='south'),
               rec('c', 12.1, 108.5, area='north')]
    e = make_engine(records)
    calls, original = [], e.matrix_fn
    e.matrix_fn = lambda *args: calls.append(1) or original(*args)
    first = e.preview(decision(['a', 'b', 'c']))
    second = e.preview(decision(['a', 'c']))
    assert len(calls) == 1
    assert second['ok']
    assert sorted(i for day in second['variants'][0]['places'] for i in day) == ['a', 'c']
    original_day = next(k for k, ids in enumerate(first['variants'][0]['places']) if ids == ['c'])
    assert second['variants'][0]['places'][original_day] == ['c']


def test_selecting_one_more_place_preserves_other_days():
    records = [rec('a', 11.9, 108.4, area='south'), rec('b', 11.901, 108.401, area='south'),
               rec('c', 12.1, 108.5, area='north')]
    e = make_engine(records)
    before = e.preview(decision(['a', 'c']))
    after = e.preview(decision(['a', 'b', 'c']))
    old_day = next(k for k, ids in enumerate(before['variants'][0]['places']) if ids == ['c'])
    assert after['ok'] and after['variants'][0]['places'][old_day] == ['c']


def test_context_changes_invalidate_preview():
    e = make_engine([rec('a', 11.9, 108.4)])
    assert e.preview(decision(['a'], days=2))['days'] == 2
    assert e.preview(decision(['a'], days=3))['days'] == 3


def test_create_owns_a_detached_preview_and_the_current_decision_log():
    e = make_engine([rec('a', 11.9, 108.4)])
    d = decision(['a'])
    preview = e.preview(d)
    confirmed = deepcopy(d)
    confirmed['decision_log'] = [{'op': 'confirm'}]
    out = e.create(confirmed)
    assert e.store.get(out['id']).decision['decision_log'] == confirmed['decision_log']
    e.act(out['id'], {'type': 'pick_variant', 'id': out['view']['variants'][0]['id']})
    assert e.preview(d) == preview


def test_preview_expires_with_the_matrix_it_reused(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr('planning.preview.time.monotonic', lambda: clock[0])
    records = [rec('a', 11.9, 108.4), rec('b', 11.91, 108.41), rec('c', 12.1, 108.5)]
    e = make_engine(records)
    e.live_cfg = SimpleNamespace(tz_offset_h=7, ttl_s={'osrm': 10, 'weather': 30, 'geocode': 40})
    calls, original = [], e.matrix_fn
    from datetime import datetime
    e.matrix_fn = lambda *args: calls.append(clock[0]) or {
        **original(*args), 'fetched_at': datetime.now(UTC).isoformat()}
    e.preview(decision(['a', 'b', 'c']))
    clock[0] = 108.0
    e.preview(decision(['a', 'c']))
    assert calls == [100.0]
    clock[0] = 111.0
    e.preview(decision(['a', 'c']))
    assert calls == [100.0, 111.0]


def test_preview_invalidates_when_planning_policy_changes():
    e = make_engine([rec('a', 11.9, 108.4)])
    d = decision(['a'], days=None)
    before = e.preview(d)['days']
    e.cfg = replace(e.cfg, default_days=before + 1)
    assert e.preview(d)['days'] == before + 1


def test_preview_selection_stability_is_scoped_to_the_journey(monkeypatch):
    e = make_engine([rec('a', 11.9, 108.4), rec('b', 11.91, 108.41)])
    e.preview(decision(['a', 'b']), namespace='journey-a')
    calls, original = [], e._build_base
    monkeypatch.setattr(e, '_build_base', lambda *a, **kw: calls.append(kw) or original(*a, **kw))
    e.preview(decision(['a', 'b']), namespace='journey-b')
    assert len(calls) == 1
    out = e.create(decision(['a', 'b']), namespace='journey-b')
    assert out['view']['ok'] and len(calls) == 1


def test_matrix_cache_invalidation_includes_live_configuration():
    from planning.preview import Resources
    resources, calls = Resources(), []
    points = [(11.9, 108.4), (12.1, 108.5)]
    def provider(points, mode, cfg):
        calls.append(cfg.osrm_profile)
        return {'minutes': [[0, cfg.factor], [cfg.factor, 0]], 'source': 'osrm', 'fetched_at': 'fixture'}
    cfg = SimpleNamespace(osrm_profile='driving', factor=10)
    resources.matrix(points, 'car', cfg, provider, 30)
    cfg = SimpleNamespace(osrm_profile='cycling', factor=20)
    assert resources.matrix(points, 'car', cfg, provider, 30)['minutes'][0][1] == 20
    assert calls == ['driving', 'cycling']


def test_unchanged_day_routes_are_reused_but_changed_legs_are_not(monkeypatch):
    records = [rec('a', 11.9, 108.4, area='south'), rec('b', 11.91, 108.41, area='south'),
               rec('c', 12.1, 108.5, area='north')]
    e = make_engine(records)
    e.preview(decision(['a', 'b', 'c']))
    from planning.route import order_day
    calls = []
    def tracked(ids, *args, **kwargs):
        calls.append(tuple(ids))
        return order_day(ids, *args, **kwargs)
    monkeypatch.setattr('planning.route.order_day', tracked)
    monkeypatch.setattr('planning.build.order_day', tracked)
    e.preview(decision(['a', 'c']))
    assert ('c',) not in calls
    e.cfg = replace(e.cfg, buffer_min={pace: minutes + 1 for pace, minutes in e.cfg.buffer_min.items()})
    e.preview(decision(['a', 'c']))
    assert ('c',) in calls


def test_resource_cache_honors_original_source_freshness_for_matrix_and_nested_weather(monkeypatch):
    from datetime import datetime
    from planning.preview import Resources
    clock = [100.0]
    monkeypatch.setattr('planning.preview.time.monotonic', lambda: clock[0])
    monkeypatch.setattr('planning.preview.time.time', lambda: 1000 + clock[0] - 100)
    fetched = datetime.fromtimestamp(991, UTC).isoformat()
    resources, calls, deadlines = Resources(), [], []
    cfg = SimpleNamespace(ttl_s={'osrm': 10})
    def provider(*args):
        calls.append(clock[0])
        return {'minutes': [[0, 10], [10, 0]], 'source': 'osrm', 'fetched_at': fetched}
    points = [(11.9, 108.4), (12.1, 108.5)]
    resources.matrix(points, 'car', cfg, provider, 10, deadlines)
    assert deadlines == [101.0]
    clock[0] = 102.0
    resources.matrix(points, 'car', cfg, provider, 10)
    assert calls == [100.0, 102.0]
    deadlines.clear()
    resources.get('weather', 10, lambda: ({'2026-10-09': {'fetched_at': fetched}}, {}),
                  deadlines, source_ttl=10)
    assert deadlines == [102.0]


def test_namespaced_create_passes_namespace_on_a_preview_cache_miss(monkeypatch):
    e = make_engine([rec('a', 11.9, 108.4)])
    namespaces, original = [], e._build_base
    def tracked(decision, namespace=None):
        namespaces.append(namespace)
        return original(decision, namespace)
    monkeypatch.setattr(e, '_build_base', tracked)
    e.create(decision(['a']), namespace='journey-a')
    assert namespaces == ['journey-a']
