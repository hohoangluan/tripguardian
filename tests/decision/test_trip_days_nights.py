from types import SimpleNamespace

import pytest

from decision.trip_days import trip_days
from decision.geo import to_min

CFG = SimpleNamespace(default_days=2, day_start="08:00", day_end="21:00", leave_at="15:00")


def ctx(**kw):
    base = dict(days=3, nights=None, start_date=None, checkin_at=None, checkout_at=None, day_end=None)
    return SimpleNamespace(**{**base, **kw})


@pytest.mark.parametrize("days, nights, last_end", [
    (3, 2, "15:00"),    # leaves on the last day: the default departure cuts it
    (3, None, "15:00"),  # only days said: days - 1 nights
    (3, 3, "21:00"),    # sleeps the night after the last day: no default departure
    (1, 0, "15:00"),    # one day, no night: a day trip home
])
def test_the_last_day_is_cut_by_the_default_departure_only_when_the_trip_leaves_that_day(days, nights, last_end):
    out = trip_days(ctx(days=days, nights=nights), CFG)
    assert len(out) == days and out[-1].end == to_min(last_end)


def test_a_departure_the_user_stated_always_cuts_the_last_day():
    assert trip_days(ctx(days=3, nights=3, checkout_at="12:00"), CFG)[-1].end == to_min("12:00")
