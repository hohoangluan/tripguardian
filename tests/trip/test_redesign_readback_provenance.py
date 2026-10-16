"""Read-back provenance must follow each contributing value.

Part 5 merged the per-day lines (tests/trip/test_redesign_readback.py RB1): a default hour now lives only in the one
"Mặc định" line, a user's hour only in a said line. The intent of these tests is unchanged.
"""

from trip import TripState, compile_search_input
from trip.domain.readback import build


def said(value, source="user"):
    return {"value": value, "source": source, "evidence": [{"turn": 1, "quote": "q"}]}


def state(**changes):
    data = {"start_date": said("2026-11-20"), "days": said(3), "checkin_at": said("14:00"),
            "checkout_at": said("12:00")}
    data.update(changes)
    return TripState.model_validate(data)


def text_of(lines, kind):
    return " ".join(x.text for x in lines if x.kind == kind)


def test_intensity_override_does_not_make_default_day_hours_user_facts():
    lines = build(compile_search_input(state(frame={"days": [{"index": 1, "intensity": "free"}]}))).lines
    assert "Ngày 2" in text_of(lines, "said") and "để trống" in text_of(lines, "said")
    assert "08:00" not in text_of(lines, "said") and "21:00" not in text_of(lines, "said")


def test_start_override_does_not_make_default_end_a_user_fact():
    lines = build(compile_search_input(state(frame={"days": [{"index": 1, "start": "05:00"}]}))).lines
    assert "05:00" in text_of(lines, "said")
    assert "21:00" not in text_of(lines, "said") and "21:00" in text_of(lines, "default")


def test_inferred_budget_scope_is_not_read_back_as_a_user_fact():
    si = compile_search_input(state(budget_vnd=said(10_000_000), budget_scope=said("trip_total", "inferred")))
    line = next(x for x in build(si).lines if x.tab == "budget")
    assert line.kind == "guess" and line.undo == "budget_scope"


def test_selected_transport_retains_arrival_provenance():
    inbound = {"mode": "plane", "carrier": "Test Air", "depart_at": "2026-11-20T08:00",
               "arrive_at": "2026-11-20T09:30", "from_point": "SGN", "to_point": "DLI",
               "source": "fixture", "fetched_at": "2026-10-15T12:00"}
    si = compile_search_input(state(inbound=said(inbound)))
    assert "9:30" in text_of(build(si).lines, "said")
