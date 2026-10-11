"""The user-driven mode bar: chat (plain words, no cards) and quiz (chip cards), sharing one Trip State."""

from datetime import date

from trip_fixtures import ScriptedChat, say

from trip.agent import AgentError
from trip.api.engine import DECLINE_SAY, Engine, TurnInput
from trip.infrastructure.sessions import SessionStore


def make_engine(catalog, cfg, tmp_path, chat=None):
    return Engine(catalog, cfg, SessionStore(tmp_path), chat or ScriptedChat(error=AgentError("down")),
                  today=lambda: date(2026, 10, 2))


def run(engine, sid, **inp):
    events = []
    engine.turn(sid, TurnInput(**inp), lambda e, d: events.append((e, d)))
    return events


def test_mode_bar_switches_both_ways_and_declines_the_open_card(catalog, cfg, tmp_path):
    e = make_engine(catalog, cfg, tmp_path)
    sid = e.create("first", "nothing")["id"]
    assert e.load(sid)["phase"] == "chat"
    run(e, sid, kind="to_quiz")
    assert e.load(sid)["phase"] == "quiz" and e.load(sid)["card"]["qid"] == "days"
    run(e, sid, kind="to_chat")
    v = e.load(sid)
    assert v["phase"] == "chat" and v["card"]["qid"] == "conversation"
    st = e.store.get(sid).state
    assert "days" in st.meta.asked and "Chuyến này bạn đi mấy ngày?" in st.meta.declined
    run(e, sid, kind="to_quiz")
    assert e.load(sid)["card"]["qid"] == "companions"  # days is never asked again in either mode


def test_switching_to_the_current_phase_just_reemits(catalog, cfg, tmp_path):
    e = make_engine(catalog, cfg, tmp_path)
    sid = e.create("first", "nothing")["id"]
    before = len(e.store.get(sid).transcript)
    run(e, sid, kind="to_chat")
    assert e.load(sid)["card"]["qid"] == "frame"
    assert len(e.store.get(sid).transcript) == before  # no marker, no decline


def test_chat_learning_is_visible_to_the_quiz(catalog, cfg, tmp_path):
    e = make_engine(catalog, cfg, tmp_path)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi 3 ngày")  # the agent is down: only the keyword rules write
    assert e.store.get(sid).state.days.value == 3
    run(e, sid, kind="to_quiz")
    assert e.load(sid)["card"]["qid"] == "nights"  # days is known: the quiz skips it


def test_quiz_learning_is_visible_to_the_chat(catalog, cfg, tmp_path):
    chat = ScriptedChat(say(""))
    e = make_engine(catalog, cfg, tmp_path, chat)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="to_quiz")
    run(e, sid, kind="answer", qid="days", chips=("days:3",))
    run(e, sid, kind="to_chat")
    run(e, sid, kind="text", text="ok")
    context = next(m["content"] for m in chat.seen[0][0] if m["content"].startswith("CURRENT CONTEXT"))
    assert '"days": {"value": 3' in context
    assert '"still_needed": {"companions": "đi cùng ai", "mobility": "đi lại bằng gì", "when": "ngày hoặc tháng đi"}' in context


def test_two_declines_in_a_row_marks_the_next_turn_stuck(catalog, cfg, tmp_path):
    e = make_engine(catalog, cfg, tmp_path)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="to_quiz")
    ev = run(e, sid, kind="answer", qid="days", chips=("skip",))
    assert next(d["replace"] for n, d in ev if n == "say") == DECLINE_SAY
    run(e, sid, kind="answer", qid="companions", chips=("unsure",))
    assert e.store.get(sid).state.meta.unsure_streak == 2
    run(e, sid, kind="text", text="không biết nữa")  # the agent is down: nothing is learned either
    st = e.store.get(sid).state
    assert st.meta.unsure_streak == 2 and st.meta.idle_streak == 1


def test_stuck_flag_reaches_the_agent(catalog, cfg, tmp_path):
    chat = ScriptedChat(error=AgentError("down"))  # seen is recorded before the error raises
    e = make_engine(catalog, cfg, tmp_path, chat)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="to_quiz")
    run(e, sid, kind="answer", qid="days", chips=("skip",))
    run(e, sid, kind="answer", qid="companions", chips=("skip",))
    run(e, sid, kind="text", text="không biết nữa")
    context = next(m["content"] for m in chat.seen[0][0] if m["content"].startswith("CURRENT CONTEXT"))
    assert '"stuck": true' in context


def test_quiz_exhaustion_goes_to_review(catalog, cfg, tmp_path):
    e = make_engine(catalog, cfg, tmp_path)
    sid = e.create("first", "nothing")["id"]
    for target, value in (("days", "3"), ("nights", "2"), ("companions", "solo"), ("arrival_mode", "self"),
                          ("mobility", "motorbike"), ("start_date", "2026-12-12"), ("lodging_booked", "no"),
                          ("checkin_at", "14:00"), ("checkout_at", "11:00"), ("purpose", "relax"),
                          ("crowd_tolerance", "avoid"), ("pace", "slow"), ("budget_vnd", "5000000"),
                          ("soft:scenic_view=present", "love")):
        run(e, sid, kind="edit", target=target, value=value)
    run(e, sid, kind="to_quiz")
    v = e.load(sid)
    assert v["phase"] == "review" and v["card"] is not None and v["card"]["qid"] == "review"
    assert [c["id"] for c in v["card"]["chips"]] == ["show"]  # an open chat box: type, or press show
