from dataclasses import replace

from plan_fixtures import CENTRE, all_days, day_ctx, rec
from planning.schedule import _SimulationCache, simulate
from planning.validate import validate


def test_unreachable_breakfast_venue_takes_lunch_and_preserves_free_breakfast():
    venue = rec('food', *CENTRE, usable=('meal',), group='restaurant', name='Bánh căn',
                hours=all_days('06:30', '16:00'), visit=(30, 30, 30))
    venue['operation']['visit_minutes']['source'] = 'reviews'
    sight = rec('sight', *CENTRE, visit=(30, 30, 30))
    cx = day_ctx([venue, sight], minutes=20, start=480, end=900,
                 start_node='h', end_node='h', extra_nodes=['h'])
    cx = replace(cx, home='h', require_meals=True, compact_estimates=True)
    cache = _SimulationCache(['food', 'sight'], cx)
    # The same meal order needs different slots when another visit precedes it.
    simulate(['food', 'sight'], cx, _cache=cache)
    result = simulate(['sight', 'food'], cx, _cache=cache)
    assert not validate([cx], [result], [], set(), None, None)
    breakfast = next(i for i in result.items if i.kind == 'meal_free' and i.name == 'breakfast')
    assert (breakfast.start, breakfast.end) == (480, 510)
    meal = next(i for i in result.items if i.kind == 'visit' and i.place_id == 'food')
    assert 660 <= meal.start <= 810
    assert result == simulate(['sight', 'food'], cx)
