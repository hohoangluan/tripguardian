"""Vehicles are motorbike | car (| walk when a trip that arrives by coach or plane rents nothing); no Grab / taxi.
A trip that arrives by coach or plane is guided to rent a motorbike (docs/P2_TRIP_UNDERSTANDING.md §Hậu cần)."""

import pytest
from pydantic import ValidationError

from trip import rents_bike
from trip.domain import values
from trip.domain.prepass import prepass
from trip.domain.questions import apply_chip, find_quiz, mobility_q
from trip.domain.rental import rental_hint
from trip.domain.state import Base, Evidence, TripState, Update, apply
from trip.domain.understanding import view
from datetime import date

EV = Evidence(turn=1, quote="x")


def up(s, field, value):
    return apply(s, Update(field=field, value=value, source="user", confidence="high", evidence=EV))


def chips(q):
    return {c.id: c.label for c in q.chips if c.id != "other"}


def test_ride_is_not_a_vehicle_and_walk_is(catalog):
    with pytest.raises(ValueError):
        values.parse("mobility", "ride", catalog)
    assert values.parse("mobility", "walk", catalog) == "walk"
    with pytest.raises(ValidationError):
        up(TripState(), "mobility", "ride")


def test_grab_and_taxi_set_no_vehicle():
    for text in ("mình đi grab", "gọi taxi cho tiện", "đi xe công nghệ"):
        assert not [p for p in prepass(text, date(2026, 10, 2)).proposals if p.field == "mobility"], text


def test_the_mobility_card_offers_motorbike_and_car_for_a_trip_that_drives_in():
    assert list(chips(mobility_q())) == ["mobility:motorbike", "mobility:car"]
    assert list(chips(mobility_q("self"))) == ["mobility:motorbike", "mobility:car"]


@pytest.mark.parametrize("arrival", ["bus", "plane"])
def test_the_mobility_card_of_a_trip_that_arrives_without_a_vehicle_leads_to_a_rental(arrival):
    q = mobility_q(arrival)
    assert list(chips(q)) == ["mobility:motorbike", "mobility:car", "mobility:walk"]
    assert chips(q)["mobility:motorbike"].startswith("Thuê xe máy")
    assert "đi bộ" in chips(q)["mobility:walk"]
    assert q.input == "rental" and q.params == {"mode": arrival}
    for c in q.chips:
        for dr in c.drafts:
            values.parse(dr.field, str(dr.value), None)


def test_the_quiz_asks_the_card_that_matches_how_the_trip_arrives(catalog, cfg):
    s = up(TripState(), "arrival_mode", "bus")
    q = find_quiz("mobility", s, catalog, cfg)
    assert "mobility:walk" in chips(q)
    s = apply_chip(s, q, ("mobility:walk",), 1)
    assert s.mobility.value == "walk"
    assert "mobility:walk" not in chips(find_quiz("mobility", TripState(), catalog, cfg))


def test_the_card_measures_from_the_entry_point_when_it_has_a_point():
    s = up(up(TripState(), "arrival_mode", "plane"), "entry_point", Base(text="Sân bay", lat=11.75, lng=108.37))
    assert mobility_q("plane", s.entry_point.value).params == {"mode": "plane", "lat": 11.75, "lng": 108.37, "text": "Sân bay"}


@pytest.mark.parametrize("ctx, expected", [
    ({"arrival_mode": "bus", "mobility": "motorbike"}, True),
    ({"arrival_mode": "plane", "mobility": "motorbike"}, True),
    ({"arrival_mode": "self", "mobility": "motorbike"}, False),      # rides in on their own bike
    ({"arrival_mode": None, "mobility": "motorbike"}, False),
    ({"arrival_mode": "bus", "mobility": "car"}, False),
    ({"arrival_mode": "bus", "mobility": "walk"}, False),            # refused to rent: nothing to collect
])
def test_only_a_motorbike_rider_without_a_vehicle_rents(ctx, expected):
    assert rents_bike(ctx) is expected


def test_the_panel_hint_suggests_a_rental_declines_gracefully_and_stays_silent_otherwise():
    bus = up(TripState(), "arrival_mode", "bus")
    assert rental_hint(bus) == {"status": "suggest", "params": {"mode": "bus"}}
    assert rental_hint(up(bus, "mobility", "motorbike"))["status"] == "suggest"
    declined = rental_hint(up(bus, "mobility", "walk"))
    assert declined["status"] == "declined" and "đi bộ" in declined["note"] and "xa" in declined["note"]
    assert rental_hint(up(bus, "mobility", "car")) is None
    assert rental_hint(TripState()) is None
    assert rental_hint(up(up(TripState(), "arrival_mode", "self"), "mobility", "motorbike")) is None


def test_the_understanding_view_carries_the_hint(catalog, cfg):
    s = up(TripState(), "arrival_mode", "plane")
    assert view(s, catalog, cfg)["rental"]["params"] == {"mode": "plane"}
    assert view(TripState(), catalog, cfg)["rental"] is None
