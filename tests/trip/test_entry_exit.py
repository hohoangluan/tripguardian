"""entry_point / exit_point: where the user enters and leaves the city (docs/P4_PLANNING.md §Đầu vào)."""

from datetime import date


from trip.domain.compile import compile_search_input
from trip.domain.state import Base, Evidence, TripState, Update, apply, settle, unknown_fields
from trip.domain.values import parse

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


def test_the_understanding_view_shows_what_a_chip_recorded():
    from trip.domain.understanding import view
    s = up(minimal(), "entry_point", Base(text="Sân bay Liên Khương"))
    targets = {r["target"] for r in view(settle(s), None, None)["trip"]}
    assert "entry_point" in targets and "exit_point" not in targets


def test_the_agent_may_write_both_fields_and_is_told_how():
    from trip.agent import system_prompt
    from trip.agent import SPECS

    allowed = SPECS["record_fact"]["function"]["parameters"]["properties"]["field"]["enum"]
    assert {"entry_point", "exit_point"} <= set(allowed)
    assert "entry_point" in system_prompt() and "exit_point" in system_prompt()
