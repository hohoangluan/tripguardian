"""Regression cases for overload wiring review round 1 (spec sections 6, 7, 11)."""
from dataclasses import replace

import pytest

from plan_fixtures import CENTRE, CFG, all_days, day_ctx, rec
from planning.build import schedule_trip
from planning.roles import meal_kind
from planning.schedule import simulate
from test_planning_layout import framed
from realistic_cases import SERVING

needs_serving = pytest.mark.skipif(not SERVING.exists(), reason="needs data/serving/places.json")


def test_breakfast_venue_takes_breakfast_before_lunch():
    venue = rec('breakfast', *CENTRE, usable=('meal',), group='restaurant', name='Bánh căn',
                hours=all_days('06:30', '16:00'), visit=(90, 90, 90))
    cx = day_ctx([venue], minutes=41, start=480, end=720, start_node='h', end_node='h', extra_nodes=['h'])
    result = simulate(['breakfast'], replace(cx, require_meals=True))
    assert not result.violations
    assert next(i.start for i in result.items if i.kind == 'visit') == 521


def test_last_morning_does_not_require_a_lunch_that_cannot_fit():
    t = framed([rec('temple', *CENTRE, visit=(15, 37, 60))], ['2026-12-12'], ends={0: '12:00'})
    # Breakfast + road + visit + return leave less than the minimum lunch, which validator already handles.
    from plan_fixtures import flat_travel
    travel = flat_travel(list(t.travel.index), minutes=42)
    t = replace(t, travel=travel, ctxs=[replace(cx, travel=travel) for cx in t.ctxs])
    result = schedule_trip(t)
    assert not result.leftover and result.per_day == [['temple']]
    assert not result.violations


def test_hotpot_side_noodles_do_not_make_it_a_breakfast_venue():
    venue = rec('hotpot', *CENTRE, usable=('meal',), group='restaurant', name='Lẩu gà')
    venue['menu'] = {'dishes': [{'name': 'Lẩu gà', 'popular': True}, {'name': 'Bún', 'section': 'Lẩu gà'}]}
    assert meal_kind(venue, CFG) == 'main'


def test_dessert_evidence_overrides_a_generic_restaurant_category():
    venue = rec('dessert', *CENTRE, usable=('meal',), group='restaurant', name='Kem bơ - Chè Huyền')
    venue['menu'] = {'dishes': [{'name': 'Kem bơ'}, {'name': 'Chè nóng'}]}
    assert meal_kind(venue, CFG) == 'light'


@pytest.mark.parametrize('case_id', ['worker_meeting', 'family_kid_nap', 'friends_packed_bar', 'food_tour_8',
                                    'zero_food', 'hotel_breakfast', 'rainy_month', 'add_to_full_day', 'short_by_40'])
@needs_serving
def test_reviewed_case_matches_independent_expectations(case_id):
    from realistic_cases import CASES, run_case
    from realistic_checks import overload_explained
    c = next(c for c in CASES if c['id'] == case_id)
    assert overload_explained(run_case(c)) == []


def test_selected_direction_tray_separates_codes_and_display_text():
    from test_planning_overload_edits import overloaded_started
    e, sid = overloaded_started()
    view = e.load(sid)['view']
    assert view['unplaced']
    reasons = {d['place_id']: d['reason'] for d in view['active_variant']['dropped']}
    for p in view['unplaced']:
        assert p['reason'] == view['state']['chosen_variant']
        assert p['reason_text'] == reasons[p['place_id']]


def test_keep_all_is_not_an_objective():
    from test_planning_engine import started
    from planning.session import ActionError
    e, sid = started()
    with pytest.raises(ActionError, match='objective'):
        e.act(sid, {'type': 'set_objective', 'name': 'keep_all'})


def test_drop_metadata_uses_pace_duration_and_survives_merged_selection():
    from plan_fixtures import decision, prepared, spot
    from planning.variants import plan_cards
    from test_planning_overload_edits import overloaded_started
    recs = [spot(f'p{i}', CENTRE, i % 7, visit=(30, 60, 90), price={'typical_vnd': 10000}) for i in range(8)]
    d = decision([r['id'] for r in recs], days=1, pace='slow', leave_at='21:00')
    trip = prepared(d, recs)
    cards = plan_cards(trip)
    drops = [p for v in cards['variants'] for p in v['dropped_by_plan']]
    assert drops and all(p['saved_min'] == 90 for p in drops)
    for v in cards['variants']:
        assert all(p['reason'] == v['id'] for p in v['dropped_by_plan'])
    e, sid = overloaded_started()
    selected = e.load(sid)['view']['active_variant']
    assert all(p['reason'] == selected['id'] for p in selected['dropped_by_plan'])


def test_tight_clock_shortens_earlier_estimates_before_rejecting_later_stops():
    places = [rec(pid, *CENTRE, visit=(30, 90, 90)) for pid in ('first', 'last')]
    from plan_fixtures import flat_travel
    trip = framed(places, ['2026-12-12'], ends={0: '11:40'})
    travel = flat_travel(list(trip.travel.index), minutes=1)
    trip = replace(trip, travel=travel,
                   ctxs=[replace(cx, travel=travel, day=replace(cx.day, start=540),
                                 meal_skip=frozenset(CFG.meal_windows)) for cx in trip.ctxs])
    result = schedule_trip(trip)
    assert not result.leftover and not result.violations
    visits = [i for r in result.results for i in r.items if i.kind == 'visit']
    assert {i.place_id for i in visits} == {'first', 'last'}
    assert all(i.end - i.start >= 30 for i in visits)
    assert schedule_trip(trip, allow_shrink=False).leftover


def test_a_restaurant_also_selected_as_a_sight_can_use_a_free_stretch():
    venue = rec('view', *CENTRE, usable=('meal', 'experience'), group='restaurant', name='View restaurant')
    cx = day_ctx([venue], start=840, end=1020)
    from planning.roles import takes_meal_slot
    assert not takes_meal_slot(cx.places['view'])
    assert not simulate(['view'], cx).violations
    explicit = replace(cx.places['view'], activity='eating', activity_explicit=True)
    assert takes_meal_slot(explicit)
    photo = replace(cx.places['view'], activity='photography', activity_explicit=True)
    assert not takes_meal_slot(photo)
    assert not simulate(['view'], replace(cx, places={'view': photo})).violations


def test_main_venue_tries_dinner_when_the_lunch_stretch_has_no_room():
    from planning.layout import _Layout
    sights = rec('sight', *CENTRE, visit=(100, 100, 100))
    venue = rec('restaurant', *CENTRE, usable=('meal',), group='restaurant', visit=(90, 90, 90),
                hours=all_days('10:00', '22:00'))
    t = framed([sights, venue], ['2026-12-12'], busy={0: [('12:30', '14:00', 'nap', 'lodging')]})
    day = _Layout(t, t.ctxs).days[0]
    day.put('sight', day.option('sight'))
    opt = day.option('restaurant')
    assert opt is not None and opt[3] == 'dinner'
    result = schedule_trip(t)
    assert not result.leftover and not result.violations
    meal = next(i for r in result.results for i in r.items if i.place_id == 'restaurant' and i.kind == 'visit')
    assert CFG.meal_windows['dinner'][0] <= meal.start <= CFG.meal_windows['dinner'][1]


@needs_serving
def test_fitting_expectation_does_not_call_the_scheduler_as_its_oracle(monkeypatch):
    from realistic_cases import CASES, Run
    from realistic_checks import overload_explained
    import planning.build

    def forbidden(*args, **kwargs):
        raise AssertionError('the scheduler cannot decide the expected overload state')

    monkeypatch.setattr(planning.build, 'schedule_trip', forbidden)
    case = next(c for c in CASES if c['id'] == 'worker_meeting')
    assert overload_explained(Run(case, {})) == []
    assert overload_explained(Run(case, {'overload': {'missing_min': 90}})) == [
        'overload shown for a case expected to fit']


@pytest.mark.parametrize('case_id', ['worker_meeting', 'seven_days', 'family_kid_nap', 'food_tour_8', 'zero_food',
                                    'rainy_month'])
@needs_serving
def test_fitting_places_does_not_waive_the_days_fixed_meals(case_id):
    from realistic_cases import CASES, run_case
    from realistic_checks import meals, overload_explained
    case = next(c for c in CASES if c['id'] == case_id)
    run = run_case(case)
    assert meals(run) == []
    assert overload_explained(run) == []


@pytest.mark.parametrize('source, user_minutes, expected', [('category_default', None, 30),
                                                          ('reviews', None, 90),
                                                          ('category_default', 75, 75)])
def test_breakfast_default_uses_its_slot_estimate_but_preserves_evidence_and_user_duration(source, user_minutes, expected):
    from plan_fixtures import prepared
    venue = rec('breakfast', *CENTRE, usable=('meal',), group='restaurant', name='Bánh căn', visit=(90, 90, 90))
    venue['operation']['visit_minutes']['source'] = source
    trip = framed([venue], ['2026-12-12'])
    if user_minutes is not None:
        decision = trip.decision
        decision['trip_context']['context']['frame']['visit'] = {'restaurant': user_minutes}
        trip = prepared(decision, [venue])
    assert [trip.by_place['breakfast'].visit[key] for key in ('short', 'typical', 'long')] == [expected] * 3


def test_compact_arrival_keeps_breakfast_after_dropping_bags():
    venue = rec('sight', *CENTRE, visit=(30, 120, 120))
    venue['operation']['visit_minutes']['source'] = 'reviews'
    cx = day_ctx([venue], minutes=30, start=480, end=730, start_node='@entry', end_node='h',
                 extra_nodes=['@entry', 'h'])
    cx = replace(cx, home='h', drop_bags=True, compact_estimates=True, require_meals=True)
    result = simulate(['sight'], cx)
    assert not result.violations
    breakfast = next(i for i in result.items if i.kind == 'meal_free' and i.name == 'breakfast')
    assert (breakfast.start, breakfast.end) == (525, 555)
    assert any(i.kind == 'meal_free' and i.name == 'lunch' for i in result.items)


def test_unpin_does_not_search_again_when_opening_hours_already_neutralize_the_pin(monkeypatch):
    import planning.build as build
    venue = rec('sight', *CENTRE, hours=all_days('08:00', '17:00'))
    cx = day_ctx([venue])
    cx = replace(cx, places={'sight': replace(cx.places['sight'], pins=('live_music',))})
    result = simulate(['sight'], cx)
    def forbidden(*args, **kwargs):
        raise AssertionError('removing an ineffective pin must not repeat route search')
    monkeypatch.setattr(build, 'order_day', forbidden)
    assert build._unpin(cx, result, ['sight'], [], None, None) == (cx, result, [])


@pytest.mark.parametrize('group, wanted, pinned', [('nature', False, False), ('nature', True, True),
                                                ('bar', False, True)])
def test_full_frame_does_not_assume_a_sightseeing_visit_attends_live_music(group, wanted, pinned):
    from plan_fixtures import prepared
    venue = rec('sight', *CENTRE, features={'live_music': 'present'}, group=group,
                hours=all_days('00:00', '23:59'))
    trip = framed([venue], ['2026-12-12'])
    if wanted:
        d = trip.decision
        d['trip_context']['soft_weights'] = [{'feature': 'live_music', 'value': 'present', 'weight': 1}]
        trip = prepared(d, [venue])
    assert ('live_music' in trip.by_place['sight'].pins) is pinned


@needs_serving
def test_a_valid_lower_road_order_is_not_lost_to_an_earlier_finish():
    from realistic_cases import CASES, run_case
    from realistic_checks import meals, travel_vs_nn
    run = run_case(next(c for c in CASES if c['id'] == 'seven_days'))
    assert meals(run) == []
    assert travel_vs_nn(run) == []


def compact_clock(places, end=670):
    cx = day_ctx(places, minutes=1, start=540, end=end, start_node='h', end_node='h', extra_nodes=['h'])
    cfg = replace(CFG, buffer_min={**CFG.buffer_min, 'normal': 0},
                  max_consecutive_min={**CFG.max_consecutive_min, 'normal': 10000})
    return replace(cx, cfg=cfg, compact_estimates=True, meal_skip=frozenset(CFG.meal_windows))


def test_compaction_recovers_only_the_minutes_the_day_needs():
    cx = compact_clock([rec(pid, *CENTRE, visit=(30, 90, 90)) for pid in ('first', 'last')])
    result = simulate(['first', 'last'], cx)
    assert not result.violations
    visits = [i for i in result.items if i.kind == 'visit']
    assert sum(i.end - i.start for i in visits) == 127  # 130-minute day less three one-minute legs
    assert all(i.end - i.start >= 30 for i in visits)
    assert any(30 < i.end - i.start < 90 for i in visits)


def test_compaction_cannot_recover_minutes_across_an_opening_wait():
    first = rec('first', *CENTRE, visit=(30, 90, 90))
    last = rec('last', *CENTRE, visit=(30, 90, 90), hours=all_days('13:00', '21:00'))
    cx = compact_clock([first, last], end=810)
    result = simulate(['first', 'last'], cx)
    visit = next(i for i in result.items if i.place_id == 'first' and i.kind == 'visit')
    assert visit.end - visit.start == 90


def test_compaction_preserves_a_user_duration():
    cx = compact_clock([rec(pid, *CENTRE, visit=(30, 90, 90)) for pid in ('first', 'last')])
    fixed = replace(cx.places['first'], visit={'short': 75, 'typical': 75, 'long': 75, 'source': 'user'})
    result = simulate(['first', 'last'], replace(cx, places={**cx.places, 'first': fixed}))
    visit = next(i for i in result.items if i.place_id == 'first' and i.kind == 'visit')
    assert visit.end - visit.start == 75


def test_meal_only_recovery_can_keep_an_earlier_wait_and_fixed_user_visits():
    places = [rec('first', *CENTRE, visit=(30, 30, 30), hours=all_days('10:30', '21:00')),
              rec('last', *CENTRE, visit=(300, 300, 300))]
    cx = compact_clock(places, end=1022)
    cx = replace(cx, meal_skip=frozenset({'breakfast', 'dinner'}), require_meals=True,
                 places={pid: replace(p, visit={**p.visit, 'source': 'user'}) for pid, p in cx.places.items()})
    result = simulate(['first', 'last'], cx)
    assert not result.violations
    assert [(i.place_id, i.end - i.start) for i in result.items if i.kind == 'visit'] == [('first', 30), ('last', 300)]
    assert next(i.end - i.start for i in result.items if i.kind == 'meal_free') == 60
    assert any(i.kind == 'free' and i.end - i.start >= 60 for i in result.items)


def test_meal_recovery_can_fill_an_earlier_wait_and_restore_the_visit_pace():
    first = rec('first', *CENTRE, visit=(30, 30, 30), hours=all_days('12:00', '21:00'))
    last = rec('last', *CENTRE, visit=(30, 90, 90))
    cx = compact_clock([first, last], end=842)
    cx = replace(cx, day=replace(cx.day, start=600), meal_skip=frozenset({'breakfast', 'dinner'}), require_meals=True,
                 places={**cx.places, 'first': replace(cx.places['first'],
                                                     visit={**cx.places['first'].visit, 'source': 'user'})})
    result = simulate(['first', 'last'], cx)
    assert not result.violations
    assert [(i.place_id, i.end - i.start) for i in result.items if i.kind == 'visit'] == [('first', 30), ('last', 90)]
    assert next((i.start, i.end) for i in result.items if i.kind == 'meal_free') == (660, 720)


@pytest.mark.parametrize('dish', ['Phở bò', 'Bánh mì xíu mại', 'Bún bò'])
def test_main_section_breakfast_dishes_keep_the_breakfast_role(dish):
    venue = rec('breakfast', *CENTRE, usable=('meal',), group='restaurant', name='Quán ăn')
    venue['menu'] = {'dishes': [{'name': dish, 'section': 'Món chính'}]}
    assert meal_kind(venue, CFG) == 'breakfast'


@pytest.mark.parametrize('idle_kind', ['free', 'wait', 'gap'])
def test_pace_kept_detects_slack_and_exempts_only_user_duration(monkeypatch, idle_kind):
    import realistic_checks as checks
    from realistic_cases import Run
    venue = rec('sight', *CENTRE, visit=(30, 60, 90))
    monkeypatch.setattr(checks, 'by_id', lambda: {'sight': venue})
    items = [{'kind': 'visit', 'place_id': 'sight', 'name': 'sight', 'start': '09:00', 'end': '09:30'}]
    if idle_kind == 'gap':
        items.append({'kind': 'meal_free', 'start': '11:00', 'end': '12:00'})
    else:
        items.append({'kind': idle_kind, 'start': '09:30', 'end': '10:30'})
    case = {'pace': 'normal', 'frame': {'visit': {}}}
    run = Run(case, {}, days=[{'day': 1, 'items': items}])
    assert checks.pace_kept(run)
    case['frame']['visit']['x'] = 30
    assert checks.pace_kept(run) == []
    case['frame']['visit']['x'] = 75
    assert checks.pace_kept(run)
    run.view['state'] = {'visit_duration_override': {'sight': 30}}
    assert checks.pace_kept(run) == []


def test_nearest_neighbour_keeps_only_ends_actually_placed_by_time_pins(monkeypatch):
    import realistic_checks as checks
    from realistic_cases import Run
    places = [rec('dawn', 0, 1, features={'cloud_hunting': 'present'}),
              rec('near', 0, .01), rec('evening', 0, 1.01, features={'live_music': 'present'})]
    monkeypatch.setattr(checks, 'by_id', lambda: {r['id']: r for r in places})
    items = [{'kind': 'visit', 'place_id': p, 'start': start} for p, start in
             [('dawn', '05:30'), ('near', '10:00'), ('evening', '18:00')]]
    run = Run({}, {}, days=[{'day': 1, 'items': items}], home=(0, 0))
    assert checks.travel_vs_nn(run) == []
    # Evidence of a feature alone does not fix an endpoint when its item is outside that time window.
    items[0]['start'], items[-1]['start'] = '10:00', '12:00'
    assert checks.travel_vs_nn(run)


def test_compaction_restores_minutes_when_shortening_removes_a_pace_rest():
    cx = compact_clock([rec(pid, *CENTRE, visit=(30, 90, 90)) for pid in ('first', 'last')], end=700)
    cx = replace(cx, cfg=replace(cx.cfg, max_consecutive_min={**cx.cfg.max_consecutive_min, 'normal': 150}))
    result = simulate(['first', 'last'], cx)
    assert not result.violations
    visits = [i for i in result.items if i.kind == 'visit']
    # One more visit minute triggers the 15-minute rest and cannot fit; five minutes can be restored after it vanishes.
    assert sum(i.end - i.start for i in visits) == 147


@needs_serving
@pytest.mark.parametrize('case_id', ['twenty_in_2', 'add_to_full_day'])
def test_duration_recovery_keeps_a_feasible_road_saving_order(case_id):
    from realistic_cases import CASES, run_case
    from realistic_checks import frame_kept, meals, pace_kept, travel_vs_nn
    run = run_case(next(c for c in CASES if c['id'] == case_id))
    assert travel_vs_nn(run) == []
    assert meals(run) == []
    assert pace_kept(run) == []
    assert frame_kept(run) == []
