"""Nights are their own fact next to days: "3 ngày 2 đêm", "3 ngày 3 đêm", "1 ngày 0 đêm"."""

from datetime import date

import pytest

from trip import nights
from trip.domain.compile import compile_search_input
from trip.domain.prepass import prepass
from trip.domain.questions import QUIZ_FIELD, find_quiz, quiz_queue
from trip.domain.state import Evidence, TripState, Update, apply, unknown_fields
from trip.domain.understanding import TRIP_ROWS, view

TODAY = date(2026, 10, 2)
EV = Evidence(turn=1, quote="x")


def got(text):
    return {(p.field, p.value) for p in prepass(text, TODAY).proposals if p.field in ("days", "nights")}


def up(s, field, value=None, op="set"):
    return apply(s, Update(field=field, op=op, value=value, source="user", confidence="high", evidence=EV))


# ---------- reading the user's words ----------

@pytest.mark.parametrize("text, expected", [
    ("đi Đà Lạt 3 ngày 2 đêm", {("days", 3), ("nights", 2)}),
    ("3 ngày 3 đêm nhé", {("days", 3), ("nights", 3)}),
    ("1 ngày 0 đêm", {("days", 1), ("nights", 0)}),
    ("lịch 3N2Đ", {("days", 3), ("nights", 2)}),
    ("3N3Đ", {("days", 3), ("nights", 3)}),
    ("1N0Đ", {("days", 1), ("nights", 0)}),
    ("ba ngày hai đêm", {("days", 3), ("nights", 2)}),
    ("đi 3 ngày", {("days", 3)}),                    # nights not said: not guessed
])
def test_prepass_reads_nights_with_days(text, expected):
    assert got(text) == expected


# ---------- the state ----------

def test_nights_range_and_never_more_than_days():
    s = up(TripState(), "days", 3)
    assert up(s, "nights", 0).nights.value == 0 and up(s, "nights", 3).nights.value == 3
    with pytest.raises(ValueError):
        up(s, "nights", 4)
    with pytest.raises(ValueError):
        up(TripState(), "nights", 8)


def test_a_shorter_trip_drops_the_nights_said_of_the_longer_one():
    s = up(up(TripState(), "days", 3), "nights", 2)
    assert up(s, "days", 3).nights.value == 2
    assert not up(s, "days", 1).nights.known


def test_unknown_nights_is_listed_only_once_days_are_known():
    assert "nights" not in unknown_fields(TripState())
    s = up(TripState(), "days", 3)
    assert "nights" in unknown_fields(s) and "nights" not in unknown_fields(up(s, "nights", 2))


def test_the_understanding_panel_has_a_nights_row_after_days(catalog, cfg):
    assert TRIP_ROWS.index("nights") == TRIP_ROWS.index("days") + 1
    s = up(up(TripState(), "days", 3), "nights", 2)
    rows = {r["target"]: r for r in view(s, catalog, cfg)["trip"]}
    assert rows["nights"]["value"] == 2


# ---------- Search Input ----------

@pytest.mark.parametrize("days, n", [(3, 2), (3, 3), (1, 0)])
def test_search_input_carries_nights(days, n):
    si = compile_search_input(up(up(TripState(), "days", days), "nights", n))
    assert (si.context.days, si.context.nights) == (days, n) and "nights" not in si.unknowns


def test_search_input_without_nights_says_so_and_does_not_guess():
    si = compile_search_input(up(TripState(), "days", 3))
    assert si.context.nights is None and "nights" in si.unknowns


# ---------- the shared helper ----------

def test_nights_helper_reads_nights_else_falls_back_to_days_minus_one():
    assert nights({"days": 3, "nights": 3}) == 3
    assert nights({"days": 3, "nights": 2}) == 2
    assert nights({"days": 1, "nights": 0}) == 0
    assert nights({"days": 3, "nights": None}) == 2 and nights({"days": 3}) == 2
    assert nights({"days": 1}) == 0 and nights({}) == 0
    si = compile_search_input(up(up(TripState(), "days", 3), "nights", 3))
    assert nights(si.context) == 3                                  # the object form, not only a dict
    assert nights(compile_search_input(up(TripState(), "days", 4)).context) == 3


# ---------- the question ----------

def test_nights_is_asked_right_after_days_with_days_minus_one_first(catalog, cfg):
    s = up(TripState(), "days", 3)
    qids = [q.qid for q in quiz_queue(s, catalog, cfg)]
    assert qids[0] == "nights" and QUIZ_FIELD["nights"] == "nights"
    q = find_quiz("nights", s, catalog, cfg)
    assert [c.id for c in q.chips][:2] == ["nights:2", "nights:3"]      # days - 1 is the suggested one, listed first
    assert [(d.field, d.value) for d in q.chips[0].drafts] == [("nights", 2)]


def test_a_one_day_trip_may_have_no_night(catalog, cfg):
    q = find_quiz("nights", up(TripState(), "days", 1), catalog, cfg)
    assert [c.id for c in q.chips][:2] == ["nights:0", "nights:1"]


def test_nights_is_not_asked_before_days_or_once_known(catalog, cfg):
    assert "nights" not in [q.qid for q in quiz_queue(TripState(), catalog, cfg)]
    s = up(up(TripState(), "days", 3), "nights", 3)
    assert "nights" not in [q.qid for q in quiz_queue(s, catalog, cfg)]
