from datetime import date

import pytest

import trip
from trip.domain.questions import days_q
from trip.domain.state import Context, Evidence, TripState, Update, apply


def context(**changes):
    data = dict(start_date=None, month=None, days=None, base=None, mobility=None,
                companions=(), people=None, checkin_at=None, checkout_at=None, day_end=None)
    return Context(**(data | changes))


def update(field, value):
    return Update(field=field, value=value, source="user", confidence="high",
                  evidence=Evidence(turn=1, quote="duration"))


def test_public_duration_limit():
    assert getattr(trip, "MAX_TRIP_DAYS", None) == 30
    assert getattr(trip, "RECOMMENDED_TRIP_DAYS", None) == 14


@pytest.mark.parametrize("days", (1, 7, 8, 14, 30, None))
def test_context_accepts_supported_days(days):
    assert context(days=days).days == days


@pytest.mark.parametrize("field,value", (("days", 0), ("days", 31), ("nights", -1), ("nights", 31)))
def test_context_rejects_unsupported_duration(field, value):
    with pytest.raises(ValueError):
        context(**{field: value})


@pytest.mark.parametrize("nights", (0, 13, 14, 30, None))
def test_context_accepts_supported_nights(nights):
    assert context(nights=nights).nights == nights


def test_state_supports_fourteen_days_and_preserves_consistency():
    state = apply(TripState(), update("days", 14))
    state = apply(state, update("nights", 13))
    assert state.days.value == 14 and state.nights.value == 13
    assert apply(state, update("days", 7)).nights.value is None
    with pytest.raises(ValueError):
        apply(apply(TripState(), update("days", 7)), update("nights", 8))
    for field in ("days", "nights"):
        with pytest.raises(ValueError):
            apply(TripState(), update(field, 31))


@pytest.mark.parametrize("text,expected", (
    ("đi 14 ngày 13 đêm", {"days": 14, "nights": 13}),
    ("sau khoảng 2 tuần mình đi một tuần", {"days": 7}),
    ("2 tuần nữa mình mới đi một tuần", {"days": 7}),
    ("đi 2 tuần", {"days": 14}), ("đi hai tuần", {"days": 14}),
    ("đi một tuần", {"days": 7}), ("14N13Đ", {"days": 14, "nights": 13}),
    ("ở 13 đêm", {"days": 14, "nights": 13}),
    ("ở 14 đêm", {"days": 15, "nights": 14}),
    ("ở 30 đêm", {"nights": 30}),
    ("đi 30 ngày 29 đêm", {"days": 30, "nights": 29}),
    ("đi 4 tuần", {"days": 28}),
))
def test_prepass_reads_long_durations(text, expected):
    actual = {p.field: p.value for p in trip.prepass(text, date(2026, 10, 2)).proposals
              if p.field in ("days", "nights")}
    assert actual == expected


@pytest.mark.parametrize("text", (
    "sau 2 tuần đi", "sau hai tuần đi", "2 tuần nữa mình mới đi", "sau khoảng 2 tuần mình đi", "ngân sách 2 triệu mỗi tuần", "2 triệu / 2 tuần",
    "không đi 14 ngày", "không ở 13 đêm", "không đi hai tuần", "không đi 14N13Đ",
    "đi 31 ngày", "đi 5 tuần", "ở 31 đêm", "31N30Đ",
))
def test_prepass_does_not_invent_supported_duration(text):
    assert not [p for p in trip.prepass(text, date(2026, 10, 2)).proposals
                if p.field in ("days", "nights")]


def test_duration_chips_include_week_and_fortnight():
    chips = {chip.id: chip for chip in days_q().chips}
    for days in (1, 2, 3, 4, 5, 7, 14):
        assert {draft.field: draft.value for draft in chips[f"days:{days}"].drafts} == {
            "days": days, "nights": days - 1}


def test_agent_prompt_uses_supported_duration_range():
    from trip.agent.prompt import SYSTEM
    assert "days 1-30" in SYSTEM and "nights 0-30" in SYSTEM
    assert "14 days" in SYSTEM


def test_state_accepts_thirty_days_and_nights():
    state = apply(TripState(), update("days", 30))
    assert apply(state, update("nights", 30)).nights.value == 30
