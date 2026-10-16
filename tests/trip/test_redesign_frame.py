"""Trip redesign part 2a: the day frame is compiled once, in Trip, and physical times always win.

Test ids F1-F17 of docs/superpowers/specs/2026-10-15-trip-understanding-architecture.md §5.2. Times: buffer 45 min
around a coach / flight, 30 min between the hub and the lodging.
"""

from datetime import date

import pytest

from trip import TripState, compile_frame, compile_search_input
from trip.domain.frame import FrameDefaults

BUFFER, ENTRY = 45, 30
START = "2026-11-20"  # a Friday


def said(value, turn=1):
    return {"value": value, "source": "user", "confidence": "high", "status": "confirmed",
            "evidence": [{"turn": turn, "quote": "q"}]}


def state(days=3, start=START, frame=None, **fields):
    data = {"days": said(days), **({"start_date": said(start)} if start else {}),
            **{k: said(v) for k, v in fields.items()}, "frame": frame or {}}
    return TripState.model_validate(data)


def frame(st, **kw):
    return compile_frame(st, arrival_buffer_min=BUFFER, entry_min=ENTRY, **kw)


def windows(f):
    return [(d.start, d.end) for d in f.days]


def busy(f, i):
    return [(b.start, b.end) for b in f.days[i].busy]


def issues(f):
    return {i.code for i in f.issues}


# ---------- F1, F17: defaults ----------

def test_f1_plain_trip_uses_published_defaults_and_real_dates():
    f = frame(state())
    assert [d.date for d in f.days] == [date(2026, 11, 20), date(2026, 11, 21), date(2026, 11, 22)]
    assert windows(f) == [("14:00", "21:00"), ("08:00", "21:00"), ("08:00", "12:00")]
    assert all(d.intensity == "normal" for d in f.days)


def test_f17_a_day_trip_never_ends_before_it_starts():
    # first-day 14:00 and last-day 12:00 defaults would cross on a one-day trip
    f = frame(state(days=1))
    (start, end), = windows(f)
    assert start < end and "day_has_no_time" not in issues(f)


def test_f1_defaults_come_from_the_caller():
    f = frame(state(days=2), defaults=FrameDefaults(day_start="07:00", day_end="22:00", first_start="10:00",
                                                  last_end="16:00"))
    assert windows(f) == [("10:00", "22:00"), ("07:00", "16:00")]


# ---------- F2-F6, F15: arrival and departure are physical ----------

def test_f2_a_flight_landing_opens_day_one_after_buffer_and_road():
    f = frame(state(frame={"arrive": said({"at": "2026-11-20T09:30", "how": "plane"})}))
    assert f.days[0].start == "10:45"


def test_f3_wanting_to_start_before_the_plane_lands_is_not_possible():
    st = state(checkin_at="08:00", frame={"arrive": said({"at": "2026-11-20T10:00", "how": "plane"})})
    f = frame(st)
    assert f.days[0].start == "11:15" and "start_before_arrival" in issues(f)


def test_f4_a_flight_home_closes_the_last_day_before_buffer_and_road():
    f = frame(state(frame={"leave": said({"at": "2026-11-22T16:00", "how": "plane"})}))
    assert f.days[-1].end == "14:45"


def test_f4_wanting_to_stay_later_than_the_flight_allows_is_not_possible():
    st = state(checkout_at="18:00", frame={"leave": said({"at": "2026-11-22T16:00", "how": "plane"})})
    f = frame(st)
    assert f.days[-1].end == "14:45" and "end_after_departure" in issues(f)


def test_f5_an_overnight_coach_at_four_never_opens_the_day_earlier():
    f = frame(state(frame={"arrive": said({"at": "2026-11-20T04:00", "how": "bus"})}))
    assert f.days[0].start == "05:15"


def test_f6_leaving_at_dawn_leaves_no_time_on_the_last_day():
    f = frame(state(frame={"leave": said({"at": "2026-11-22T07:00", "how": "bus"})}))
    assert f.days[-1].intensity == "free" and "day_has_no_time" in issues(f)


def test_f15_an_arrival_on_another_date_than_day_one_is_reported_not_shifted():
    f = frame(state(frame={"arrive": said({"at": "2026-11-21T09:30", "how": "plane"})}))
    assert "arrive_not_on_first_day" in issues(f)
    assert f.days[0].date == date(2026, 11, 20)


def test_f2_a_crawled_inbound_trip_counts_as_the_arrival():
    st = state(inbound={"mode": "plane", "carrier": "VN", "depart_at": "2026-11-20T08:00",
                        "arrive_at": "2026-11-20T09:30", "from_point": "SGN", "to_point": "DLI",
                        "source": "test", "fetched_at": "2026-10-15T00:00"})
    assert frame(st).days[0].start == "10:45"


# ---------- F7-F10, F14: busy blocks ----------

def test_f7_a_daily_nap_is_on_every_day_inside_its_window():
    nap = {"label": "nghỉ trưa", "kind": "rest", "where": "lodging", "start": "12:00", "end": "14:00", "on": "all"}
    f = frame(state(frame={"busy": [nap]}))
    assert busy(f, 0) == []  # day one opens at 14:00: the nap is already over
    assert busy(f, 1) == [("12:00", "14:00")]
    assert busy(f, 2) == []  # the last day ends at 12:00


def test_f8_weekday_work_lands_only_on_weekdays_of_the_trip():
    work = {"label": "họp", "kind": "work", "where": "lodging", "start": "08:00", "end": "17:00", "on": "weekdays"}
    st = state(checkin_at="08:00", checkout_at="21:00", frame={"busy": [work]})
    f = frame(st)
    assert busy(f, 0) == [("08:00", "17:00")]  # Friday
    assert busy(f, 1) == [] and busy(f, 2) == []  # Saturday, Sunday


def test_f9_overlapping_busy_blocks_are_merged():
    nap = {"label": "nghỉ trưa", "kind": "rest", "where": "lodging", "start": "12:00", "end": "14:00", "on": "all"}
    tour = {"label": "tour", "kind": "event", "where": "Tour xe jeep", "start": "13:30", "end": "15:00", "on": [1]}
    f = frame(state(frame={"busy": [nap, tour]}))
    assert busy(f, 1) == [("12:00", "15:00")]


def test_f10_an_evening_sleep_ends_the_day_and_crosses_midnight():
    sleep = {"label": "bé ngủ", "kind": "sleep", "where": "lodging", "start": "19:30", "end": "06:30", "on": "all"}
    f = frame(state(frame={"busy": [sleep]}))
    assert [d.end for d in f.days[:2]] == ["19:30", "19:30"]
    assert f.days[1].start == "08:00"  # waking at 06:30 does not move the default start earlier


def test_f14_a_busy_block_outside_the_day_is_dropped_never_negative():
    late = {"label": "gọi điện", "kind": "work", "where": "lodging", "start": "22:00", "end": "23:00", "on": "all"}
    f = frame(state(frame={"busy": [late]}))
    assert all(busy(f, i) == [] for i in range(3))


def test_f14_a_busy_block_cut_by_the_day_edge_is_clipped():
    early = {"label": "họp", "kind": "work", "where": "lodging", "start": "06:00", "end": "09:00", "on": [1]}
    assert busy(frame(state(frame={"busy": [early]})), 1) == [("08:00", "09:00")]


# ---------- F11-F12: per-day rhythm ----------

def test_f11_an_early_start_on_one_day_only():
    f = frame(state(frame={"days": [{"index": 1, "start": "05:00", **_ev()}]}))
    assert [d.start for d in f.days] == ["14:00", "05:00", "08:00"]


def test_f11_an_early_rhythm_for_the_whole_trip_is_not_clamped_to_the_default():
    st = state(day_end="20:00", frame={"day_start": said("05:00")})
    assert windows(frame(st))[1] == ("05:00", "20:00")


def test_f12_a_rest_day_has_no_time_to_fill():
    f = frame(state(frame={"days": [{"index": 2, "intensity": "free", **_ev()}]}))
    assert f.days[2].intensity == "free"


def test_f12_a_whole_day_of_busy_makes_the_day_free():
    work = {"label": "hội thảo", "kind": "event", "where": "Trung tâm hội nghị", "start": "08:00", "end": "21:00",
            "on": [1]}
    f = frame(state(frame={"busy": [work]}))
    assert f.days[1].intensity == "free" and "day_has_no_time" in issues(f)


# ---------- F13 + carried wishes ----------

def test_f13_no_start_date_no_frame():
    assert frame(state(start=None)) is None


def test_the_daily_driving_cap_and_meal_needs_reach_the_frame():
    f = frame(state(frame={"drive_day_min": said(120), "meals": said({"skip": ["breakfast"], "snacks": True})}))
    assert f.drive_day_min == 120 and f.meals.skip == ("breakfast",) and f.meals.snacks


def test_search_input_carries_the_compiled_frame():
    si = compile_search_input(state(frame={"arrive": said({"at": "2026-11-20T09:30", "how": "plane"})}))
    assert si.context.frame is not None and si.context.frame.days[0].start == "10:45"


def _ev():
    return {"source": "user", "evidence": [{"turn": 1, "quote": "q"}]}


@pytest.mark.parametrize("bad", [
    {"start": "25:00", "end": "26:00"}, {"start": "14:00", "end": "14:00"},
])
def test_an_impossible_busy_block_is_refused_at_the_boundary(bad):
    with pytest.raises(ValueError):
        state(frame={"busy": [{"label": "x", "kind": "work", "where": "lodging", "on": "all", **bad}]})
