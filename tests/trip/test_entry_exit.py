"""entry_point / exit_point: where the user enters and leaves the city (docs/specs/PLANNING_SPEC.md §Đầu vào)."""

from datetime import date

import pytest

from trip.compile import compile_search_input
from trip.state import Base, Evidence, TripState, Update, apply, settle, unknown_fields
from trip.values import parse

EV = Evidence(turn=1, quote="mình xuống bến xe Liên tỉnh")


def up(s, field, value=None, op="set", source="user"):
    return apply(s, Update(field=field, op=op, value=value, source=source,
                           confidence="high" if source == "user" else "medium", evidence=EV))


def minimal():
    s = up(TripState(), "start_date", date(2026, 12, 12))
    return up(up(s, "days", 3), "mobility", "motorbike")


def test_a_bus_station_the_corpus_does_not_hold_is_kept_as_plain_text(catalog):
    got = parse("entry_point", "Bến xe Liên tỉnh Đà Lạt", catalog)
    assert isinstance(got, Base)
    assert got.place_id is None                      # the corpus holds no bus stations, and nothing is invented
    assert got.text == "Bến xe Liên tỉnh Đà Lạt"     # the text survives for Planning to geocode


def test_both_points_reach_the_search_input():
    s = minimal()
    s = up(s, "entry_point", Base(text="Bến xe Liên tỉnh Đà Lạt"))
    s = up(s, "exit_point", Base(text="Sân bay Liên Khương"))
    si = compile_search_input(settle(s))
    assert si.context.entry_point.text == "Bến xe Liên tỉnh Đà Lạt"
    assert si.context.exit_point.text == "Sân bay Liên Khương"


def test_not_knowing_them_leaves_them_none_and_breaks_nothing():
    si = compile_search_input(settle(minimal()))
    assert si.context.entry_point is None and si.context.exit_point is None


def test_only_the_entry_point_is_known():
    s = up(minimal(), "entry_point", Base(text="Bến xe Liên tỉnh Đà Lạt"))
    si = compile_search_input(settle(s))
    assert si.context.entry_point is not None and si.context.exit_point is None


def test_the_user_can_skip_the_question_without_losing_the_field():
    s = up(minimal(), "entry_point", op="remove")
    assert s.entry_point.status == "skipped"
    assert compile_search_input(settle(s)).context.entry_point is None


def test_they_are_not_counted_as_unknowns_that_block_the_search():
    assert "entry_point" not in unknown_fields(settle(minimal()))
    assert "exit_point" not in unknown_fields(settle(minimal()))


from trip.questions import bank


def test_the_question_appears_once_the_trip_has_dates_and_a_length(catalog, cfg):
    qs = {q.qid for q in bank(settle(minimal()), catalog, cfg)}
    assert "entry_exit" in qs


def test_the_question_disappears_once_both_points_are_known(catalog, cfg):
    s = up(minimal(), "entry_point", Base(text="Bến xe Liên tỉnh Đà Lạt"))
    s = up(s, "exit_point", Base(text="Bến xe Liên tỉnh Đà Lạt"))
    qs = {q.qid for q in bank(settle(s), catalog, cfg)}
    assert "entry_exit" not in qs


def test_asking_once_does_not_ask_again(catalog, cfg):
    from trip.state import with_meta
    s = with_meta(settle(minimal()), asked=("entry_exit",))
    assert "entry_exit" not in {q.qid for q in bank(s, catalog, cfg)}


def test_every_chip_of_the_question_writes_one_of_the_two_fields(catalog, cfg):
    q = next(q for q in bank(settle(minimal()), catalog, cfg) if q.qid == "entry_exit")
    assert q.multi is True
    assert set(q.single_rows) == {"Tới Đà Lạt bằng", "Rời Đà Lạt từ"}
    for chip in q.chips:
        fields = {dr.field for dr in chip.drafts}
        assert fields <= {"entry_point", "exit_point"} and fields
