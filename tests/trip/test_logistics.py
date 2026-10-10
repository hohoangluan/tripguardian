
from trip.domain.compile import compile_search_input, day_window
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


def test_a_chosen_flight_sets_the_city_entry_and_exit():
    st = pick_transit(TripState(), "inbound", FLIGHT_IN, REAL, 1)
    st = pick_transit(st, "outbound", FLIGHT_OUT, REAL, 2)
    assert st.inbound.value == FLIGHT_IN and st.outbound.value == FLIGHT_OUT
    assert st.entry_point.value.text == "Sân bay Liên Khương" and st.exit_point.value.text == "Sân bay Liên Khương"


def at(st, field, value):
    from trip.domain.state import Evidence, Update, apply
    return apply(st, Update(field=field, value=value, source="user", confidence="high", evidence=Evidence(turn=1, tool="t")))


def test_a_flight_is_the_physical_window_and_the_wished_hours_cannot_widen_it():
    st = pick_transit(pick_transit(TripState(), "inbound", FLIGHT_IN, REAL, 1), "outbound", FLIGHT_OUT, REAL, 2)
    assert day_window(st, REAL.arrival_buffer_min) == ("08:45", "17:55")  # landing 08:00 + 45 min; leaving 18:40 - 45 min
    early = at(at(st, "checkin_at", "07:00"), "checkout_at", "20:00")
    assert day_window(early, REAL.arrival_buffer_min) == ("08:45", "17:55")
    late = at(at(st, "checkin_at", "14:00"), "checkout_at", "12:00")
    assert day_window(late, REAL.arrival_buffer_min) == ("14:00", "12:00")  # the wish is narrower: it wins


def test_without_a_coach_or_flight_the_wished_hours_are_the_window():
    st = at(at(TripState(), "checkin_at", "14:00"), "checkout_at", "11:00")
    assert day_window(st) == ("14:00", "11:00")
    assert day_window(TripState()) == (None, None)
    context = compile_search_input(st).context
    assert (context.checkin_at, context.checkout_at) == ("14:00", "11:00")
