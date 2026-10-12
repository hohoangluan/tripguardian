import pytest
from plan_fixtures import CENTRE, CFG, FakeLive, decision, fake_lodging, fake_matrix, no_geocode, spot
from test_planning_engine import started

from planning.engine import Engine
from planning.session import ActionError, State, ActCtx, Store, apply_act


def overloaded_started(preset='low_cost', backup=False):
    records = [spot(f'p{i}', CENTRE, i % 7, price={'typical_vnd': 200000 if i == 7 else 10000},
                    group=f'kind-{i % 4}') for i in range(8)]
    output = decision([r['id'] for r in records], days=1, leave_at='21:00')
    output['feasibility'] = {'status': 'infeasible', 'totals': {'needed': 1000, 'available': 600},
                             'conflicts': [{'check': 'time', 'id': 'time'}]}
    for chosen in output['confirmed']:
        chosen['utility'] = 0.1 if chosen['id'] == 'p7' else 1.0
    if backup:
        records.append(spot('backup', CENTRE, 0, price={'typical_vnd': 10000}))
        output['backup_pool'] = [{'id': 'backup', 'name': 'Backup', 'for_places': ['p0']}]
    engine = Engine(records, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode,
                    matrix_fn=fake_matrix, sun_fn=lambda *a: (360, 1050), lodging_fn=fake_lodging,
                    background=False)
    created = engine.create(output, None)
    variant = next(v for v in created['view']['variants']
                   if v['preset'] == preset and v['status'] == 'available')
    engine.act(created['id'], {'type': 'pick_variant', 'id': variant['id']})
    return engine, created['id']


def visit_ids(view):
    return {item['place_id'] for day in view['itinerary'] for item in day['items']
            if item['kind'] == 'visit'}


def test_restoring_plan_drop_preserves_source_and_protects_membership():
    state = State(plan_dropped=['p'], restored=[])
    ctx = ActCtx({'p': object()}, 1, set(), {}, [[]], set(), set())
    after = apply_act(state, {'type': 'move_place', 'place': 'p', 'day': 0}, ctx)
    assert after.plan_dropped == []
    assert after.restored == ['p']
    assert after.dropped == []


def test_preview_is_read_only_and_token_is_stale_after_edit():
    e, sid = started()
    state = e.store.get(sid).model_dump(mode='json')
    pid = next(item['place_id'] for item in e.load(sid)['view']['itinerary'][0]['items']
               if item['kind'] == 'visit')
    action = {'type': 'drop_place', 'place': pid}
    preview = e.preview_act(sid, action)
    assert e.store.get(sid).model_dump(mode='json') == state
    assert preview['action'] == action
    e.act(sid, {'type': 'lock_slot', 'place': pid})
    with pytest.raises(ActionError, match='preview'):
        e.act(sid, {**action, '_preview_token': preview['token']})


def test_active_profile_is_recomputed_from_the_edited_itinerary():
    e, sid = overloaded_started()
    before = e.load(sid)['view']
    pid = next(iter(visit_ids(before)))

    after = e.act(sid, {'type': 'drop_place', 'place': pid})['view']

    assert after['active_variant']['metrics']['places'] == len(visit_ids(after))
    assert after['active_variant']['kept'] == sorted(visit_ids(after))
    assert pid not in after['active_variant']['kept']


def test_swap_accepts_a_selection_place_dropped_by_the_profile():
    e, sid = overloaded_started()
    before = e.load(sid)['view']
    incoming = before['state']['plan_dropped'][0]
    outgoing = next(pid for pid in visit_ids(before) if pid not in before['state']['locked'])

    preview = e.preview_act(sid, {'type': 'swap', 'place': outgoing, 'with': incoming})

    assert incoming in visit_ids(preview['view'])
    assert outgoing not in visit_ids(preview['view'])
    assert incoming in preview['view']['state']['restored']


def test_reoptimize_keeps_user_choices_and_can_be_applied_from_its_preview():
    e, sid = overloaded_started()
    view = e.load(sid)['view']
    restored = view['state']['plan_dropped'][0]
    e.act(sid, {'type': 'move_place', 'place': restored, 'day': 0})
    current = e.load(sid)['view']
    locked = next(pid for pid in visit_ids(current) if pid != restored)
    e.act(sid, {'type': 'lock_slot', 'place': locked})
    current = e.load(sid)['view']
    user_drop = next(pid for pid in visit_ids(current) if pid not in {restored, locked})
    e.act(sid, {'type': 'drop_place', 'place': user_drop})

    preview = e.preview_act(sid, {'type': 'reoptimize'})
    applied = e.act(sid, {**preview['action'], '_preview_token': preview['token']})['view']

    assert restored in visit_ids(applied)
    assert locked in visit_ids(applied)
    assert user_drop not in visit_ids(applied)
    assert restored in applied['state']['restored']
    assert locked in applied['state']['locked']
    assert user_drop in {drop['place_id'] for drop in applied['state']['dropped']}


def test_reoptimize_replays_from_the_public_action_after_a_restart():
    e, sid = overloaded_started()
    preview = e.preview_act(sid, {'type': 'reoptimize'})
    live = e.act(sid, {**preview['action'], '_preview_token': preview['token']})['view']
    assert e.store.get(sid).log[-1]['action'] == {'type': 'reoptimize'}

    e._base.pop(sid, None)
    e._schedules.pop(sid, None)
    replayed = e.load(sid)['view']

    assert visit_ids(replayed) == visit_ids(live)
    assert replayed['state'] == live['state']


def test_invalid_restore_offers_a_validated_atomic_make_room_action():
    e, sid = overloaded_started()
    invalid = None
    for pid in list(e.load(sid)['view']['state']['plan_dropped']):
        preview = e.preview_act(sid, {'type': 'move_place', 'place': pid, 'day': 0})
        if not preview['confirmable']:
            invalid = preview
            break
        e.act(sid, {**preview['action'], '_preview_token': preview['token']})

    assert invalid is not None
    assert invalid['make_room']
    room = e.preview_act(sid, invalid['make_room'][0])
    assert room['confirmable']
    assert room['action']['type'] == 'make_room'


def test_keep_all_can_be_selected_confirmed_and_replayed_without_a_profile():
    from test_planning_engine import fake_route
    e, sid = overloaded_started()
    e.route_fn = fake_route
    view = e.load(sid)['view']
    assert view['keep_all']['confirmable']
    selected = e.act(sid, {'type': 'pick_variant', 'id': 'keep_all'})['view']
    assert visit_ids(selected) == {c['id'] for c in e.store.get(sid).decision['confirmed']}
    assert selected['active_variant']['preset'] is None
    assert selected['active_variant']['confirmable']
    assert not selected['state']['plan_dropped']
    assert e.confirm(sid)['chosen'] == 'keep_all'
    e.act(sid, {'type': 'undo'})
    e.act(sid, {'type': 'redo'})
    e._base.clear()
    e._schedules.clear()
    assert visit_ids(e.load(sid)['view']) == visit_ids(selected)


def test_invalid_keep_all_is_viewable_but_cannot_be_confirmed():
    from planning.engine import NotConfirmable
    e, sid = overloaded_started()
    e.act(sid, {'type': 'pick_variant', 'id': 'keep_all'})
    view = e.act(sid, {'type': 'set_day_window', 'day': 0, 'start': '09:00', 'end': '10:00'})['view']
    assert view['violations']
    assert not view['active_variant']['confirmable']
    with pytest.raises(NotConfirmable):
        e.confirm(sid)


@pytest.mark.parametrize('preset', ['low_cost', 'diverse', 'least_travel'])
@pytest.mark.parametrize('kind', ['swap', 'add_from_backup'])
def test_backup_preview_apply_metrics_and_replay_preserve_selection_value(preset, kind):
    e, sid = overloaded_started(preset, backup=True)
    before = e.load(sid)['view']
    snapshot = e.store.get(sid).model_dump(mode='json')
    outgoing = sorted(visit_ids(before))[0]
    action = ({'type': 'swap', 'place': outgoing, 'with': 'backup'} if kind == 'swap' else
              {'type': 'add_from_backup', 'place': 'backup', 'day': 0})
    preview = e.preview_act(sid, action)
    assert e.store.get(sid).model_dump(mode='json') == snapshot
    after = e.act(sid, {**action, '_preview_token': preview['token']})['view']
    assert 'backup' in visit_ids(after)
    original_values = {c['id']: c['utility'] for c in snapshot['decision']['confirmed']}
    expected_share = sum(original_values[p] for p in visit_ids(after) if p in original_values) / sum(original_values.values())
    assert after['active_variant']['metrics']['value_share'] == pytest.approx(expected_share)
    assert after['active_variant']['metrics']['utility_source'] == 'selection_and_preferences'
    e.act(sid, {'type': 'undo'})
    assert visit_ids(e.load(sid)['view']) == visit_ids(before)
    e.act(sid, {'type': 'redo'})
    e._base.clear()
    e._schedules.clear()
    replayed = e.load(sid)['view']
    assert replayed['state'] == after['state']
    assert replayed['active_variant']['metrics'] == after['active_variant']['metrics']


def test_make_room_requires_exact_current_preview_and_replays_atomically():
    import copy
    e, sid = overloaded_started()
    view = e.load(sid)['view']
    action = {'type': 'make_room', 'edit': {'type': 'move_place', 'place': view['state']['plan_dropped'][0], 'day': 0},
              'drop_places': [sorted(visit_ids(view))[0]]}
    before = e.store.get(sid).model_dump(mode='json')
    with pytest.raises(ActionError, match='preview'):
        e.act(sid, action)
    preview = e.preview_act(sid, action)
    for change in ('token', 'edit', 'drops'):
        altered = copy.deepcopy(action)
        altered['_preview_token'] = preview['token']
        if change == 'token':
            altered['_preview_token'] = 'wrong'
        elif change == 'edit':
            altered['edit']['day'] = 1
        else:
            altered['drop_places'] = []
        with pytest.raises(ActionError, match='preview'):
            e.act(sid, altered)
        assert e.store.get(sid).model_dump(mode='json') == before
    applied = e.act(sid, {**action, '_preview_token': preview['token']})['view']
    assert not applied['violations']
    assert applied['active_variant']['confirmable']
    e._base.clear()
    e._schedules.clear()
    assert e.load(sid)['view']['state'] == applied['state']
