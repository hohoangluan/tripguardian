"""The quiz cards for how the trip arrives, where it starts, the coach / flight, the lodging and the wished hours."""

import json
from datetime import date

from test_engine import make, names, run  # noqa: F401  (shared fixtures and helpers)
from test_logistics import FLIGHT_IN, REAL

from trip.domain.questions import arrival_q, find_quiz, lodging_q, quiz_queue, stay_times_q, transit_q
from trip.domain.state import Base, Evidence, TripState, Update, apply, settle

HCM = {"text": "TP Hồ Chí Minh", "lat": 10.7769, "lng": 106.7009, "province": "TP Hồ Chí Minh"}


def put(st, field, value):
    return settle(apply(st, Update(field=field, value=value, source="user", confidence="high",
                                   evidence=Evidence(turn=1, tool="test"))))


def told(e, sid):
    run(e, sid, kind="text", text="3 ngày 2 đêm với bạn gái tháng 12")  # the agent is down: keyword rules only
    return e.load(sid)["card"]


def test_arrival_card_says_the_vehicle_too_unless_it_is_known():
    assert [c.id for c in arrival_q(False).chips if c.id != "other"] == ["self:motorbike", "self:car", "bus", "plane"]
    assert [c.id for c in arrival_q(True).chips if c.id != "other"] == ["self", "bus", "plane"]


def test_driving_in_sets_the_vehicle_with_one_answer(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    assert told(e, sid)["qid"] == "arrival"  # days, nights and the partner were read; mobility and arrival were not
    st = e.store.get(sid).state
    assert not st.arrival_mode.known and not st.mobility.known
    run(e, sid, kind="answer", qid="arrival", chips=("self:motorbike",))
    st = e.store.get(sid).state
    assert (st.arrival_mode.value, st.mobility.value) == ("self", "motorbike")


def test_by_coach_the_origin_is_asked_then_the_rental_guide(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    told(e, sid)
    run(e, sid, kind="answer", qid="arrival", chips=("bus",))
    card = e.load(sid)["card"]
    assert (card["qid"], card["input"]) == ("origin", "geo")
    ev = run(e, sid, kind="answer", qid="origin", value=json.dumps(HCM))
    st = e.store.get(sid).state
    assert st.origin.value.text == "TP Hồ Chí Minh" and st.origin.value.province == "TP Hồ Chí Minh"
    card = ev[-1][1]
    assert (card["qid"], card["input"]) == ("mobility", "rental")


def test_a_bad_origin_row_is_refused_and_the_card_stays(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    told(e, sid)
    run(e, sid, kind="answer", qid="arrival", chips=("bus",))
    ev = run(e, sid, kind="answer", qid="origin", value='{"lat": 1}')
    assert names(ev)[0] == "error" and ev[-1][1]["qid"] == "origin"
    assert not e.store.get(sid).state.origin.known


def test_the_transit_card_needs_the_route_and_the_day_and_never_invents_either():
    st = put(put(TripState(), "arrival_mode", "plane"), "days", 3)
    assert transit_q("inbound", st, REAL) is None  # no origin, no date
    st = put(put(put(st, "origin", Base(**HCM)), "start_date", date(2026, 12, 14)), "mobility", "motorbike")
    inbound, outbound = transit_q("inbound", st, REAL), transit_q("outbound", st, REAL)
    assert inbound.params == {"mode": "plane", "from": "SGN", "to": "DLI", "date": "2026-12-14"}
    assert outbound.params == {"mode": "plane", "from": "DLI", "to": "SGN", "date": "2026-12-16"}
    assert (inbound.input, inbound.qid, outbound.qid) == ("transit", "inbound", "outbound")


def test_a_picked_flight_is_stored_and_sets_the_entry_point(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    told(e, sid)
    s = e.store.get(sid)
    s.state = put(put(put(s.state, "arrival_mode", "bus"), "origin", Base(**HCM)), "start_date", date(2026, 12, 14))
    e.store.save(s)
    q = find_quiz("inbound", e.store.get(sid).state, e.catalog, e.cfg)
    assert q is not None and q.params["mode"] == "bus"
    s = e.store.get(sid)
    s.card = q
    e.store.save(s)
    bus = FLIGHT_IN.model_copy(update={"mode": "bus", "carrier": "Phương Trang", "stops": None, "from_point": "Bến xe Miền Đông",
                                       "to_point": "Bến xe Liên tỉnh Đà Lạt"})
    run(e, sid, kind="answer", qid="inbound", value=bus.model_dump_json())
    st = e.store.get(sid).state
    assert st.inbound.value.carrier == "Phương Trang" and st.entry_point.value.text == "Bến xe Liên tỉnh Đà Lạt"


def test_only_a_time_typed_for_the_coach_sets_the_wished_start(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    told(e, sid)
    s = e.store.get(sid)
    s.state = put(put(put(s.state, "arrival_mode", "bus"), "origin", Base(**HCM)), "start_date", date(2026, 12, 14))
    s.card = find_quiz("inbound", s.state, e.catalog, e.cfg)
    e.store.save(s)
    run(e, sid, kind="answer", qid="inbound", value='{"time": "10:00"}')
    st = e.store.get(sid).state
    assert st.checkin_at.value == "10:00" and not st.inbound.known


def test_the_lodging_card_offers_the_not_booked_exit():
    q = lodging_q()
    assert (q.qid, q.input) == ("lodging", "lodging") and [c.id for c in q.chips] == ["none"]


def test_picking_a_lodging_makes_it_the_base_and_the_hours_are_asked_next(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    told(e, sid)
    s = e.store.get(sid)
    s.card = find_quiz("lodging", s.state, e.catalog, e.cfg)
    e.store.save(s)
    row = {"kind": "live", "text": "Khách sạn Ngọc Lan", "lat": 11.94, "lng": 108.44}
    run(e, sid, kind="answer", qid="lodging", value=json.dumps(row))
    st = e.store.get(sid).state
    assert st.lodging.value.text == "Khách sạn Ngọc Lan" and st.lodging_booked.value == "yes"
    assert "lodging" not in [q.qid for q in quiz_queue(st, e.catalog, e.cfg)]


def test_declining_the_lodging_still_asks_for_the_wished_hours(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    told(e, sid)
    s = e.store.get(sid)
    s.card = find_quiz("lodging", s.state, e.catalog, e.cfg)
    e.store.save(s)
    run(e, sid, kind="answer", qid="lodging", chips=("none",))
    st = e.store.get(sid).state
    assert st.lodging_booked.value == "no" and not st.lodging.known
    qids = [q.qid for q in quiz_queue(st, e.catalog, e.cfg)]
    assert "lodging" not in qids and "stay_times" in qids
    card = find_quiz("stay_times", st, e.catalog, e.cfg)      # no room to check into: it asks about the days
    assert "phòng" not in card.text and {c.row for c in card.chips if c.id != "other"} == {"Ngày đầu bắt đầu lúc", "Ngày cuối kết thúc lúc"}


def test_the_hours_card_writes_checkin_and_checkout_and_is_not_asked_again(make):
    q = stay_times_q()
    assert [c.id for c in q.chips if c.id != "other"][:1] == ["checkin:7"]
    assert {c.row for c in q.chips if c.id != "other"} == {"Nhận phòng lúc", "Trả phòng lúc"}
    e = make()
    sid = e.create("first", "nothing")["id"]
    told(e, sid)
    s = e.store.get(sid)
    s.card = find_quiz("stay_times", s.state, e.catalog, e.cfg)
    e.store.save(s)
    run(e, sid, kind="answer", qid="stay_times", chips=("checkin:14", "checkout:11"))
    st = e.store.get(sid).state
    assert (st.checkin_at.value, st.checkout_at.value) == ("14:00", "11:00")
    assert "stay_times" not in [q.qid for q in quiz_queue(st, e.catalog, e.cfg)]
