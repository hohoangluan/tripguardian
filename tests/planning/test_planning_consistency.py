"""Regression coverage for edited drafts, lodging coordinates and meal validation."""

import copy
from dataclasses import replace

import pytest
from plan_fixtures import CFG, CENTRE, FakeLive, all_days, day_ctx, decision, LODGING, fake_matrix, no_geocode, rec, spot, stay

from planning import Engine
from planning.schedule import simulate
from planning.session import ActionError, Store
from planning.validate import validate


def make_engine(d=None, records=None):
    records = records or [rec(f'p{i}', CENTRE[0] + i * .001, CENTRE[1], price={'typical_vnd': 10000})
                          for i in range(8)]
    d = d or decision([r['id'] for r in records], days=2, leave_at='21:00')
    d['feasibility'] = {'status': 'partial', 'conflicts': [{'check': 'time'}]}
    e = Engine(records + LODGING, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode,
               matrix_fn=fake_matrix, sun_fn=lambda *a: None, route_fn=lambda *a: None, background=False)
    return e, e.create(d)['id']


def pick(e, sid):
    card = next(v for v in e.variants(sid) if v['status'] == 'available')
    view = e.act(sid, {'type': 'pick_variant', 'id': card['id']})['view']
    return card, view


def test_booked_hotel_has_identical_card_and_selection_metrics():
    d = decision([f'p{i}' for i in range(8)], days=2, leave_at='21:00')
    d['trip_context']['context'].update(lodging_booked='yes', lodging={
        'text': 'Booked hotel', 'lat': CENTRE[0], 'lng': CENTRE[1]})
    e, sid = make_engine(d)
    card, view = pick(e, sid)
    assert card['metrics'] == view['metrics']
    assert card['lodging'] == view['active_variant']['lodging']


def test_pace_edited_card_is_the_draft_selected_without_another_rebuild(monkeypatch):
    e, sid = make_engine()
    e.act(sid, {'type': 'pick_lodging', 'id': 'h1'})
    pick(e, sid)
    e.act(sid, {'type': 'set_pace', 'level': 'packed'})
    card = next(v for v in e.variants(sid) if v['status'] == 'available')
    monkeypatch.setattr(e, '_rebuild_variant', lambda *a: pytest.fail('draft already computed'))
    view = e.act(sid, {'type': 'pick_variant', 'id': card['id']})['view']
    assert card['metrics'] == view['metrics']
    assert card['itinerary'] == view['itinerary']


def test_same_hotel_name_at_new_coordinates_changes_travel_and_supports_undo():
    e, sid = make_engine()
    action = {'type': 'set_lodging', 'text': 'Manual hotel', 'lat': CENTRE[0] + .03, 'lng': CENTRE[1]}
    e.act(sid, action)
    _, before = pick(e, sid)
    after = e.act(sid, {**action, 'lat': CENTRE[0] + .07})['view']
    assert after['metrics']['travel_min'] > before['metrics']['travel_min']
    undone = e.act(sid, {'type': 'undo'})['view']
    assert undone['itinerary'] == before['itinerary']
    assert undone['metrics'] == before['metrics']


def test_manual_hotel_is_in_the_confirmed_route():
    e, sid = make_engine()
    hotel = (CENTRE[0] + .03, CENTRE[1])
    e.act(sid, {'type': 'set_lodging', 'text': 'Manual hotel', 'lat': hotel[0], 'lng': hotel[1]})
    pick(e, sid)
    routes = []
    e.route_fn = lambda points, *a: routes.append(points)
    e.confirm(sid)
    assert routes and all(points[0] == hotel and points[-1] == hotel for points in routes)


def test_reanchored_cards_cannot_offer_a_closed_anchor():
    records = [rec('early', *CENTRE, hours=all_days('08:00', '09:00'), visit=(30, 45, 60))]
    d = decision(['early'], days=1, roles={'early': 'anchor'}, leave_at='21:00')
    e, sid = make_engine(d, records)
    view = e.act(sid, {'type': 'set_lodging', 'text': 'Far hotel', 'lat': CENTRE[0] + .2, 'lng': CENTRE[1]})['view']
    assert all(v['status'] == 'unavailable' for v in view['variants'])
    assert any(v['kind'] == 'hours' for card in view['variants'] for v in card['violations'])


def test_lodging_recomposes_overloaded_drafts_and_preserves_the_selection_on_replay():
    records = [spot(f'p{i}', CENTRE, i % 3, price={'typical_vnd': 10000}) for i in range(16)]
    output = decision([r['id'] for r in records])
    engine, sid = make_engine(output, records)
    original = copy.deepcopy(engine.store.get(sid).decision)
    before = engine.load(sid)['view']['variants']
    action = {'type': 'set_lodging', 'text': 'Chosen hotel', 'lat': 11.94, 'lng': 108.45}

    after = engine.act(sid, action)['view']
    available = [v for v in after['variants'] if v['confirmable']]

    assert available, [(v['preset'], v['violations']) for v in after['variants']]
    assert engine.store.get(sid).decision == original
    card = available[0]
    selected = engine.act(sid, {'type': 'pick_variant', 'id': card['id']})['view']
    assert selected['itinerary'] == card['itinerary']
    assert selected['metrics'] == card['metrics']
    assert selected['active_variant']['confirmable'] and not selected['violations']
    engine._base.clear()
    engine._schedules.clear()
    replayed = engine.load(sid)['view']
    assert replayed['itinerary'] == selected['itinerary']
    assert replayed['metrics'] == selected['metrics']
    assert engine.store.get(sid).decision == original
    engine.act(sid, {'type': 'undo'})
    undone = engine.act(sid, {'type': 'undo'})['view']
    assert undone['variants'] == before


def test_validator_detects_missing_meals_in_an_active_day():
    cx = replace(day_ctx([rec('a', *CENTRE)]), require_meals=True)
    result = simulate(['a'], cx)
    stripped = replace(result, items=tuple(it for it in result.items if it.kind != 'meal_free'))
    assert any(v.kind == 'meal_missing' for v in validate([cx], [stripped], [], set(), None, None))


@pytest.mark.parametrize('edit', ['lock_slot', 'move_place'])
def test_reanchored_profiles_preserve_protected_places_and_their_days(edit):
    records = [spot(f'p{i}', CENTRE, i % 3, price={'typical_vnd': 10000}) for i in range(16)]
    engine, sid = make_engine(decision([r['id'] for r in records], leave_at='14:30'), records)   # a short last day keeps the load tight
    selected = engine.act(sid, {'type': 'pick_variant', 'id': engine.variants(sid)[0]['id']})['view']
    day = next(i for i, d in enumerate(selected['itinerary'])
               if any(it.get('place_id') == 'p13' and it['kind'] == 'visit' for it in d['items']))
    action = {'type': edit, 'place': 'p13'}
    if edit == 'move_place':
        action['day'] = day
    engine.act(sid, action)
    view = engine.act(sid, {'type': 'set_lodging', 'text': 'Chosen hotel', 'lat': 11.94, 'lng': 108.45})['view']
    card = next(v for v in view['variants'] if v['id'] == selected['state']['chosen_variant'])

    assert 'p13' in card['kept']
    assert any(it.get('place_id') == 'p13' and it['kind'] == 'visit' for it in card['itinerary'][day]['items'])
    # The layout fills a day only up to its free minutes (layout.py), so the reanchored card is no longer overloaded
    # here; the user extends the default last-day window, and the protected place must still survive switching.
    for changed_day in range(len(view['itinerary'])):
        view = engine.act(sid, {'type': 'set_day_window', 'day': changed_day, 'start': '08:00', 'end': '21:00'})['view']
    card = next(v for v in view['variants'] if v['id'] == selected['state']['chosen_variant'])
    assert card['confirmable'], card['violations']
    after = engine.act(sid, {'type': 'pick_variant', 'id': card['id']})['view']
    assert any(it.get('place_id') == 'p13' and it['kind'] == 'visit' for it in after['itinerary'][day]['items'])
    assert 'p13' not in after['state']['plan_dropped']
    assert after['active_variant']['confirmable'] and not after['violations']
    engine._base.clear()
    engine._schedules.clear()
    replayed = engine.load(sid)['view']
    assert replayed['itinerary'] == after['itinerary']
    assert replayed['state'] == after['state']


def test_arrival_after_breakfast_is_not_reported_as_a_missing_breakfast():
    result = simulate(['a'], day_ctx([rec('a', *CENTRE)], start=600))
    assert 'meal_missed:breakfast' not in result.notes


def test_manual_duration_requires_preview_and_is_undoable():
    e, sid = make_engine()
    _, before = pick(e, sid)
    pid = next(it['place_id'] for day in before['itinerary'] for it in day['items'] if it['kind'] == 'visit')
    action = {'type': 'set_visit_duration', 'place': pid, 'minutes': 30}
    with pytest.raises(ActionError, match='preview'):
        e.act(sid, action)
    preview = e.preview_act(sid, action)
    assert e.load(sid)['view']['itinerary'] == before['itinerary']
    edited = e.act(sid, {**action, '_preview_token': preview['token']})['view']
    visit = next(it for day in edited['itinerary'] for it in day['items']
                 if it['kind'] == 'visit' and it['place_id'] == pid)
    assert visit['end'] != next(it['end'] for day in before['itinerary'] for it in day['items']
                              if it['kind'] == 'visit' and it['place_id'] == pid)
    assert e.act(sid, {'type': 'undo'})['view']['itinerary'] == before['itinerary']


def test_duration_fallbacks_follow_activity_and_trip_choices():
    from planning.build import prepare
    from planning.traits import visit_minutes
    records = [rec('coffee', *CENTRE, group='cafe', visit=(45, 75, 150)),
               rec('meal', *CENTRE, group='restaurant', usable=('meal',), visit=(45, 75, 120)),
               rec('view', *CENTRE, group='nature', visit=(60, 120, 240))]
    d = decision(['coffee', 'meal', 'view'])
    trip = prepare(d, records, CFG, FakeLive(), no_geocode, fake_matrix, lambda *a: None)
    assert visit_minutes(trip.by_place['coffee'], CFG, 'normal') == 60
    assert visit_minutes(trip.by_place['meal'], CFG, 'normal') == 90
    assert [visit_minutes(trip.by_place['view'], CFG, pace) for pace in ('packed', 'normal', 'slow')] == [30, 60, 150]
    d['trip_context']['activities'] = {'view': 'photography'}
    trip = prepare(d, records, CFG, FakeLive(), no_geocode, fake_matrix, lambda *a: None)
    assert visit_minutes(trip.by_place['view'], CFG, 'normal') == 150


def test_duration_policy_preserves_place_specific_evidence():
    from planning.places import build_places
    from planning.traits import visit_minutes
    record = rec('view', *CENTRE, group='nature', visit=(60, 120, 240))
    record['operation']['visit_minutes']['source'] = 'reviews'
    places, _ = build_places(decision(['view']), {'view': record}, CFG)
    assert visit_minutes(places[0], CFG, 'normal') == 120


def test_day_load_uses_the_same_coffee_duration_and_only_unclaimed_meals():
    from planning.days import day_load, load_of
    cx = day_ctx([rec('coffee', *CENTRE, group='cafe', visit=(45, 75, 150))], pace='slow')
    result = simulate(['coffee'], cx)
    visit = next(it.end-it.start for it in result.items if it.kind == 'visit')
    assert load_of(['coffee'], cx.places, CFG, 'slow') == visit + CFG.intra_leg_min
    assert day_load(['coffee'], cx.places, CFG, 'slow') == visit + CFG.intra_leg_min + CFG.buffer_min['slow'] + 210


def test_three_flexible_restaurants_fill_distinct_meals_in_clock_order():
    records = [rec(pid, *CENTRE, group='restaurant', hours=all_days('07:00', '23:00'))
               for pid in ('a', 'b', 'c')]
    cx = replace(day_ctx(records), require_meals=True)
    result = simulate(['a', 'b', 'c'], cx)
    meals = [it for it in result.items if it.kind == 'visit']
    assert [it.end - it.start for it in meals] == [90, 90, 90]
    assert all(CFG.meal_windows[name][0] <= it.start <= CFG.meal_windows[name][1]
               for name, it in zip(('breakfast', 'lunch', 'dinner'), meals))
    assert not validate([cx], [result], [], set(), None, None)


def test_hotel_budget_refresh_preserves_manual_hotel_and_undo_routes():
    e, sid = make_engine()
    e.act(sid, {'type': 'set_lodging', 'text': 'Manual', 'lat': CENTRE[0] + .02, 'lng': CENTRE[1]})
    _, before = pick(e, sid)
    e.records = e.records + [stay('new-hotel', CENTRE[0] + .001, CENTRE[1], price=300000)]  # found by the wider search
    after = e.act(sid, {'type': 'set_lodging_budget', 'max_per_night': 900000})['view']
    assert after['itinerary'] == before['itinerary']
    assert after['metrics'] == before['metrics']
    assert e.act(sid, {'type': 'undo'})['view']['itinerary'] == before['itinerary']


def test_local_and_lock_edits_do_not_rebuild_alternative_trips(monkeypatch):
    e, sid = make_engine()
    e.act(sid, {'type': 'pick_lodging', 'id': 'h1'})
    _, before = pick(e, sid)
    pid = next(it['place_id'] for day in before['itinerary'] for it in day['items'] if it['kind'] == 'visit')
    monkeypatch.setattr(e, '_rebuild_variant', lambda *a: pytest.fail('local edit rebuilt the trip'))
    locked = e.act(sid, {'type': 'lock_slot', 'place': pid})['view']
    assert locked['itinerary'] == before['itinerary']
    e.act(sid, {'type': 'unlock', 'place': pid})
    e.act(sid, {'type': 'drop_place', 'place': pid})


def test_matching_query_preferences_select_deeper_visit_without_question():
    from planning.build import prepare, schedule_trip
    records = [rec('garden', *CENTRE, group='garden_farm', features={'photo_spot': 'present'})]
    output = decision(['garden'], days=1, leave_at='21:00')
    output['trip_context']['soft_weights'] = [{'feature': 'photo_spot', 'value': 'present', 'weight': 2}]
    trip = prepare(output, records, CFG, FakeLive(), no_geocode, fake_matrix, lambda *a: None)
    result = schedule_trip(trip)
    assert not result.violations
    visit = next(it for it in result.results[0].items if it.kind == 'visit')
    assert visit.end - visit.start == 150
    output['trip_context']['pace']['level'] = 'packed'
    trip = prepare(output, records, CFG, FakeLive(), no_geocode, fake_matrix, lambda *a: None)
    visit = next(it for it in schedule_trip(trip).results[0].items if it.kind == 'visit')
    assert visit.end - visit.start == 30
