from datetime import date

from live.sun import sun_times

DALAT_LAT, DALAT_LNG = 11.9465, 108.4419


def hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def test_dalat_midsummer_sunrise_and_sunset_land_in_the_right_window():
    rise, set_ = sun_times(date(2026, 6, 21), DALAT_LAT, DALAT_LNG)
    assert 5 * 60 + 15 <= rise <= 5 * 60 + 40, hhmm(rise)
    assert 18 * 60 + 0 <= set_ <= 18 * 60 + 25, hhmm(set_)


def test_dalat_midwinter_sunrise_and_sunset_land_in_the_right_window():
    rise, set_ = sun_times(date(2026, 12, 21), DALAT_LAT, DALAT_LNG)
    assert 6 * 60 + 0 <= rise <= 6 * 60 + 25, hhmm(rise)
    assert 17 * 60 + 15 <= set_ <= 17 * 60 + 40, hhmm(set_)


def test_the_longest_day_of_the_year_is_in_june_not_december():
    june = sun_times(date(2026, 6, 21), DALAT_LAT, DALAT_LNG)
    december = sun_times(date(2026, 12, 21), DALAT_LAT, DALAT_LNG)
    assert (june[1] - june[0]) > (december[1] - december[0])


def test_sunrise_is_always_before_sunset_across_a_year():
    first = date(2026, 1, 1).toordinal()
    for offset in range(0, 365, 7):
        day = date.fromordinal(first + offset)
        rise, set_ = sun_times(day, DALAT_LAT, DALAT_LNG)
        assert rise < set_, day
        assert 10 * 60 < (set_ - rise) < 14 * 60, day  # the tropics never swing further than this


def test_on_the_equinox_at_the_equator_the_day_is_about_twelve_hours():
    rise, set_ = sun_times(date(2026, 3, 20), 0.0, 105.0, tz_offset_h=7.0)
    assert 11 * 60 + 50 <= (set_ - rise) <= 12 * 60 + 20


def test_the_polar_night_has_no_sunrise():
    assert sun_times(date(2026, 12, 21), 78.0, 15.0, tz_offset_h=1.0) is None
