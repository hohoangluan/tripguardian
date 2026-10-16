"""Session activity, meal coverage and stable hotel-anchored plan estimates."""

from dataclasses import replace

import pytest
from plan_fixtures import CFG, CENTRE, FakeLive, all_days, day_ctx, decision, LODGING, fake_matrix, no_geocode, rec

from planning.engine import Engine
from planning.places import build_places
from planning.schedule import simulate
from planning.session import Store
from planning.validate import validate


def test_coffee_record_with_meal_only_coverage_is_not_a_restaurant():
    record = rec('coffee', *CENTRE, group='cafe', usable=('meal', 'backup'))
    places, _ = build_places(decision(['coffee']), {'coffee': record}, CFG)
    assert (places[0].activity, places[0].kind) == ('coffee', 'experience')


def test_explicit_eating_and_sightseeing_override_the_same_venue():
    record = rec('coffee', *CENTRE, group='cafe', usable=('meal', 'backup'))
    for activity, kind in [('eating', 'meal'), ('sightseeing', 'experience')]:
        d = decision(['coffee'])
        d['trip_context']['activities'] = {'coffee': activity}
        places, _ = build_places(d, {'coffee': record}, CFG)
        assert (places[0].activity, places[0].kind) == (activity, kind)


def test_extra_restaurant_cannot_fall_back_to_an_ordinary_visit():
    records = [rec(pid, *CENTRE, group='restaurant', usable=('meal',), hours=all_days('11:00', '17:00'))
               for pid in ['r1', 'r2']]
    cx = day_ctx(records, start=660)
    result = simulate(['r1', 'r2'], cx)
    assert any(v.kind == 'meal_window' for v in result.violations)
    assert any(v.kind == 'meal_window' for v in validate([cx], [result], [], set(), None, None))


def test_meals_cover_breakfast_lunch_and_dinner_even_when_visits_end_early():
    cx = day_ctx([rec('a', *CENTRE)], start=480, end=1260)
    result = simulate(['a'], cx)
    assert {it.name for it in result.items if it.kind == 'meal_free'} == {'breakfast', 'lunch', 'dinner'}
    assert not validate([cx], [result], [], set(), None, None)


def test_departure_day_does_not_get_dinner_outside_its_window():
    result = simulate(['a'], day_ctx([rec('a', *CENTRE)], start=600, end=900))
    assert not any(it.name in {'breakfast', 'dinner'} for it in result.items if it.kind == 'meal_free')
    assert all(it.end <= 900 for it in result.items)


def test_long_visit_reserves_lunch_instead_of_running_through_it():
    cx = day_ctx([rec('a', *CENTRE, visit=(60, 300, 400)), rec('b', *CENTRE)], start=600)
    result = simulate(['a', 'b'], cx)
    assert any(it.kind == 'meal_free' and it.name == 'lunch' for it in result.items)
    assert 'meal_missed:lunch' not in result.notes
    assert result.order == ('a', 'b')
    assert all(it.end - it.start >= cx.places[it.place_id].visit['short']
               for it in result.items if it.kind == 'visit')


def test_slow_coffee_uses_typical_duration_without_a_matching_preference():
    cx = day_ctx([rec('c', *CENTRE, group='cafe', visit=(45, 75, 150))], pace='slow')
    result = simulate(['c'], cx)
    visit = next(it for it in result.items if it.kind == 'visit')
    assert visit.end - visit.start == 60
    preferred = simulate(['c'], replace(cx, prefs={'c': 2}))
    visit = next(it for it in preferred.items if it.kind == 'visit')
    assert visit.end - visit.start == 90


def make_engine():
    records = [rec(f'p{i}', CENTRE[0] + i * .001, CENTRE[1], price={'typical_vnd': 10000}) for i in range(8)]
    d = decision([r['id'] for r in records], days=2, leave_at='21:00')
    d['feasibility'] = {'status': 'partial', 'conflicts': [{'check': 'time'}]}
    e = Engine(records + LODGING, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode,
               matrix_fn=fake_matrix, sun_fn=lambda *a: None, background=False)
    return e, e.create(d)['id']


def test_selecting_the_main_card_keeps_its_exact_timeline_and_metrics():
    e, sid = make_engine()
    e.act(sid, {'type': 'pick_lodging', 'id': 'h1'})
    card = next(v for v in e.load(sid)['view']['variants'] if v['id'] == 'main')
    assert card['status'] == 'available'
    selected = e.act(sid, {'type': 'pick_variant', 'id': card['id']})['view']
    assert selected['itinerary'] == card['itinerary']
    assert selected['active_variant']['metrics'] == card['metrics']
    assert selected['metrics'] == selected['active_variant']['metrics']
    assert card['metrics']['lodging_cost_vnd'] == 300000


def test_picking_profile_does_not_rerun_the_scheduler(monkeypatch):
    e, sid = make_engine()
    card = next(v for v in e.load(sid)['view']['variants'] if v['status'] == 'available')
    monkeypatch.setattr(e, '_rebuild_variant', lambda *a: pytest.fail('offered profile must be reused'))
    e.act(sid, {'type': 'pick_variant', 'id': card['id']})


def test_hotel_first_session_rejects_plan_selection_and_confirmation_without_a_hotel():
    from planning.engine import NotConfirmable
    from planning.session import ActionError
    e, sid = make_engine()
    e.store.get(sid).require_lodging = True
    card = e.variants(sid)[0]
    with pytest.raises(ActionError, match='hotel'):
        e.act(sid, {'type': 'pick_variant', 'id': card['id']})
    with pytest.raises(NotConfirmable, match='hotel'):
        e.confirm(sid)
    e.act(sid, {'type': 'pick_lodging', 'id': 'h1'})
    assert not e.load(sid)['view']['needs_hotel']


def test_selected_hotel_coordinates_do_not_need_another_geocode_lookup():
    e, sid = make_engine()
    e.geocode_fn = lambda text: pytest.fail('the user already picked coordinates')
    view = e.act(sid, {'type': 'set_lodging', 'text': 'Chosen hotel', 'lat': CENTRE[0], 'lng': CENTRE[1]})['view']
    assert view['state']['lodging_point']['lat'] == CENTRE[0]


def test_meal_only_restaurants_are_distributed_between_days_that_can_host_them():
    from planning.build import prepare, schedule_trip
    records = [rec(pid, *CENTRE, group='restaurant', usable=('meal',), hours=all_days('11:00', '17:00'))
               for pid in ['r1', 'r2']]
    trip = prepare(decision(['r1', 'r2']), records, CFG, FakeLive(), no_geocode, fake_matrix, lambda *a: None)
    schedule = schedule_trip(trip)
    assert not schedule.violations
    assert [len(result.order) for result in schedule.results] == [1, 1]


def test_confirmed_cost_counts_the_hotel_exactly_once():
    e, sid = make_engine()
    e.route_fn = lambda *a: None
    e.act(sid, {'type': 'pick_lodging', 'id': 'h1'})
    card = next(v for v in e.variants(sid) if v['status'] == 'available')
    selected = e.act(sid, {'type': 'pick_variant', 'id': card['id']})['view']
    output = e.confirm(sid)
    assert output['cost']['known_vnd'] == selected['metrics']['cost_vnd']
    assert output['cost']['unknown_items'] == selected['metrics']['cost_unknown']



def test_manual_hotel_unknown_cost_is_consistent_on_card_detail_and_confirmation():
    e, sid = make_engine()
    e.route_fn = lambda *a: None
    e.act(sid, {'type': 'set_lodging', 'text': 'Chosen hotel', 'lat': CENTRE[0], 'lng': CENTRE[1]})
    card = next(v for v in e.variants(sid) if v['status'] == 'available')
    selected = e.act(sid, {'type': 'pick_variant', 'id': card['id']})['view']
    output = e.confirm(sid)
    assert card['metrics'] == selected['metrics']
    assert output['cost']['unknown_items'] == selected['metrics']['cost_unknown']


def test_confirmation_uses_the_edited_day_windows():
    e, sid = make_engine()
    e.route_fn = lambda *a: None
    card = next(v for v in e.variants(sid) if v['status'] == 'available')
    e.act(sid, {'type': 'pick_variant', 'id': card['id']})
    e.act(sid, {'type': 'set_day_window', 'day': 0, 'start': '09:00', 'end': '21:00'})
    out = e.confirm(sid)
    assert out['time_budget']['per_day'][0] == {'day': 1, 'from': '09:00', 'to': '21:00', 'minutes': 720}


def test_lunch_only_venue_keeps_lunch_when_another_restaurant_can_serve_dinner():
    from planning.route import order_day
    cx = day_ctx([rec('flexible', *CENTRE, group='restaurant', usable=('meal',), hours=all_days('11:00', '23:00')),
                  rec('lunch_only', *CENTRE, group='restaurant', usable=('meal',), hours=all_days('11:00', '17:00'))])
    result = order_day(['flexible', 'lunch_only'], cx)
    assert not result.violations
    visits = {i.place_id: i for i in result.items if i.kind == 'visit'}
    assert 660 <= visits['lunch_only'].start <= 810
    assert 1050 <= visits['flexible'].start <= 1200


def test_reloading_a_selected_plan_reuses_validation_and_robustness(monkeypatch):
    import planning.engine as engine_module
    e, sid = make_engine()
    card = next(v for v in e.variants(sid) if v['status'] == 'available')
    e.act(sid, {'type': 'pick_variant', 'id': card['id']})
    e.load(sid)
    monkeypatch.setattr(engine_module, 'robustness_of', lambda *a, **kw: pytest.fail('unchanged plan was recomputed'))
    monkeypatch.setattr(engine_module, 'backups_of', lambda *a, **kw: pytest.fail('unchanged backups were recomputed'))
    assert e.load(sid)['view']['active_variant']['metrics'] == card['metrics']
