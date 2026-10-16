"""Physical bounds apply to every date, including midnight-crossing transit buffers."""

from trip import TripState, compile_frame


def field(value):
    return {"value": value}


def compile_trip(**frame):
    return compile_frame(TripState.model_validate({
        "start_date": field("2026-11-20"), "days": field(3), "frame": frame,
    }))


def test_late_arrival_closes_earlier_dates_and_bounds_the_actual_arrival_day():
    result = compile_trip(arrive=field({"at": "2026-11-21T10:00", "how": "plane"}))
    assert result.days[0].start == result.days[0].end
    assert result.days[0].intensity == "free"
    assert result.days[1].start >= "11:15"
    assert result.days[1].date.isoformat() == "2026-11-21"


def test_arrival_buffer_crossing_midnight_cannot_leave_fake_time_before_ready():
    result = compile_trip(arrive=field({"at": "2026-11-20T23:30", "how": "plane"}),
                          days=[{"index": 0, "end": "23:59"}, {"index": 1, "start": "00:15"}])
    assert result.days[0].start == result.days[0].end
    assert result.days[0].intensity == "free"
    assert result.days[1].start == "00:45"
    assert any(i.code == "start_before_arrival" and i.day == 1 for i in result.issues)


def test_early_departure_closes_later_dates_and_bounds_its_actual_date():
    result = compile_trip(leave=field({"at": "2026-11-21T10:00", "how": "plane"}))
    assert result.days[1].end == "08:45"
    assert result.days[2].start == result.days[2].end
    assert result.days[2].intensity == "free"


def test_departure_buffer_crossing_midnight_bounds_the_previous_day():
    result = compile_trip(leave=field({"at": "2026-11-22T00:30", "how": "plane"}),
                          days=[{"index": 1, "end": "23:50"}])
    assert result.days[1].end == "23:15"
    assert result.days[2].start == result.days[2].end
    assert any(i.code == "end_after_departure" and i.day == 1 for i in result.issues)


def test_arrival_outside_trip_leaves_every_date_empty():
    result = compile_trip(arrive=field({"at": "2026-11-25T10:00", "how": "plane"}))
    assert all(d.start == d.end and d.intensity == "free" for d in result.days)


def test_departure_before_trip_leaves_every_date_empty():
    result = compile_trip(leave=field({"at": "2026-11-19T10:00", "how": "plane"}))
    assert all(d.start == d.end and d.intensity == "free" for d in result.days)
