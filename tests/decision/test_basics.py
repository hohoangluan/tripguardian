from datetime import date

from fixtures import MONDAY, si, srec

from decision.geo import fmt, km, minutes, point, to_min
from decision.model import Cand, role_of, value
from decision.settings import default
from decision.trip_days import month_of, trip_days

CFG = default()


def test_settings_load_every_key():
    assert CFG.per_day["normal"] == 4 and CFG.narrow_buckets == ("early_morning", "evening", "night")
    assert CFG.labels["feature"]["steep_or_stairs"] == "Dốc, nhiều bậc"


def test_geo():
    assert round(km((11.94, 108.44), (11.94, 108.45)), 2) == 1.09
    assert minutes(10, "motorbike", CFG) == 34 and minutes(10, None, CFG) == 34
    assert to_min("07:30") == 450 and fmt(450) == "07:30"
    assert point(srec("A")) == (11.94, 108.44) and point(srec("B", lat=None)) is None


def test_trip_days_windows_and_weekdays():
    days = trip_days(si(context={"days": 3, "arrive_at": "10:00", "leave_at": "14:00"}).context, CFG)
    assert [d.weekday for d in days] == ["mon", "tue", "wed"] and days[0].day_type == "weekday"
    assert (days[0].start, days[1].start, days[1].end, days[2].end) == (600, 480, 1260, 840)
    assert days[0].date == MONDAY


def test_trip_days_without_dates():
    ctx = si(context={"start_date": None, "month": 12, "days": None}).context
    days = trip_days(ctx, CFG)
    assert len(days) == CFG.default_days and days[0].weekday is None and month_of(ctx) == 12


def test_model_helpers():
    r = srec("A", features={"crowd": "high"}, usable=("meal",))
    assert role_of(r) == "meal" and role_of(srec("B", usable=())) is None
    assert value(r, "crowd") == "high" and value(r, "noise") is None
    assert Cand(r, "meal").name == "Nơi A"
