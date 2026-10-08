import pytest
from plan_fixtures import CFG, FakeLive, fake_lodging, fake_matrix, no_geocode, small_trip
from planning.engine import Engine


def started(agent):
    decision, records = small_trip()
    e = Engine(records, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode,
               matrix_fn=fake_matrix, sun_fn=lambda *a: (360, 1050),
               lodging_fn=fake_lodging, route_fn=lambda *a: {'points': []},
               background=False, proposal_agent=agent)
    return e, e.create(decision)['id']


@pytest.mark.parametrize('bad', ['variant', 'fingerprint', 'unlock', 'relax', 'drop_place', 'add_from_backup', 'say', 'reason'])
def test_invalid_proposal_keeps_deterministic_baseline(bad):
    calls = []
    async def agent(fields):
        calls.append(fields)
        p = {'fingerprint': fields['fingerprint'], 'variant_id': fields['variants'][0]['id']}
        if bad == 'variant': p['variant_id'] = 'V999'
        elif bad == 'fingerprint': p['fingerprint'] = 'stale'
        elif bad == 'say': p['say'] = 'invented 999 minutes'
        elif bad == 'reason': p['reasons'] = ['invented']
        else: p['acts'] = [{'type': bad, 'place': 'a'}]
        return p
    e, sid = started(agent)
    out = e.recommend(sid)
    assert out['id'] == sid and out['view']['itinerary']
    assert out['proposal']['status'] == 'fallback'
    assert len(calls) == 1
    assert out['view']['state']['chosen_variant'] == 'v1'
    assert out['view']['state']['locked'] == []


def test_valid_existing_variant_is_accepted():
    async def agent(fields):
        return {'fingerprint': fields['fingerprint'], 'variant_id': fields['variants'][0]['id']}
    e, sid = started(agent)
    out = e.recommend(sid)
    assert out['proposal']['status'] == 'accepted'
    assert e.confirm(sid)['chosen']


def test_timeout_preserves_baseline():
    async def agent(fields):
        raise TimeoutError()
    e, sid = started(agent)
    assert e.recommend(sid)['proposal']['status'] == 'fallback'
    assert e.load(sid)['view']['itinerary']


def test_reorder_cannot_change_locked_scheduled_slot():
    async def agent(fields):
        return {'fingerprint': fields['fingerprint'], 'variant_id': 'v1',
                'acts': [{'type': 'reorder', 'day': 0, 'order': ['c', 'b', 'a']}]}
    e, sid = started(agent)
    e.act(sid, {'type': 'pick_variant', 'id': 'v1'})
    e.act(sid, {'type': 'lock_slot', 'place': 'a'})
    before = e.load(sid)
    assert e.recommend(sid)['proposal']['status'] == 'fallback'
    assert e.load(sid) == before


def test_valid_noop_reorder_and_restart_replay(tmp_path):
    from planning.session import Store
    async def agent(fields):
        order = [item['place_id'] for item in fields['itinerary'][0]['items'] if item['kind'] == 'visit']
        return {'fingerprint': fields['fingerprint'], 'variant_id': 'v1',
                'acts': [{'type': 'reorder', 'day': 0, 'order': order}]}
    e, sid = started(agent)
    e.store.root = tmp_path
    out = e.recommend(sid)
    assert out['proposal']['status'] == 'accepted'
    e2, _ = started(agent)
    e2.store = Store(tmp_path)
    assert e2.load(sid)['view']['itinerary'] == out['view']['itinerary']


def test_wrapper_uses_structured_schema_and_stream_deadlines():
    import asyncio
    from dataclasses import replace
    from planning.proposal import run_proposal
    from agents import AgentError
    async def valid(fields):
        yield '{"fingerprint":"f","variant_id":"v1","acts":[],"reasons":[]}'
    assert asyncio.run(run_proposal({}, CFG, valid)).variant_id == 'v1'
    async def slow(fields):
        await asyncio.sleep(.05)
        yield '{}'
    with pytest.raises(AgentError):
        asyncio.run(run_proposal({}, replace(CFG, first_token_s=.001, total_s=.01), slow))


def test_unknown_place_alias_is_rejected():
    async def agent(fields):
        return {'fingerprint': fields['fingerprint'], 'variant_id': 'v1',
                'acts': [{'type': 'move_place', 'place': 'P1', 'day': 0}]}
    e, sid = started(agent)
    out = e.recommend(sid)
    assert out['proposal']['status'] == 'fallback'
    assert out['view']['state']['assignment'] == {}


def test_persist_failure_does_not_commit_draft():
    async def agent(fields):
        return {'fingerprint': fields['fingerprint'], 'variant_id': 'v1'}
    e, sid = started(agent)
    e.act(sid, {'type': 'pick_variant', 'id': 'v1'})
    before = e.store.get(sid).model_dump()
    def fail_save(session):
        raise OSError('disk full')
    e.store.save = fail_save
    assert e.recommend(sid)['proposal']['status'] == 'fallback'
    assert e.store.get(sid).model_dump() == before


def test_lower_travel_cannot_worsen_current_diversity_objective():
    from plan_fixtures import CENTRE, SOUTH, decision, spot
    from planning.objectives import metrics, score
    records = [spot('a', CENTRE, 0, group='x'), spot('b', CENTRE, 1, group='x'),
               spot('c', SOUTH, 0, group='y'), spot('d', SOUTH, 1, group='y')]
    async def agent(fields):
        return {'fingerprint': fields['fingerprint'], 'variant_id': 'v1',
                'acts': [{'type': 'move_place', 'place': 'b', 'day': 0},
                         {'type': 'move_place', 'place': 'c', 'day': 1}]}
    e = Engine(records, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode,
               matrix_fn=fake_matrix, sun_fn=lambda *a: (360, 1050),
               lodging_fn=fake_lodging, background=False, proposal_agent=agent)
    sid = e.create(decision(['a', 'b', 'c', 'd'], days=2))['id']
    e.act(sid, {'type': 'pick_variant', 'id': 'v1'})
    e.act(sid, {'type': 'set_objective', 'name': 'diverse'})
    for place, day in [('a', 0), ('c', 0), ('b', 1), ('d', 1)]:
        e.act(sid, {'type': 'move_place', 'place': place, 'day': day})
    session, base = e.store.get(sid), e._base[sid]
    baseline = e._turn_current(session, base)
    proposal = {'variant_id': 'v1', 'acts': [{'type': 'move_place', 'place': 'b', 'day': 0},
                                           {'type': 'move_place', 'place': 'c', 'day': 1}]}
    state, draft = e._proposal_trial(base, session, session.state, baseline, proposal)
    _, ctxs = e._ctxs_for(base.trip, e._places_for(session, base), e._home_for(session, base), state)
    before_m, after_m = metrics(ctxs, baseline), metrics(ctxs, draft)
    assert after_m['travel_min'] < before_m['travel_min']
    assert score('diverse', after_m) > score('diverse', before_m)
    before = e.load(sid)
    result = e.recommend(sid)
    assert result['proposal'] == {'status': 'fallback', 'diagnostics': ['objective_worse']}
    assert e.load(sid) == before


def test_decision_locked_role_keeps_its_exact_scheduled_slot():
    from plan_fixtures import CENTRE, decision, spot
    async def agent(fields):
        return {'fingerprint': fields['fingerprint'], 'variant_id': 'v1',
                'acts': [{'type': 'reorder', 'day': 0, 'order': ['c', 'b', 'a']}]}
    records = [spot('a', CENTRE, 0), spot('b', CENTRE, 1), spot('c', CENTRE, 2)]
    e = Engine(records, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode,
               matrix_fn=fake_matrix, sun_fn=lambda *a: (360, 1050),
               lodging_fn=fake_lodging, background=False, proposal_agent=agent)
    sid = e.create(decision(['a', 'b', 'c'], days=1, roles={'a': 'locked'}))['id']
    e.act(sid, {'type': 'pick_variant', 'id': 'v1'})
    e.act(sid, {'type': 'reorder', 'day': 0, 'order': ['a', 'b', 'c']})
    before = e.load(sid)
    result = e.recommend(sid)
    assert result['proposal'] == {'status': 'fallback', 'diagnostics': ['protected_slot_changed']}
    assert e.load(sid) == before
