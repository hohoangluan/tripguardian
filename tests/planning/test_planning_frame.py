from plan_fixtures import CFG

from planning.frame import trip_days


def ctx(**kw):
    base = {"start_date": "2026-12-12", "days": 3, "arrive_at": None, "leave_at": None, "day_end": None}
    return {**base, **kw}


def test_every_day_has_a_date_a_weekday_and_the_default_window():
    days = trip_days(ctx(), CFG, "h", None, None)
    assert [(d.date.isoformat(), d.weekday) for d in days] == [
        ("2026-12-12", "sat"), ("2026-12-13", "sun"), ("2026-12-14", "mon")]
    assert (days[1].start, days[1].end) == (480, 1260)


def test_the_first_day_opens_at_arrival_and_the_last_closes_at_departure():
    days = trip_days(ctx(arrive_at="13:30", leave_at="12:00", day_end="20:00"), CFG, "h", None, None)
    assert (days[0].start, days[0].end) == (810, 1200)
    assert (days[1].start, days[1].end) == (480, 1200)
    assert (days[2].start, days[2].end) == (480, 720)


def test_the_last_day_closes_at_the_default_leave_time_when_the_user_gave_none():
    assert trip_days(ctx(), CFG, "h", None, None)[-1].end == CFG.leave_at


def test_a_one_day_trip_is_both_the_first_and_the_last_day():
    (d,) = trip_days(ctx(days=1, arrive_at="10:00", leave_at="17:00"), CFG, "h", "in", "out")
    assert (d.start, d.end, d.start_node, d.end_node) == (600, 1020, "in", "out")


def test_the_day_opens_at_the_entry_point_and_closes_at_the_exit_point_otherwise_at_home():
    days = trip_days(ctx(), CFG, "h", "in", "out")
    assert [(d.start_node, d.end_node) for d in days] == [("in", "h"), ("h", "h"), ("h", "out")]


def test_without_an_entry_or_exit_point_every_day_is_home_to_home():
    assert [(d.start_node, d.end_node) for d in trip_days(ctx(), CFG, "h", None, None)] == [("h", "h")] * 3


def test_days_and_dates_the_user_never_gave_stay_unknown():
    days = trip_days(ctx(days=None, start_date=None), CFG, "h", None, None)
    assert len(days) == CFG.default_days and all(d.date is None and d.weekday is None for d in days)
    only_date = trip_days(ctx(days=None), CFG, "h", None, None)      # a start date without a length gives no weekdays
    assert all(d.weekday is None for d in only_date)
