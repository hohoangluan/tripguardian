"""Stored data from before the Vehicle values were motorbike | car | walk still carries mobility="ride" (Grab, taxi)."""

from trip import TripState, drop_ride
from trip.domain.state import Context

UNKNOWN = {"value": None, "source": "default", "confidence": "low", "status": "unknown", "evidence": []}
STALE = {"value": "ride", "source": "user", "confidence": "high", "status": "confirmed",
         "evidence": [{"turn": 1, "quote": "grab"}]}


def test_state_with_ride_loads_with_mobility_unknown():
    state = TripState.model_validate({"mobility": STALE})
    assert state.mobility.value is None
    assert state.mobility.status == "unknown"


def test_context_with_ride_loads_with_mobility_none():
    raw = {"start_date": None, "month": None, "days": 2, "base": None, "mobility": "ride", "companions": [],
           "people": None, "checkin_at": None, "checkout_at": None, "day_end": None}
    assert Context.model_validate(raw).mobility is None


def test_drop_ride_clears_field_context_and_chip_drafts():
    chip_ride = {"id": "mobility:ride", "label": "Grab, taxi", "drafts": [{"field": "mobility", "op": "set", "value": "ride"}]}
    chip_bike = {"id": "mobility:motorbike", "label": "Xe máy", "drafts": [{"field": "mobility", "op": "set", "value": "motorbike"}]}
    data = {"state": {"mobility": STALE}, "context": {"mobility": "ride", "days": 2}, "card": {"chips": [chip_bike, chip_ride]}}
    out = drop_ride(data)
    assert out["state"]["mobility"] == UNKNOWN
    assert out["context"] == {"mobility": None, "days": 2}
    assert out["card"]["chips"] == [chip_bike]
    assert "ride" not in repr(out)


def test_drop_ride_leaves_other_data_alone():
    data = {"state": {"mobility": {**STALE, "value": "car"}}, "context": {"mobility": "walk"}, "note": "ride the bus"}
    assert drop_ride(data) == data


def test_old_clock_fields_load_as_the_wished_hours_but_a_transits_arrival_stays():
    from trip import upgrade
    transit = {"mode": "plane", "carrier": "X", "depart_at": "2026-12-14T07:05", "arrive_at": "2026-12-14T08:00",
               "from_point": "a", "to_point": "b", "source": "s", "fetched_at": "t"}
    old = {"arrive_at": {**UNKNOWN, "value": "09:00", "source": "user", "confidence": "high",
                         "evidence": [{"turn": 1, "quote": "9h"}]}, "leave_at": UNKNOWN,
           "inbound": {**UNKNOWN, "value": transit, "source": "user", "confidence": "high", "evidence": [{"turn": 1, "tool": "t"}]}}
    state = TripState.model_validate(old)
    assert state.checkin_at.value == "09:00" and not state.checkout_at.known
    assert state.inbound.value.arrive_at == "2026-12-14T08:00"
    assert upgrade({"context": {"arrive_at": None, "leave_at": "15:00"}}) == {"context": {"checkin_at": None, "checkout_at": "15:00"}}
