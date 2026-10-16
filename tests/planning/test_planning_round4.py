"""Round-4 regressions: experience pins, duration policy and breakfast evidence."""
from dataclasses import replace

import pytest

from plan_fixtures import CENTRE, CFG, day_ctx, rec
from planning.roles import meal_kind
from planning.schedule import _SimulationCache, simulate
from planning.traits import visit_minutes


@pytest.mark.parametrize('section', ['Bữa sáng', 'Breakfast (Điểm Tâm)', 'Bữa Sáng An Lành', 'Điểm Tâm',
                                     'Ăn Sáng', 'Khác', 'Món Ăn', 'Thực đơn', 'Menu', 'Món chính', None])
def test_breakfast_sections_and_generic_menu_keep_breakfast_dishes(section):
    r = rec('food', *CENTRE, usable=('meal',), group='restaurant', name='Quán ăn')
    r['menu'] = {'dishes': [{'name': 'Hủ tiếu', 'section': section}]}
    assert meal_kind(r, CFG) == 'breakfast'


def test_breakfast_named_section_does_not_require_a_known_dish_name():
    r = rec('food', *CENTRE, usable=('meal',), group='restaurant')
    r['menu'] = {'dishes': [{'name': 'Điểm tâm đặc biệt', 'section': 'Bữa sáng'}]}
    assert meal_kind(r, CFG) == 'breakfast'


@pytest.mark.parametrize('name', ['Tiệm Bánh Cuốn Thủ Công Ồh Ngon Quá', 'Tiệm Bánh Canh 2 Chàng'])
def test_noodle_or_rice_roll_shop_is_not_a_bakery(name):
    r = rec('food', *CENTRE, usable=('meal',), group='restaurant', name=name)
    assert meal_kind(r, CFG) == 'breakfast'


@pytest.mark.parametrize('group,activity', [('cafe', 'coffee'), ('restaurant', 'eating'), ('x', 'sightseeing')])
@pytest.mark.parametrize('preferred', [False, True])
def test_frame_and_cache_use_traits_duration(group, activity, preferred):
    r = rec('place', *CENTRE, visit=(30, 60, 120), group=group)
    cx = day_ctx([r], pace='slow', prefs={'place': 2 if preferred else 0})
    p = replace(cx.places['place'], activity=activity)
    cx = replace(cx, places={'place': p})
    framed = replace(cx, compact_estimates=True)
    expected = visit_minutes(p, CFG, cx.pace, cx.prefs)
    for context in (cx, framed):
        for cache in (None, _SimulationCache(['place'], context)):
            result = simulate(['place'], context, _cache=cache)
            visit = next(i for i in result.items if i.kind == 'visit')
            assert visit.end - visit.start == expected


def test_simulate_does_not_release_pin_to_keep_pace_on_a_slack_day():
    # The fixed order leaves morning slack then too little time after sunset for both visits.
    places = [rec('sunset', *CENTRE, visit=(30, 90, 90), features={'sunset_view': 'present'}),
              rec('later', *CENTRE, visit=(30, 120, 120))]
    cx = replace(day_ctx(places, start=480, end=1140, sun=(360, 1050)), compact_estimates=True)
    result = simulate(['sunset', 'later'], cx)
    assert not result.unpinned
    visit = next(i for i in result.items if i.place_id == 'sunset' and i.kind == 'visit')
    assert 975 <= visit.start <= 1030
