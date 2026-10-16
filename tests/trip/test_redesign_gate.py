"""Trip redesign part 2b: seven required answers, the read-back digest and the gate into Lịch trình.

Test ids Q1-Q13 of docs/superpowers/specs/2026-10-15-trip-understanding-architecture.md §5.3 (Q14 lives in
tests/planning/test_planning_trip_gate.py).
"""

import time
from datetime import date

import pytest
from trip_fixtures import ScriptedChat, say

from trip import TripState, compile_search_input, plan_digest
from trip.agent import AgentError
from trip.api.engine import Engine, TurnInput
from trip.domain import readback, readiness
from trip.domain.state import with_meta
from trip.infrastructure.sessions import SessionStore

REQUIRED = ["trip", "companions", "mobility", "care", "pace", "budget", "lodging"]


def said(value, turn=1, source="user"):
    return {"value": value, "source": source, "confidence": "high" if source == "user" else "medium",
            "status": "confirmed" if source == "user" else "unknown", "evidence": [{"turn": turn, "quote": "q"}]}


FULL = {"start_date": said("2026-11-20"), "days": said(3), "checkin_at": said("14:00"), "checkout_at": said("12:00"),
        "companions": said(["partner"]), "people": said(2), "mobility": said("motorbike"), "care": said("none"),
        "pace": said("slow"), "budget_vnd": said(10_000_000), "budget_scope": said("trip_total"),
        "lodging": said({"text": "Khách sạn Colline", "lat": 11.94, "lng": 108.43, "kind": "address"})}


def build(drop=(), **over):
    data = {k: v for k, v in FULL.items() if k not in drop}
    data.update(over)
    return TripState.model_validate(data)


def keys(st):
    return [k for k, _ in readiness.missing(st)]


# ---------- Q1-Q8: what "answered" means ----------

def test_q1_an_empty_trip_misses_all_seven_in_tab_order():
    assert keys(TripState()) == REQUIRED
    assert all(label and "_" not in label for _, label in readiness.missing(TripState()))  # Vietnamese, no ids


def test_q2_a_month_is_not_a_trip_date():
    st = build(drop=("start_date",), month=said(11))
    assert keys(st) == ["trip"]


def test_q2_dates_without_the_two_hours_are_not_enough():
    assert keys(build(drop=("checkin_at",))) == ["trip"]
    assert keys(build(drop=("checkout_at",))) == ["trip"]


def test_q2_a_flight_in_and_out_answers_the_two_hours():
    st = build(drop=("checkin_at", "checkout_at"),
               frame={"arrive": said({"at": "2026-11-20T09:30", "how": "plane"}),
                      "leave": said({"at": "2026-11-22T16:00", "how": "plane"})})
    assert keys(st) == []


def test_q3_a_guessed_required_answer_waits_for_one_tap():
    st = build(companions=said(["friends"], source="inferred"))
    assert keys(st) == ["companions"]
    st = build(pace=said("slow", source="profile"))
    assert keys(st) == ["pace"]


def test_q3_companions_need_a_head_count():
    assert keys(build(drop=("people",))) == ["companions"]


def test_q4_nothing_to_avoid_is_an_answer():
    assert "care" not in keys(build())


def test_q4_care_is_answered_by_a_recorded_limit_too():
    st = build(drop=("care",), hard=[{"feature": "steep_or_stairs", "op": "ne", "value": "present",
                                      "evidence": [{"turn": 1, "quote": "không leo dốc"}]}])
    assert "care" not in keys(st)


def test_q5_an_open_health_hint_keeps_care_missing_even_after_none():
    st = build(signals=[{"kind": "pregnant", "quote": "vợ bầu", "turn": 1}])
    assert "care" in keys(st)


def test_q6_no_budget_limit_is_an_answer():
    st = build(drop=("budget_vnd", "budget_scope"), budget_unlimited=said(True))
    assert "budget" not in keys(st)


def test_q7_an_amount_without_what_it_covers_is_not_enough():
    assert keys(build(drop=("budget_scope",))) == ["budget"]


def test_q8_a_complete_trip_misses_nothing_and_says_so_downstream():
    st = build()
    assert keys(st) == []
    assert compile_search_input(st).readiness.missing == ()


def test_q8_search_input_always_carries_readiness():
    si = compile_search_input(TripState())
    assert list(si.readiness.missing) == REQUIRED and si.readiness.readback_ok is False


# ---------- Q9-Q12: the read-back ----------

def test_q9_the_digest_is_stable_and_ignores_taste():
    a = compile_search_input(build())
    assert plan_digest(a) == plan_digest(compile_search_input(build()))
    tasted = build(soft={"noise=quiet": said("love")})
    assert plan_digest(compile_search_input(tasted)) == plan_digest(a)


@pytest.mark.parametrize("change", [
    {"pace": said("packed")}, {"checkin_at": said("10:00")}, {"mobility": said("car")},
    {"lodging": said({"text": "Homestay khác", "lat": 11.95, "lng": 108.44, "kind": "address"})},
    {"people": said(3)}, {"budget_vnd": said(20_000_000)},
    {"hard": [{"feature": "steep_or_stairs", "op": "ne", "value": "present",
               "evidence": [{"turn": 2, "quote": "không leo dốc"}]}]},
    {"frame": {"busy": [{"label": "nghỉ trưa", "kind": "rest", "where": "lodging", "start": "12:00", "end": "14:00",
                         "on": "all"}]}},
])
def test_q10_anything_that_changes_the_plan_changes_the_digest(change):
    assert plan_digest(compile_search_input(build(**change))) != plan_digest(compile_search_input(build()))


def test_q11_a_readback_holds_until_the_plan_inputs_change():
    st = build()
    st = with_meta(st, readback_digest=plan_digest(compile_search_input(st)))
    assert compile_search_input(st).readiness.readback_ok is True
    moved = st.model_copy(update={"checkin_at": TripState.model_validate({"checkin_at": said("09:00")}).checkin_at})
    assert compile_search_input(moved).readiness.readback_ok is False


def test_q12_the_readback_separates_said_guessed_default_and_points_to_a_tab():
    st = build(soft={"crowd=low": said("love", source="inferred")})
    rb = readback.build(compile_search_input(st))
    kinds = {line.kind for line in rb.lines}
    assert {"said", "guess", "default"} <= kinds
    assert all(line.tab in REQUIRED + ["more"] for line in rb.lines)
    text = " ".join(line.text for line in rb.lines)
    for leak in ("budget_scope", "checkin_at", "crowd=low", "source", "inferred"):
        assert leak not in text
    assert rb.digest == plan_digest(compile_search_input(st))


def test_q12_the_readback_shows_the_day_window_the_planner_will_use():
    st = build(frame={"arrive": said({"at": "2026-11-20T09:30", "how": "plane"})}, drop=("checkin_at",))
    text = " ".join(line.text for line in readback.build(compile_search_input(st)).lines)
    assert "10:45" in text and "9:30" in text


# ---------- Q13: a deck tap is applied by code, with no model call ----------

@pytest.fixture
def engine(catalog, cfg, tmp_path):
    chat = ScriptedChat(error=AgentError("the model must not be called for a tap"))
    return Engine(catalog, cfg, SessionStore(tmp_path), chat, today=lambda: date(2026, 10, 15)), chat


def tap(e, sid, answers):
    events = []
    e.turn(sid, TurnInput(kind="deck", answers=answers), lambda ev, d: events.append((ev, d)))
    return events


def test_q13_required_tabs_are_written_as_the_users_answers_then_read_by_the_agent(engine):
    e, chat = engine
    sid = e.create("first", "nothing")["id"]
    e.chat = chat = ScriptedChat(say("Rõ rồi."))
    tap(e, sid, {"trip.dates": "2026-11-20..2026-11-22", "trip.start": "10:00", "trip.end": "15:00",
                 "companions.who": ["partner"], "companions.people": "2", "mobility": ["car_hired"],
                 "care": ["none"], "pace": ["slow"], "budget.amount": "10000000", "budget.scope": ["trip_total"]})
    st = e.store.get(sid).state
    assert chat.calls == 1  # The agent reacts after code writes every answer.
    assert e.load(sid)["card"]["qid"] == "conversation"
    assert (st.start_date.value, st.days.value, st.checkin_at.value, st.checkout_at.value) == (
        date(2026, 11, 20), 3, "10:00", "15:00")
    assert (st.mobility.value, st.driver.value, st.pace.value, st.care.value) == ("car", "hired", "slow", "none")
    assert all(getattr(st, f).source == "user" for f in ("start_date", "mobility", "pace", "people", "budget_vnd"))
    assert keys(st) == ["lodging"]


def test_q13_a_tap_answer_is_fast(engine):
    e, _ = engine
    sid = e.create("first", "nothing")["id"]
    t0 = time.perf_counter()
    tap(e, sid, {"pace": ["normal"]})
    assert time.perf_counter() - t0 < 0.15


def test_q13_a_tap_can_never_write_a_value_outside_the_tab(engine):
    e, _ = engine
    sid = e.create("first", "nothing")["id"]
    tap(e, sid, {"pace": ["very_fast"], "mobility": ["helicopter"]})
    st = e.store.get(sid).state
    assert not st.pace.known and not st.mobility.known


def test_q13_readback_ok_stores_the_current_digest_without_the_model(engine):
    e, chat = engine
    sid = e.create("first", "nothing")["id"]
    s = e.store.get(sid)
    s.state = build()
    e.store.save(s)
    e.turn(sid, TurnInput(kind="readback_ok"), lambda *_: None)
    st = e.store.get(sid).state
    assert chat.calls == 0 and compile_search_input(st).readiness.readback_ok is True


def test_q13_readback_ok_is_refused_while_answers_are_missing(engine):
    e, _ = engine
    sid = e.create("first", "nothing")["id"]
    e.turn(sid, TurnInput(kind="readback_ok"), lambda *_: None)
    assert e.store.get(sid).state.meta.readback_digest is None
