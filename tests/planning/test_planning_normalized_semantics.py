import copy
from dataclasses import replace
import pytest

from plan_fixtures import CFG, CENTRE, FakeLive, fake_matrix, no_geocode, sample_trip, stay
from planning.engine import Engine
from planning.lodging import from_record, price_cap, rank, sieve
from planning.session import ActionError


def test_lodging_budget_requires_group_dimensions():
    assert price_cap({'budget_vnd': 100000}, 2, CFG) is None
    assert price_cap({'budget_vnd': 100000, 'days': 3, 'people': 2}, 2, CFG) == round(600000 * CFG.lodging_share / 2)


def test_lodging_requirements_apply_eq_and_unknown_policy():
    raw = [from_record(stay('unknown', *CENTRE)), from_record(stay('present', *CENTRE, features={'parking': 'present'}))]
    hard = [{'feature': 'parking', 'op': 'eq', 'value': 'present', 'unknown_policy': 'exclude'}]
    assert [c['id'] for c in sieve(raw, hard, 1)] == ['present']
    hard[0]['unknown_policy'] = 'flag'
    assert sieve(raw, hard, 1)[0]['unverified'] == ['parking']
    hard = [{'feature': 'vegetarian_options', 'op': 'eq', 'value': 'present', 'unknown_policy': 'exclude', 'scope': 'eating'}]
    assert len(sieve(raw, hard, 1)) == 2


@pytest.mark.parametrize('feature,value', [('steep_or_stairs', 'present'), ('kids', 'unsuitable')])
def test_physical_unknown_cannot_be_flagged_through_lodging(feature, value):
    raw = [from_record(stay('unknown', *CENTRE))]
    hard = [{'feature': feature, 'op': 'ne', 'value': value, 'unknown_policy': 'flag', 'scope': 'eating'}]
    assert sieve(raw, hard, 1) == []


def test_person_price_is_not_a_room_night_price():
    r = stay('s', *CENTRE)
    r['operation']['price_per_person'] = {'value': {'min_vnd': 200000}, 'as_of': '2026-01-01'}
    assert from_record(r)['price_vnd'] is None
    assert from_record(r)['rec']['operation']['price_per_person']['value']['min_vnd'] == 200000


def test_rank_uses_explicit_nights_for_group_budget_price_fit():
    from plan_fixtures import decision
    d = decision([], days=3, budget=100000)
    d['trip_context']['context']['nights'] = 3
    c = from_record(stay('s', *CENTRE, price=60000))
    actual = rank([c], d, {}, CFG)[0]['score']
    cap = round(600000 * CFG.lodging_share / 3)
    expected = CFG.lodging_weights['price'] * (1 - .5 * 60000 / cap) + CFG.lodging_weights['rating'] * ((4.5 - 3.5) / 1.5)
    assert actual == round(expected, 4)


def test_preview_semantic_hit_rebinds_decision_and_invalidates_dependencies():
    d, recs = sample_trip()
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix, background=False)
    e.preview(d)
    built = []
    real = e._build_base
    e._build_base = lambda decision: built.append(1) or real(decision)
    cached = next(iter(e._previews.values()))[1]
    changed = copy.deepcopy(d)
    changed.update(decision_log=[{'new': True}], wishlist=['new'], feasibility={'new': True})
    e.preview(changed)
    assert not built
    assert cached.trip.decision == d
    base = e._take_preview(changed)
    assert base.trip.decision == changed
    e.preview(d)
    built.clear()
    e.cfg = replace(CFG, lodging_share=CFG.lodging_share / 2)
    e.preview(d)
    assert built == [1]
    recs[0]['identity']['name'] = 'Changed name'
    e.preview(d)
    assert built == [1, 1]
    e.live_cfg.tz_offset_h = 8
    e.preview(d)
    assert built == [1, 1, 1]
    e.live_dependency_version = 'new weather observation'
    e.preview(d)
    assert built == [1, 1, 1, 1]
    e.conditions_fn = lambda *args: (None, None)
    e.preview(d)
    assert built == [1, 1, 1, 1, 1]
    released = copy.deepcopy(d)
    released['corpus_release'] = {'release_id': 'new-release'}
    e.preview(released)
    assert built == [1, 1, 1, 1, 1, 1]
    tight = copy.deepcopy(released)
    tight['feasibility'] = {'totals': {'available': 1, 'needed': 2}}
    e.preview(tight)
    assert built == [1, 1, 1, 1, 1, 1, 1]


def test_verified_immutable_records_version_controls_cache_invalidation():
    d, recs = sample_trip()
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), immutable_records_version='verified-manifest-hash')
    original = e._decision_key(d)
    assert e._decision_key(d) == original
    e.immutable_records_version = 'new-verified-manifest-hash'
    assert e._decision_key(d) != original


@pytest.mark.parametrize('method', ['create', 'preview'])
@pytest.mark.parametrize('features,op,value', [({'steep_or_stairs': 'present'}, 'ne', 'present'),
                                            ({}, 'ne', 'present'), ({}, 'eq', 'absent')])
def test_selected_corpus_lodging_cannot_bypass_physical_checks(method, features, op, value):
    d, recs = sample_trip()
    d['lodging'] = {'kind': 'corpus', 'id': 'hotel', 'text': 'Hotel', 'lat': CENTRE[0], 'lng': CENTRE[1]}
    d['trip_context']['hard_filters'] = [{'feature': 'steep_or_stairs', 'op': op, 'value': value, 'unknown_policy': 'flag'}]
    e = Engine(recs + [stay('hotel', *CENTRE, features=features)], cfg=CFG, live_cfg=FakeLive(),
               geocode_fn=no_geocode, matrix_fn=fake_matrix, background=False)
    with pytest.raises(ActionError, match='lodging'):
        getattr(e, method)(d)


def test_selected_missing_corpus_lodging_is_rejected():
    d, recs = sample_trip()
    d['lodging'] = {'kind': 'corpus', 'id': 'missing', 'text': 'Hotel', 'lat': CENTRE[0], 'lng': CENTRE[1]}
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), matrix_fn=fake_matrix, background=False)
    with pytest.raises(ActionError, match='lodging'):
        e.preview(d)


def test_selected_corpus_lodging_requires_identity():
    d, recs = sample_trip()
    d['lodging'] = {'kind': 'corpus', 'id': None, 'text': 'Hotel', 'lat': CENTRE[0], 'lng': CENTRE[1]}
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), matrix_fn=fake_matrix, background=False)
    with pytest.raises(ActionError, match='lodging'):
        e.preview(d)


def test_selected_lodging_does_not_apply_eating_requirement():
    d, recs = sample_trip()
    d['confirmed'] = []
    d['lodging'] = {'kind': 'corpus', 'id': 'hotel', 'text': 'Hotel', 'lat': CENTRE[0], 'lng': CENTRE[1]}
    d['trip_context']['hard_filters'] = [{'feature': 'vegetarian_options', 'op': 'eq', 'value': 'present',
                                        'unknown_policy': 'exclude', 'scope': 'eating'}]
    e = Engine(recs + [stay('hotel', *CENTRE)], cfg=CFG, live_cfg=FakeLive(),
               geocode_fn=no_geocode, matrix_fn=fake_matrix, background=False)
    assert e.preview(d)['ok']


def test_confirm_rechecks_selected_lodging_after_hard_requirements_change():
    from planning.engine import NotConfirmable
    d, recs = sample_trip()
    d['confirmed'] = []
    d['lodging'] = {'kind': 'corpus', 'id': 'hotel', 'text': 'Hotel', 'lat': CENTRE[0], 'lng': CENTRE[1]}
    e = Engine(recs + [stay('hotel', *CENTRE)], cfg=CFG, live_cfg=FakeLive(),
               geocode_fn=no_geocode, matrix_fn=fake_matrix, background=False)
    sid = e.create(d)['id']
    e.act(sid, {'type': 'pick_variant', 'id': e.variants(sid)[0]['id']})
    e.store.get(sid).decision['trip_context']['hard_filters'] = [
        {'feature': 'steep_or_stairs', 'op': 'ne', 'value': 'present', 'unknown_policy': 'flag'}]
    with pytest.raises(NotConfirmable, match='lodging'):
        e.confirm(sid)


def test_invalid_selected_lodging_does_not_block_browsing_replacements():
    d, recs = sample_trip()
    d['lodging'] = {'kind': 'corpus', 'id': 'old', 'text': 'Old', 'lat': CENTRE[0], 'lng': CENTRE[1]}
    d['trip_context']['hard_filters'] = [
        {'feature': 'steep_or_stairs', 'op': 'ne', 'value': 'present', 'unknown_policy': 'exclude'}]
    hotels = [stay('old', *CENTRE), stay('safe', *CENTRE, features={'steep_or_stairs': 'absent'})]
    e = Engine(recs + hotels, cfg=CFG, live_cfg=FakeLive(),
               geocode_fn=no_geocode, matrix_fn=fake_matrix, background=False)
    before = copy.deepcopy(d)

    options = e.lodging_options(d)

    assert [c['id'] for c in options['candidates']] == ['safe']
    assert d == before
    with pytest.raises(ActionError, match='lodging'):
        e.preview(d)
