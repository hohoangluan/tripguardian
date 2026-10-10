import pytest

from plan_fixtures import CFG, FakeLive, fake_lodging, fake_matrix, no_geocode, sample_trip
from planning.engine import Engine
from planning.session import ActionError, Store


def make_engine(root=None):
    decision, records = sample_trip(days=2)
    engine = Engine(records, cfg=CFG, live_cfg=FakeLive(), store=Store(root), geocode_fn=no_geocode,
                    matrix_fn=fake_matrix, sun_fn=lambda *a: (360, 1050), lodging_fn=fake_lodging,
                    background=False)
    sid = engine.create(decision)['id']
    engine.act(sid, {'type': 'pick_variant', 'id': engine.variants(sid)[0]['id']})
    return engine, sid


def visit(engine, sid, pid='c1'):
    return next(item for result in engine._schedules[sid][engine.store.get(sid).position]
                for item in result.items if item.kind == 'visit' and item.place_id == pid)


def test_exact_visit_undo_redo_and_null_fields():
    engine, sid = make_engine()
    engine.act(sid, {'type': 'set_visit', 'place': 'c1', 'start': '10:00', 'duration_min': 45})
    assert (visit(engine, sid).start, visit(engine, sid).end) == (600, 645)
    engine.act(sid, {'type': 'undo'})
    assert not engine.store.get(sid).state.visit_overrides
    engine.act(sid, {'type': 'redo'})
    assert visit(engine, sid).start == 600
    engine.act(sid, {'type': 'set_visit', 'place': 'c1', 'start': None})
    assert engine.store.get(sid).state.visit_overrides['c1'] == {'start': None, 'duration_min': 45}
    engine.act(sid, {'type': 'clear_visit', 'place': 'c1'})
    assert not engine.store.get(sid).state.visit_overrides


@pytest.mark.parametrize('payload', [ {'start': '24:00'}, {'start': '9:00'}, {'start': True},
    {'duration_min': True}, {'duration_min': 1.5}, {'duration_min': '45'}, {'duration_min': 0},
    {'duration_min': 1441}, {'start': '10:00', 'extra': 2}, {}])
def test_invalid_payload_does_not_change_state(payload):
    engine, sid = make_engine()
    before = engine.store.get(sid).model_dump()
    with pytest.raises(ActionError):
        engine.act(sid, {'type': 'set_visit', 'place': 'c1', **payload})
    assert engine.store.get(sid).model_dump() == before


def test_impossible_exact_visit_is_refused_atomically():
    engine, sid = make_engine()
    before = engine.store.get(sid).model_dump()
    with pytest.raises(ActionError) as caught:
        engine.act(sid, {'type': 'set_visit', 'place': 'c1', 'start': '23:59', 'duration_min': 60})
    assert caught.value.say
    assert engine.store.get(sid).model_dump() == before


def test_lock_captures_clock_and_unlock_keeps_override():
    engine, sid = make_engine()
    original = visit(engine, sid)
    engine.act(sid, {'type': 'lock_slot', 'place': 'c1'})
    assert engine.store.get(sid).state.locked_visits['c1'] == {
        'start': original.start, 'duration_min': original.end - original.start}
    engine.act(sid, {'type': 'set_pace', 'level': 'slow'})
    assert visit(engine, sid) == original
    engine.act(sid, {'type': 'unlock', 'place': 'c1'})
    assert not engine.store.get(sid).state.locked_visits


def test_visit_override_survives_rebuild_and_restart(tmp_path):
    engine, sid = make_engine(tmp_path)
    engine.act(sid, {'type': 'set_visit', 'place': 'c1', 'start': '10:00', 'duration_min': 45})
    engine.act(sid, {'type': 'set_pace', 'level': 'slow'})
    assert (visit(engine, sid).start, visit(engine, sid).end) == (600, 645)
    engine._base.clear()
    engine._schedules.clear()
    engine.store = Store(tmp_path)
    engine.load(sid)
    assert (visit(engine, sid).start, visit(engine, sid).end) == (600, 645)


def test_reorder_conflict_is_refused_without_changing_order_or_history():
    engine, sid = make_engine()
    item = visit(engine, sid)
    clock = f'{item.start // 60:02d}:{item.start % 60:02d}'
    engine.act(sid, {'type': 'set_visit', 'place': 'c1', 'start': clock})
    current = engine._schedules[sid][engine.store.get(sid).position]
    day = next(i for i, result in enumerate(current) if 'c1' in result.order)
    order = list(current[day].order)
    order.remove('c1')
    order.append('c1')
    before = engine.store.get(sid).model_dump()
    with pytest.raises(ActionError):
        engine.act(sid, {'type': 'reorder', 'day': day, 'order': order})
    assert engine.store.get(sid).model_dump() == before


def test_edit_only_relayouts_its_day_and_reports_changed_days():
    engine, sid = make_engine()
    before = engine._schedules[sid][engine.store.get(sid).position]
    day = next(i for i, result in enumerate(before) if 'c1' in result.order)
    result = engine.act(sid, {'type': 'set_visit', 'place': 'c1', 'duration_min': 45})
    after = engine._schedules[sid][engine.store.get(sid).position]
    assert result['diff']['scope'] == 'relayout'
    assert result['diff']['changed_days'] == [day + 1]
    assert all(after[i] is before[i] for i in range(len(before)) if i != day)


def test_unlock_preserves_explicit_override():
    engine, sid = make_engine()
    engine.act(sid, {'type': 'set_visit', 'place': 'c1', 'duration_min': 45})
    engine.act(sid, {'type': 'lock_slot', 'place': 'c1'})
    engine.act(sid, {'type': 'unlock', 'place': 'c1'})
    assert engine.store.get(sid).state.visit_overrides['c1']['duration_min'] == 45


def test_independent_validator_detects_tampered_visit():
    from dataclasses import replace
    from planning.validate import validate
    engine, sid = make_engine()
    base = engine._ensure_base(sid)
    session = engine.store.get(sid)
    current = engine._schedules[sid][session.position]
    places = engine._places_for(session, base)
    places['c1'] = replace(places['c1'], requested_start=600, requested_duration=45)
    _, ctxs = engine._ctxs_for(base.trip, places, engine._home_for(session, base), session.state, current)
    kinds = {v.kind for v in validate(ctxs, current, [], set(), None, None)}
    assert {'requested_start', 'requested_duration'} <= kinds


def test_objective_and_variant_preserve_explicit_visit():
    engine, sid = make_engine()
    engine.act(sid, {'type': 'set_visit', 'place': 'c1', 'start': '10:00', 'duration_min': 45})
    engine.act(sid, {'type': 'set_objective', 'name': 'low_cost'})
    assert (visit(engine, sid).start, visit(engine, sid).end) == (600, 645)
    variants = engine.variants(sid)
    engine.act(sid, {'type': 'pick_variant', 'id': variants[-1]['id']})
    assert (visit(engine, sid).start, visit(engine, sid).end) == (600, 645)


def test_locked_visit_survives_restart_and_window_conflict_is_atomic(tmp_path):
    engine, sid = make_engine(tmp_path)
    original = visit(engine, sid)
    engine.act(sid, {'type': 'lock_slot', 'place': 'c1'})
    engine._base.clear()
    engine._schedules.clear()
    engine.store = Store(tmp_path)
    engine.load(sid)
    assert visit(engine, sid) == original
    day = engine.store.get(sid).state.assignment['c1']
    before = engine.store.get(sid).model_dump()
    with pytest.raises(ActionError):
        engine.act(sid, {'type': 'set_day_window', 'day': day, 'start': '14:00', 'end': '18:00'})
    assert engine.store.get(sid).model_dump() == before


def test_null_duration_keeps_explicit_start():
    engine, sid = make_engine()
    engine.act(sid, {'type': 'set_visit', 'place': 'c1', 'start': '10:00', 'duration_min': 45})
    engine.act(sid, {'type': 'set_visit', 'place': 'c1', 'duration_min': None})
    assert engine.store.get(sid).state.visit_overrides['c1'] == {'start': 600, 'duration_min': None}
    assert visit(engine, sid).start == 600


def test_validator_rejects_missing_explicit_visit():
    from dataclasses import replace
    from planning.engine import NotConfirmable
    from planning.validate import validate
    engine, sid = make_engine()
    engine.act(sid, {'type': 'set_visit', 'place': 'c1', 'duration_min': 45})
    session = engine.store.get(sid)
    base = engine._ensure_base(sid)
    current = engine._schedules[sid][session.position]
    missing = [replace(result, items=tuple(item for item in result.items
                                         if item.kind != 'visit' or item.place_id != 'c1'),
                       order=tuple(pid for pid in result.order if pid != 'c1')) for result in current]
    _, ctxs = engine._ctxs_for(base.trip, engine._places_for(session, base),
                               engine._home_for(session, base), session.state, missing)
    assert any(v.kind == 'requested_visit' and v.place_id == 'c1'
               for v in validate(ctxs, missing, [], set(), None, None, required_visits={'c1'}))
    engine._schedules[sid][session.position] = missing
    with pytest.raises(NotConfirmable):
        engine.confirm(sid)


def test_validation_of_one_day_does_not_require_fixed_visits_on_other_days():
    from planning.validate import validate
    engine, sid = make_engine()
    engine.act(sid, {'type': 'set_visit', 'place': 'c1', 'duration_min': 45})
    engine.act(sid, {'type': 'set_visit', 'place': 's1', 'duration_min': 45})
    session = engine.store.get(sid)
    base = engine._ensure_base(sid)
    current = engine._schedules[sid][session.position]
    _, ctxs = engine._ctxs_for(base.trip, engine._places_for(session, base),
                               engine._home_for(session, base), session.state, current)
    for cx, result in zip(ctxs, current):
        assert validate([cx], [result], [], set(), None, None) == []
    engine.act(sid, {'type': 'set_pace', 'level': 'slow'})
    assert visit(engine, sid, 'c1').end - visit(engine, sid, 'c1').start == 45
    assert visit(engine, sid, 's1').end - visit(engine, sid, 's1').start == 45


def test_undo_redo_report_the_days_whose_timeline_changed():
    engine, sid = make_engine()
    before = engine._schedules[sid][engine.store.get(sid).position]
    day = next(i for i, result in enumerate(before) if 'c1' in result.order)
    engine.act(sid, {'type': 'set_visit', 'place': 'c1', 'duration_min': 45})
    assert engine.act(sid, {'type': 'undo'})['diff']['changed_days'] == [day + 1]
    assert engine.act(sid, {'type': 'redo'})['diff']['changed_days'] == [day + 1]


def test_lock_captures_an_unchanged_invalid_timeline_without_making_it_confirmable():
    from dataclasses import replace
    from planning.engine import NotConfirmable
    engine, sid = make_engine()
    session = engine.store.get(sid)
    current = engine._schedules[sid][session.position]
    day = next(i for i, result in enumerate(current) if 'c1' in result.order)
    invalid_visit = replace(visit(engine, sid), start=1439, end=1499)
    current[day] = replace(current[day], items=tuple(invalid_visit if item.kind == 'visit' and item.place_id == 'c1'
                                                  else item for item in current[day].items))
    engine.act(sid, {'type': 'lock_slot', 'place': 'c1'})
    assert visit(engine, sid) == invalid_visit
    assert session.state.locked_visits['c1'] == {'start': 1439, 'duration_min': 60}
    with pytest.raises(NotConfirmable):
        engine.confirm(sid)


@pytest.mark.parametrize('locked', [False, True])
def test_recommendation_preserves_exact_visits_through_restart_and_undo_redo(tmp_path, locked):
    engine, sid = make_engine(tmp_path)
    engine.act(sid, {'type': 'set_visit', 'place': 'c1', 'start': '10:00', 'duration_min': 45})
    if locked:
        engine.act(sid, {'type': 'lock_slot', 'place': 'c1'})
    original = visit(engine, sid)
    async def proposal(fields):
        return {'fingerprint': fields['fingerprint'], 'variant_id': fields['state']['chosen_variant']}
    engine.proposal_agent = proposal
    out = engine.recommend(sid)
    assert out['proposal']['status'] == 'accepted'
    assert visit(engine, sid) == original
    engine._base.clear()
    engine._schedules.clear()
    engine.store = Store(tmp_path)
    assert engine.load(sid)['view']['itinerary'] == out['view']['itinerary']
    assert visit(engine, sid) == original
    engine.act(sid, {'type': 'undo'})
    assert visit(engine, sid) == original
    engine.act(sid, {'type': 'redo'})
    assert visit(engine, sid) == original


def test_a_conflicting_recommendation_keeps_fixed_visits_and_history():
    engine, sid = make_engine()
    item = visit(engine, sid)
    engine.act(sid, {'type': 'set_visit', 'place': 'c1', 'start': f'{item.start // 60:02d}:{item.start % 60:02d}'})
    current = engine._schedules[sid][engine.store.get(sid).position]
    day = next(i for i, result in enumerate(current) if 'c1' in result.order)
    order = [pid for pid in current[day].order if pid != 'c1'] + ['c1']
    async def proposal(fields):
        return {'fingerprint': fields['fingerprint'], 'variant_id': fields['state']['chosen_variant'],
                'acts': [{'type': 'reorder', 'day': day, 'order': order}]}
    engine.proposal_agent = proposal
    before = engine.store.get(sid).model_dump()
    assert engine.recommend(sid)['proposal']['status'] == 'fallback'
    assert engine.store.get(sid).model_dump() == before


def test_legacy_state_defaults_visit_maps_to_empty():
    from planning.session import State
    state = State.model_validate({'chosen_variant': 'v1', 'locked': ['c1'], 'assignment': {'c1': 0}})
    assert state.visit_overrides == state.locked_visits == {}
