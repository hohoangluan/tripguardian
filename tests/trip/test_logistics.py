from datetime import date

from trip.domain.logistics import entry_road, nearest_airport, pick_transit
from trip.domain.state import Base, Transit, TripState
from trip.infrastructure.settings import load

REAL = load()  # the shipped entry_roads and airports
NHA_TRANG = Base(text="Nha Trang", lat=12.2388, lng=109.1967)
FLIGHT_IN = Transit(mode="plane", carrier="Vietjet Air VJ361", depart_at="2026-12-14T07:05", arrive_at="2026-12-14T08:00",
                    from_point="Tân Sơn Nhất", to_point="Sân bay Liên Khương", price_vnd=890000,
                    source="google_flights", fetched_at="2026-12-01T03:00:00+00:00")
FLIGHT_OUT = Transit(mode="plane", carrier="Vietjet Air VJ362", depart_at="2026-12-16T18:40", arrive_at="2026-12-16T19:35",
                     from_point="Sân bay Liên Khương", to_point="Tân Sơn Nhất", price_vnd=890000,
                     source="google_flights", fetched_at="2026-12-01T03:00:00+00:00")


def test_entry_road_follows_the_direction_of_the_origin():
    assert entry_road(Base(text="HCM", lat=10.78, lng=106.70), REAL).text == "Đèo Prenn"
    assert entry_road(NHA_TRANG, REAL).text == "Đèo Khánh Lê"
    assert entry_road(Base(text="Phan Rang", lat=11.56, lng=108.99), REAL).text == "Đèo Ngoạn Mục"


def test_an_origin_without_a_point_has_no_road_and_no_airport():
    assert entry_road(Base(text="đâu đó"), REAL) is None
    assert nearest_airport(Base(text="đâu đó"), REAL) is None


def test_a_chosen_flight_sets_the_day_window_and_the_city_entry_and_exit():
    st = pick_transit(TripState(), "inbound", FLIGHT_IN, REAL, 1)
    st = pick_transit(st, "outbound", FLIGHT_OUT, REAL, 2)
    assert st.arrive_at.value == "08:45" and st.leave_at.value == "17:55"
    assert st.entry_point.value.text == "Sân bay Liên Khương" and st.exit_point.value.text == "Sân bay Liên Khương"
