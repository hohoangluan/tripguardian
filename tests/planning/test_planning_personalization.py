from dataclasses import replace

from plan_fixtures import day_ctx, rec
from planning.schedule import simulate
from planning.personalization import duration, suitability


def test_slow_known_activity_keeps_baseline_without_interest():
    cx = day_ctx([rec('a', 11, 108, group='cafe')], pace='slow')
    assert duration(cx.places['a'], cx.cfg, cx.pace) == 60
    assert duration(replace(cx.places['a'], rec={**cx.places['a'].rec, 'identity': {'category_group': 'x'}}), cx.cfg, cx.pace) == 90


def test_matching_activity_interest_extends_within_estimate():
    cx = day_ctx([rec('a', 11, 108, group='cafe', features={'scenic_view': 'present'})])
    p = cx.places['a']
    assert duration(p, cx.cfg, cx.pace, [{'feature': 'scenic_view', 'value': 'present', 'weight': 1}]) == 90
    assert duration(p, cx.cfg, cx.pace, [{'feature': 'scenic_view', 'value': 'absent', 'weight': 1}]) == 60


def test_contextual_time_is_soft_and_not_probability():
    cx = day_ctx([rec('a', 11, 108, group='cafe', features={'scenic_view': 'present'})])
    p = cx.places['a']
    p.rec['experience']['scenic_view']['by_context'] = {'time_of_day=afternoon': {'present': 100}}
    weights = [{'feature': 'scenic_view', 'value': 'present', 'weight': 1}]
    assert suitability(p, 900, cx.cfg, weights) > suitability(p, 480, cx.cfg, weights)
    cx = replace(cx, soft_weights=weights, day=replace(cx.day, end=600))
    result = simulate(['a'], cx)
    assert not result.violations


def test_explicit_wall_clock_duration_and_start_override_pin():
    cx = day_ctx([rec('a', 11, 108, features={'sunset_view': 'present'})], sun=(360, 1050))
    p = replace(cx.places['a'], requested_start=600, requested_duration=75)
    result = simulate(['a'], replace(cx, places={'a': p}))
    visit = next(i for i in result.items if i.kind == 'visit')
    assert (visit.start, visit.end) == (600, 675)


def test_explicit_start_cannot_override_opening_hours():
    cx = day_ctx([rec('a', 11, 108)])
    p = replace(cx.places['a'], requested_start=400, requested_duration=60)
    assert simulate(['a'], replace(cx, places={'a': p})).violations


def test_relocates_full_visit_before_shrinking(monkeypatch):
    from plan_fixtures import decision, prepared
    from planning.build import schedule_trip
    d = decision(['a'], days=2, checkin_at='20:00')
    trip = prepared(d, [rec('a', 11, 108, visit=(30, 120, 150))])
    monkeypatch.setattr('planning.build.assign_days', lambda clusters, ctxs: ([['a'], []], None))
    result = schedule_trip(trip)
    visits = [(k, it) for k, r in enumerate(result.results) for it in r.items if it.kind == 'visit']
    assert visits[0][0] == 1
    assert visits[0][1].end - visits[0][1].start == 120


def test_context_preference_guides_time_without_inventing_context_evidence():
    cx = day_ctx([rec('a', 11, 108, group='cafe', features={'scenic_view': 'present'})])
    p = cx.places['a']
    weights = [{'feature': 'scenic_view', 'value': 'present', 'weight': 1,
                'context': {'time_of_day': 'afternoon'}}]
    assert suitability(p, 900, cx.cfg, weights) > suitability(p, 480, cx.cfg, weights)


def test_evidence_changes_feasible_time_and_counts_do_not_scale_score():
    cx = day_ctx([rec('a', 11, 108, group='cafe', features={'scenic_view': 'present'})], start=825)
    cx.places['a'].rec['experience']['scenic_view']['by_context'] = {'time_of_day=afternoon': {'present': 1}}
    cx = replace(cx, soft_weights=[{'feature': 'scenic_view', 'value': 'present', 'weight': 1}])
    score = suitability(cx.places['a'], 900, cx.cfg, cx.soft_weights)
    cx.places['a'].rec['experience']['scenic_view']['by_context']['time_of_day=afternoon']['present'] = 100
    assert suitability(cx.places['a'], 900, cx.cfg, cx.soft_weights) == score
    result = simulate(['a'], cx)
    assert next(it for it in result.items if it.kind == 'visit').start == 840


def test_fixed_duration_is_not_extended_by_busy_day_or_shrunk():
    from planning.conditions import DayCond
    cx = day_ctx([rec('a', 11, 108, features={'crowd': 'high'})], end=540)
    p = replace(cx.places['a'], requested_duration=75)
    result = simulate(['a'], replace(cx, places={'a': p}, cond=DayCond(crowd='busy')))
    visit = next(i for i in result.items if i.kind == 'visit')
    assert visit.end - visit.start == 75
    assert result.violations


def test_requested_start_cannot_pull_a_later_day_earlier():
    from planning.build import pull_early
    cx = day_ctx([rec('a', 11, 108)])
    p = replace(cx.places['a'], requested_start=420)
    cx = replace(cx, places={'a': p}, day=replace(cx.day, index=1))
    adjusted, pid = pull_early(cx, ['a'], cx.places, cx.travel)
    assert adjusted.day.start == 480
    assert pid is None


def test_facility_preferences_and_uncertain_activity_do_not_extend_visit():
    cx = day_ctx([rec('a', 11, 108, group='cafe', features={'cash_only': 'absent', 'scenic_view': 'present'})])
    p = cx.places['a']
    assert duration(p, cx.cfg, cx.pace, [{'feature': 'cash_only', 'value': 'absent', 'weight': 1}]) == 60
    p.rec['experience']['scenic_view']['status'] = 'UNCERTAIN'
    assert duration(p, cx.cfg, cx.pace, [{'feature': 'scenic_view', 'value': 'present', 'weight': 1}]) == 60


def test_conflicting_context_and_uncertain_evidence_do_not_improve_time():
    cx = day_ctx([rec('a', 11, 108, group='cafe', features={'food_quality': 'good'})])
    p = cx.places['a']
    weights = [{'feature': 'food_quality', 'value': 'good', 'weight': 1}]
    p.rec['experience']['food_quality']['by_context'] = {'time_of_day=afternoon': {'good': 1, 'poor': 5}}
    assert suitability(p, 900, cx.cfg, weights) == 0.1
    p.rec['experience']['food_quality']['by_context'] = {'time_of_day=afternoon': {'good': 5}}
    p.rec['experience']['food_quality']['status'] = 'UNCERTAIN'
    assert suitability(p, 900, cx.cfg, weights) == 0.1


def test_contextual_interest_uses_served_context_instead_of_global_value():
    cx = day_ctx([rec('a', 11, 108, group='cafe', features={'food_quality': 'good'})])
    cx = replace(cx, cfg=replace(cx.cfg, personalization={**cx.cfg.personalization,
                                                       'interest_features': ['food_quality']}))
    p = cx.places['a']
    evidence = p.rec['experience']['food_quality']
    weights = [{'feature': 'food_quality', 'value': 'good', 'weight': 1,
                'context': {'time_of_day': 'afternoon'}}]
    evidence['by_context'] = {'time_of_day=afternoon': {'good': 1, 'poor': 5}}
    assert duration(p, cx.cfg, cx.pace, weights) == 60
    evidence['value'] = 'poor'
    evidence['by_context'] = {'time_of_day=afternoon': {'good': 5, 'poor': 1}}
    assert duration(p, cx.cfg, cx.pace, weights) == 90


def test_explicit_time_preference_cannot_override_conflicting_context_evidence():
    cx = day_ctx([rec('a', 11, 108, group='cafe', features={'food_quality': 'good'})])
    p = cx.places['a']
    p.rec['experience']['food_quality']['by_context'] = {
        'time_of_day=afternoon': {'good': 1, 'poor': 5}}
    weights = [{'feature': 'food_quality', 'value': 'good', 'weight': 1,
                'context': {'time_of_day': 'afternoon'}}]
    assert suitability(p, 900, cx.cfg, weights) == 0.1


def test_relocates_to_an_earlier_spare_day_before_shrinking(monkeypatch):
    from plan_fixtures import decision, prepared
    from planning.build import schedule_trip
    d = decision(['a'], days=2, checkout_at='09:00')
    trip = prepared(d, [rec('a', 11, 108, visit=(30, 120, 150))])
    monkeypatch.setattr('planning.build.assign_days', lambda clusters, ctxs: ([[], ['a']], None))
    result = schedule_trip(trip)
    visits = [(k, it) for k, r in enumerate(result.results) for it in r.items if it.kind == 'visit']
    assert visits[0][0] == 0
    assert visits[0][1].end - visits[0][1].start == 120


def test_day_feasibility_includes_queue_time_for_automatic_visits():
    from plan_fixtures import all_days
    from planning.conditions import DayCond
    from planning.days import can_start
    cx = day_ctx([rec('a', 11, 108, hours=all_days('08:00', '09:00'),
                      visit=(60, 60, 60), features={'crowd': 'high'})])
    cx = replace(cx, cond=DayCond(crowd='busy'))
    assert not can_start(cx.places['a'], cx)
    assert simulate(['a'], cx).violations
    p = replace(cx.places['a'], requested_duration=60)
    fixed = replace(cx, places={'a': p})
    assert can_start(p, fixed)
    assert not simulate(['a'], fixed).violations
