"""Decision reads the day frame Trip compiled (docs/superpowers/specs/2026-10-15-trip-understanding-architecture.md A1,
hand-off H1): same windows as Planning, never re-derived from config."""

from trip import TripState, compile_search_input

from decision.settings import default
from decision.trip_days import trip_days
from decision.geo import to_min


def said(value):
    return {"value": value, "source": "user", "confidence": "high", "status": "confirmed",
            "evidence": [{"turn": 1, "quote": "q"}]}


def test_h1_decision_days_are_the_compiled_frame():
    st = TripState.model_validate({
        "start_date": said("2026-11-20"), "days": said(3), "checkin_at": said("14:00"),
        "frame": {"arrive": said({"at": "2026-11-20T09:30", "how": "plane"}),
                  "days": [{"index": 1, "start": "05:00", "source": "user", "evidence": [{"turn": 1, "quote": "q"}]}]}})
    si = compile_search_input(st)
    days = trip_days(si.context, default())
    assert [(d.start, d.end) for d in days] == [(to_min(f.start), to_min(f.end)) for f in si.context.frame.days]
    assert days[1].start == to_min("05:00")  # not clamped to the config day start
