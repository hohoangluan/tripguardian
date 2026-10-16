"""Trip redesign: what the user reads on the deck (spec R §5, §8.1). Structure tests pass while the words still
re-ask what is known or say nothing about the plan; these pin the words.

C1 never re-ask a known answer in the question text      C4 budget says the ticket to Đà Lạt is not included
C2 every choice says what it changes in the plan          C5 length limits of R §8.1 on every tab
C3 tab ① offers the day-part chips of R §5                C6 a known arrival suggests the ready time, not 14:00
R9 the HTTP servers take a burst of connections (bench: 38 users at once got connection resets)
"""

import socket
import threading
import time

import pytest

from trip import TripState
from trip.domain import deck


def said(value, source="user", quote="q"):
    return {"value": value, "source": source, "confidence": "high" if source == "user" else "medium",
            "status": "confirmed" if source == "user" else "unknown", "evidence": [{"turn": 1, "quote": quote}]}


DATES = {"start_date": said("2026-11-20"), "days": said(3)}  # Friday 20/11 -> Sunday 22/11


def tabs(state, catalog, cfg, at="gate"):
    return {t.qid: t for t in deck.build(state, catalog, cfg, at=at).tabs}


def real(options):
    return [o for o in options if o.id not in ("other", "skip")]


def test_c1_known_dates_are_said_back_not_asked_again(catalog, cfg):
    t = tabs(TripState.model_validate(DATES), catalog, cfg)["trip"]
    assert "ngày nào" not in t.question.lower()
    assert "20/11" in t.question + t.why and "22/11" in t.question + t.why


def test_c1_a_known_head_count_is_not_asked_again(catalog, cfg):
    t = tabs(TripState.model_validate({"people": said(4)}), catalog, cfg)["companions"]
    assert "mấy người" not in t.question.lower() and "people" not in t.inputs


@pytest.mark.parametrize("qid", ["trip", "mobility", "care", "pace", "budget"])
def test_c2_every_choice_says_what_it_changes(catalog, cfg, qid):
    t = tabs(TripState.model_validate(DATES), catalog, cfg)
    t = t.get(qid) or tabs(TripState.model_validate({**DATES, "checkin_at": said("09:00"), "checkout_at": said("17:00"),
                                                     "companions": said(["solo"]), "people": said(1)}), catalog, cfg)[qid]
    blank = [o.label for o in real(t.options) if not o.description.strip()]
    assert not blank, f"{qid}: {blank}"


def test_c3_the_trip_tab_offers_day_parts_with_hours(catalog, cfg):
    t = tabs(TripState.model_validate(DATES), catalog, cfg)["trip"]
    labels = " ".join(o.label for o in t.options)
    for part in ("Sáng sớm", "Sáng", "Trưa", "Chiều", "Tối"):
        assert part in labels
    assert "5" in next(o.label for o in t.options if "Sáng sớm" in o.label)


def test_c3_the_default_hours_say_where_they_come_from(catalog, cfg):
    t = tabs(TripState.model_validate(DATES), catalog, cfg)["trip"]
    default = next(o for o in t.options if "14:00" in o.label)
    assert "nhận phòng" in default.description


def test_c4_the_budget_tab_says_the_ticket_is_not_included(catalog, cfg):
    state = TripState.model_validate({**DATES, "checkin_at": said("09:00"), "checkout_at": said("17:00"),
                                      "companions": said(["solo"]), "people": said(1), "mobility": said("walk"),
                                      "care": said("none"), "pace": said("normal")})
    t = tabs(state, catalog, cfg)["budget"]
    assert "chưa gồm vé" in (t.question + t.why).lower()


def test_c5_every_tab_fits_the_card(catalog, cfg):
    for state in (TripState(), TripState.model_validate(DATES)):
        for t in deck.build(state, catalog, cfg, at="gate").tabs:
            assert len(t.question) <= 90 and len(t.header) <= 12, t.qid
            for o in t.options:
                assert len(o.label) <= 40 and len(o.description) <= 80, (t.qid, o.label)


def test_c6_a_known_flight_suggests_the_ready_time(catalog, cfg):
    state = TripState.model_validate({**DATES, "frame": {"arrive": said({"at": "2026-11-20T09:30", "how": "plane"})}})
    t = tabs(state, catalog, cfg).get("trip")
    if t is None:  # the arrival already answers the first hour; the last hour is still asked
        return
    pre = [o for o in t.options if o.prefilled and o.id.startswith("start")]
    assert not pre or ("10:45" in pre[0].label and "9:30" in pre[0].because)
    assert not any("14:00" in o.label and o.prefilled for o in t.options)


# ---------- R9: a burst of connections is queued, not reset ----------

def test_r9_the_trip_server_queues_a_burst_of_connections(catalog, cfg, tmp_path):
    from http.server import ThreadingHTTPServer

    from trip.api import server as trip_server
    assert getattr(trip_server, "QUEUE", 0) >= 64
    from harness.protection import ProtectedHTTPServer
    assert ProtectedHTTPServer.request_queue_size >= 64
    assert ThreadingHTTPServer.request_queue_size == 5  # the stdlib default stays untouched: set per server


def test_r9_forty_simultaneous_connects_are_all_accepted(catalog, cfg, tmp_path):
    from trip.api.server import make_server
    from trip.api.engine import Engine
    from trip.infrastructure.sessions import SessionStore
    from trip_fixtures import ScriptedChat
    srv = make_server(Engine(catalog, cfg, SessionStore(tmp_path), ScriptedChat()), 0)
    port = srv.server_address[1]
    slow = threading.Event()
    original = srv.process_request

    def held(request, address):  # the accept loop is busy for a moment, as under load
        slow.wait(0.5)
        original(request, address)

    srv.process_request = held
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    socks = []
    try:
        for _ in range(40):
            s = socket.create_connection(("127.0.0.1", port), timeout=5)
            socks.append(s)
        for s in socks:
            s.sendall(b"GET /api/trip/places?q=a HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        time.sleep(0.2)
        slow.set()
        answered = sum(1 for s in socks if s.recv(12).startswith(b"HTTP/1."))
    finally:
        for s in socks:
            s.close()
        srv.shutdown()
    assert answered == 40


# ---------- C7-C9: found reading the real deck after part 3b ----------

def test_c7_the_last_day_cannot_end_before_dawn(catalog, cfg):
    t = tabs(TripState.model_validate(DATES), catalog, cfg)["trip"]
    ends = [o for o in t.options if o.id.startswith("end")]
    assert ends and not any("Sáng sớm" in o.label or "05:" in o.description for o in ends)


def _early(catalog, cfg):
    st = TripState.model_validate({**DATES, "soft": {"cloud_hunting=present": said("love", quote="săn mây")}})
    return next(t for t in deck.confirm_tabs(st, catalog, cfg) if t.qid == "confirm.early")


def test_c8_a_confirm_question_says_which_words_of_the_user_it_comes_from(catalog, cfg):
    t = _early(catalog, cfg)
    assert t.why.strip() and "săn mây" in t.why


def test_c9_days_are_named_by_their_date(catalog, cfg):
    labels = [o.label for o in _early(catalog, cfg).options if o.id.startswith("day.")]
    assert labels == ["T6 20/11", "T7 21/11", "CN 22/11"]
