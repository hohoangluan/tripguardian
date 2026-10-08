from datetime import date

import pytest
from trip_fixtures import FakeAgent

from trip.agent import AgentError
from trip.api.engine import FALLBACK_SAY, Engine, TurnInput
from trip.infrastructure.sessions import SessionStore


def plan(updates=(), say="Mình hiểu rồi.", qid="", kind="ask"):
    return {"say": say, "updates": list(updates),
            "next": {"kind": kind, "qid": qid, "custom_text": "", "custom_chips": [], "reason": ""}}


@pytest.fixture
def make(catalog, cfg, tmp_path):
    def build(agent=None, root=tmp_path):
        return Engine(catalog, cfg, SessionStore(root), agent or FakeAgent(error=AgentError("down")),
                      today=lambda: date(2026, 10, 2))
    return build


def run(engine, sid, **inp):
    events = []
    engine.turn(sid, TurnInput(**inp), lambda e, d: events.append((e, d)))
    return events


def names(events):
    return [e for e, _ in events]


def answer_frame(e, sid):
    return run(e, sid, kind="text", text="3 ngày đi một mình bằng ô tô")


def test_create_opens_with_an_open_frame_question(make):
    v = make().create("first", "nothing")
    assert v["card"]["qid"] == "frame" and v["card"]["chips"] == [] and v["card"]["input"] == "text"
    assert v["transcript"][0]["role"] == "agent"


def test_chip_answer_needs_no_agent(make):
    agent = FakeAgent(error=AssertionError("must not be called"))
    e = make(agent)
    sid = e.create("first", "nothing")["id"]
    ev = answer_frame(e, sid)  # days, companions and mobility only: settled without the agent
    assert names(ev) == ["preview", "say", "state", "card"] and ev[-1][1]["qid"] == "dates"
    assert all(set(c) == {"id", "label", "row"} for c in ev[-1][1]["chips"])
    ev = run(e, sid, kind="answer", qid="dates", chips=("undecided",))
    assert names(ev) == ["state", "card"] and agent.calls == 0


def test_text_alone_on_a_chip_card_is_a_text_turn(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    answer_frame(e, sid)
    ev = run(e, sid, kind="answer", qid="dates", text="tầm giữa tháng 12")
    assert names(ev)[0] == "preview" and e.store.get(sid).state.month.value == 12


def test_text_turn_streams_say_then_state_then_card(make):
    agent = FakeAgent(plan(updates=[{"field": "days", "op": "set", "value": "3", "quote": "3 ngày", "how": "said"}]),
                      chunks=("Mình ", "hiểu rồi."))
    e = make(agent)
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi 3 ngày muốn chill")
    assert names(ev) == ["preview", "say", "say", "state", "card"]
    assert ev[3][1]["understanding"]["trip"][0]["value"] == 3
    messages = agent.fields["messages"]
    assert messages[0].type == "system"
    assert messages[-2].role == "developer" and "CURRENT CONTEXT" in messages[-2].content
    assert messages[-1].type == "human" and messages[-1].content == "đi 3 ngày muốn chill"


def test_agent_context_keeps_an_append_only_conversation_prefix(make):
    agent = FakeAgent(plan())
    e = make(agent)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi 3 ngày muốn chill")
    first = agent.fields["messages"]
    run(e, sid, kind="text", text="đi cùng bạn bè")
    second = agent.fields["messages"]
    assert second[0] == first[0]
    assert [m for m in first[1:-2]] == second[1:len(first) - 2]
    assert second[-1].type == "human" and second[-1].content == "đi cùng bạn bè"


def test_agent_failure_falls_back_to_policy(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi 3 ngày bằng xe máy, muốn chill")
    assert ("say", {"replace": FALLBACK_SAY}) in ev and names(ev)[-1] == "card"
    trip = {r["target"]: r["value"] for r in ev[-2][1]["understanding"]["trip"]}
    assert trip == {"days": 3, "mobility": "motorbike"}


def test_text_only_user_gets_missing_fields_one_by_one(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi 3 ngày bằng xe máy")
    assert ev[-1][1]["qid"] == "companions"


def test_show_with_pending_safety_returns_that_question(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="mẹ đau gối")
    ev = run(e, sid, kind="show")
    assert names(ev) == ["say", "card"] and ev[1][1]["qid"] == "c_effort"


def test_conversation_completes_without_the_agent(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="3 ngày với bố mẹ, đi ô tô")
    for _ in range(15):
        c = e.load(sid)["card"]
        if c["qid"] in ("ready", "show_first"):
            break
        first = [x["id"] for x in c["chips"]][:1]
        run(e, sid, kind="answer", qid=c["qid"], chips=tuple(first or ["skip"]))
    ev = run(e, sid, kind="answer", qid=c["qid"], chips=("show",))
    assert names(ev) == ["done"] and ev[0][1]["search_input"]["context"]["days"] == 3


def test_removing_a_required_value_brings_its_question_back(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    answer_frame(e, sid)
    ev = run(e, sid, kind="edit", target="mobility", value=None)
    assert names(ev) == ["state", "card"] and ev[1][1]["qid"] == "mobility"


def test_edit_soft_and_bad_value(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="edit", target="soft:noise=quiet", value="love")
    assert e.load(sid)["understanding"]["soft"][0]["key"] == "noise=quiet"
    run(e, sid, kind="edit", target="soft:noise=quiet", value=None)
    assert e.load(sid)["understanding"]["soft"] == []
    assert names(run(e, sid, kind="edit", target="days", value="mười"))[0] == "error"


def test_stale_answer_is_rejected(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="answer", qid="pace", chips=("slow",))
    assert names(ev) == ["error", "card"]


def test_session_survives_restart(make, tmp_path):
    sid = make().create("returning", "saved")["id"]
    answer_frame(make(), sid)
    v = make().load(sid)
    assert v["card"]["qid"] == "dates" and [t["role"] for t in v["transcript"]] == ["agent", "agent", "user", "agent"]


def test_unknown_session_raises(make):
    with pytest.raises(KeyError):
        make().load("0123456789ab")


def test_keyword_guesses_are_marked_as_inferred(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi 3 ngày bằng xe máy")
    assert all(r["mark"] for r in ev[-2][1]["understanding"]["trip"])


def test_client_gone_mid_turn_still_applies_and_saves_the_turn(make):
    e = make(FakeAgent(plan(updates=[{"field": "days", "op": "set", "value": "3", "quote": "3 ngày", "how": "said"}]),
                       chunks=("Mình ",)))
    sid = e.create("first", "nothing")["id"]

    def emit(event, data):
        if event == "say":
            raise BrokenPipeError("client went away")
    e.turn(sid, TurnInput(kind="text", text="đi 3 ngày"), emit)
    v = make().load(sid)
    assert v["understanding"]["trip"][0]["value"] == 3 and v["card"]["qid"] == "companions"


def test_text_reply_to_a_tier_one_card_that_changes_nothing_asks_for_a_chip(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="mẹ đau gối")
    ev = run(e, sid, kind="text", text="không sao đâu")
    says = [d.get("replace", "") for n, d in ev if n == "say"]
    assert ev[-1][1]["qid"] == "c_effort" and any("chọn một ý" in s for s in says)


def test_off_topic_text_keeps_the_open_card(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="Đà Lạt có lạnh không?")
    assert ev[-1][1]["qid"] == "frame" and "frame" not in e.store.get(sid).state.meta.asked


def test_off_topic_text_on_an_adaptive_card_costs_no_question(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    answer_frame(e, sid)
    run(e, sid, kind="answer", qid="dates", value="2026-12-12")
    before = e.store.get(sid)
    qid, adaptive = before.card.qid, before.state.meta.adaptive_turns
    assert before.card.tier >= 2
    ev = run(e, sid, kind="text", text="Đà Lạt có lạnh không?")
    st = e.store.get(sid).state
    assert ev[-1][1]["qid"] == qid and qid not in st.meta.asked and st.meta.adaptive_turns == adaptive


def test_a_card_stays_open_through_one_off_topic_message_only(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="Đà Lạt có lạnh không?")
    run(e, sid, kind="text", text="ở đó có gì vui không?")
    assert "frame" in e.store.get(sid).state.meta.asked


@pytest.mark.parametrize("agent", [None, FakeAgent(plan(updates=[
    {"field": "mobility", "op": "set", "value": "car", "quote": "ô tô", "how": "said"}]))])
def test_text_sent_with_chips_wins_a_conflict_and_says_so(make, agent):
    e = make(agent)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="3 ngày đi một mình")
    assert e.load(sid)["card"]["qid"] == "mobility"
    ev = run(e, sid, kind="answer", qid="mobility", chips=("mobility:motorbike",), text="à thật ra đi ô tô")
    says = [d.get("replace", "") for n, d in ev if n == "say"]
    assert e.store.get(sid).state.mobility.value == "car"
    assert any("câu bạn gõ" in s and "ô tô" in s for s in says)


def to_purpose(e, sid):
    answer_frame(e, sid)
    run(e, sid, kind="answer", qid="dates", value="2026-12-12")
    assert e.load(sid)["card"]["qid"] == "purpose"


def test_typing_a_chip_label_answers_the_card_without_the_agent(make):
    agent = FakeAgent(error=AssertionError("must not be called"))
    e = make(agent)
    sid = e.create("first", "nothing")["id"]
    to_purpose(e, sid)
    run(e, sid, kind="text", text="Nghỉ ngơi nhé")
    s = e.store.get(sid)
    assert s.state.purpose.value == "relax" and "purpose" in s.state.meta.asked and agent.calls == 0
    assert any("heuristic:chip_echo" in t["text"] for t in s.transcript if t["role"] == "system")


def test_a_typed_exit_skips_the_card_without_the_agent(make):
    agent = FakeAgent(error=AssertionError("must not be called"))
    e = make(agent)
    sid = e.create("first", "nothing")["id"]
    to_purpose(e, sid)
    run(e, sid, kind="text", text="bỏ qua")
    assert "purpose" in e.store.get(sid).state.meta.skipped and agent.calls == 0


def test_a_chip_label_inside_a_longer_message_goes_to_the_agent(make):
    agent = FakeAgent(plan())
    e = make(agent)
    sid = e.create("first", "nothing")["id"]
    to_purpose(e, sid)
    run(e, sid, kind="text", text="không nghỉ ngơi")
    assert agent.calls == 1


def test_typing_the_safe_answer_closes_the_safety_card(make):
    agent = FakeAgent(error=AgentError("down"))
    e = make(agent)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="mẹ đau gối")
    assert e.load(sid)["card"]["qid"] == "c_effort"
    calls = agent.calls
    run(e, sid, kind="text", text="đi lại bình thường")
    assert e.load(sid)["card"]["qid"] != "c_effort" and agent.calls == calls


def test_show_with_a_missing_trip_field_does_not_talk_about_safety(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="show")
    assert ev[0] == ("say", {"replace": "Mình cần biết thêm điều này trước khi tìm chỗ."}) and ev[1][1]["qid"] == "frame"


def test_filling_the_asked_field_in_the_panel_moves_the_card_on(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    answer_frame(e, sid)
    assert e.load(sid)["card"]["qid"] == "dates"
    ev = run(e, sid, kind="edit", target="start_date", value="2026-12-12")
    assert names(ev) == ["state", "card"] and ev[1][1]["qid"] != "dates"


@pytest.fixture
def ready_engine(make):
    """A session that already reached "show": its Search Input was compiled once."""
    e = make()
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="3 ngày với bố mẹ, đi ô tô")
    for _ in range(15):
        c = e.load(sid)["card"]
        if c["qid"] in ("ready", "show_first"):
            break
        first = [x["id"] for x in c["chips"]][:1]
        run(e, sid, kind="answer", qid=c["qid"], chips=tuple(first or ["skip"]))
    assert names(run(e, sid, kind="answer", qid=c["qid"], chips=("show",))) == ["done"]
    return e, sid


def test_refine_updates_the_state_and_emits_done_without_a_card(ready_engine):
    e, sid = ready_engine  # a session that already reached "show"
    events = []
    e.agent = FakeAgent({"say": "Mình ưu tiên chỗ yên tĩnh.", "updates": [
        {"field": "soft", "op": "add", "value": "noise=quiet:love", "quote": "yên tĩnh hơn", "how": "said"}],
        "next": {"kind": "stop", "qid": "", "custom_text": "", "custom_chips": [], "reason": ""}})
    e.refine(sid, "muốn yên tĩnh hơn", lambda ev, d: events.append((ev, d)))
    names_ = [ev for ev, _ in events]
    assert "done" in names_ and "card" not in names_
    done = dict(events)["done"]
    assert any(w["feature"] == "noise" for w in done["search_input"]["soft_weights"])


def test_refine_never_ends_its_reply_with_a_question_no_card_will_answer(ready_engine):
    e, sid = ready_engine
    events = []
    e.agent = FakeAgent({"say": "Mình ưu tiên chỗ yên tĩnh. Bạn muốn đi buổi sáng hay chiều?", "updates": [
        {"field": "soft", "op": "add", "value": "noise=quiet:love", "quote": "yên tĩnh hơn", "how": "said"}],
        "next": {"kind": "ask", "qid": "", "custom_text": "Bạn muốn đi buổi nào?", "custom_chips": ["Sáng", "Chiều"],
                 "reason": ""}})
    e.refine(sid, "muốn yên tĩnh hơn", lambda ev, d: events.append((ev, d)))
    said = [d for ev, d in events if ev == "say"]
    assert said[-1] == {"replace": "Mình ưu tiên chỗ yên tĩnh."}
