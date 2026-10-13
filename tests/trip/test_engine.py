from datetime import date

import pytest
from trip_fixtures import ScriptedChat, call, fact, reply, say

from trip.agent import AgentError
from trip.api.engine import (BUSY_SAY, DECLINE_SAY, FALLBACK_SAY, NOT_DONE_SAY, NODATA_SAY, NOTED_TEXT_SAY, PAST_DATE, REJECT_SAY, UNSURE_SAY, Engine,
                             TurnInput)
from trip.domain.card import OPENING
from trip.domain.state import with_meta
from trip.infrastructure.clef import ClefRoute
from trip.infrastructure.sessions import SessionStore


@pytest.fixture
def make(catalog, cfg, tmp_path):
    def build(chat=None, root=tmp_path, route=None):
        return Engine(catalog, cfg, SessionStore(root), chat or ScriptedChat(error=AgentError("down")),
                      today=lambda: date(2026, 10, 2), route=route)
    return build


def run(engine, sid, **inp):
    events = []
    engine.turn(sid, TurnInput(**inp), lambda e, d: events.append((e, d)))
    return events


def names(events):
    return [e for e, _ in events]


def test_create_opens_with_an_open_frame_question(make):
    v = make().create("first", "nothing")
    assert v["card"]["qid"] == "frame" and v["card"]["chips"] == [] and v["card"]["input"] == "text"


def test_a_turn_records_facts_then_asks_in_words_with_no_card(make):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày"), fact("mobility", "car", "ô tô"),
                              text="Mình ghi lại rồi. Bạn đi cùng ai?"), say(""))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="3 ngày đi một mình bằng ô tô")
    assert names(ev) == ["preview", "state", "say", "state", "card"]  # what the keywords read shows before the agent
    assert ("say", {"delta": "Mình ghi lại rồi. Bạn đi cùng ai?"}) in ev
    assert ev[-1][1]["qid"] == "conversation"  # chat asks in words, never cards
    st = e.store.get(sid).state
    assert st.days.value == 3 and st.mobility.value == "car"
    assert chat.calls == 2  # facts, then an empty reply ends the turn


def test_the_agent_sees_the_state_and_the_tools_it_may_call(make):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày"), text="Rõ rồi, bạn đi cùng ai?"), say(""),
                        reply(fact("companions", "friends", "bạn bè", op="add"), text="Ghi nhận nhé."), say(""))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi 3 ngày")
    run(e, sid, kind="text", text="bạn bè")
    messages, tool_names = chat.seen[2]
    assert tool_names == ["record_fact", "resolve_relative_date", "search_places", "search_features", "ask", "drop_refusal"]
    context = next(m["content"] for m in messages if m["content"].startswith("CURRENT CONTEXT"))
    assert '"still_needed": {"companions": "đi cùng ai", "mobility": "đi lại bằng gì", "when": "ngày hoặc tháng đi"}' in context
    assert '"phase": "chat"' in context and '"stuck": false' in context
    assert [m["role"] for m in messages[1:-2]] == ["assistant", "assistant", "user", "assistant"]
    assert e.store.get(sid).state.companions.value == frozenset({"friends"})


def test_a_wish_no_feature_expresses_keeps_the_agents_own_words(make):
    chat = ScriptedChat(reply(fact("unmapped", "chó", "muốn có chó", op="add"),
                              text="Mình ghi lại là bạn muốn có chó đi cùng. Chó là để chơi cùng ở nơi tham quan, hay bạn cần nơi cho thú cưng vào?"))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="mình muốn có chó")
    said = [t["text"] for t in e.store.get(sid).transcript if t["role"] == "agent"][-1]
    assert "muốn có chó" in said and "thú cưng" in said
    assert chat.calls == 1 and ev[-1][1]["qid"] == "conversation"  # chat stays chat: no auto-quiz
    assert [u.phrase for u in e.store.get(sid).state.unmapped] == ["chó"]


def test_a_lead_in_front_of_a_question_stays_in_the_chat(make):
    e = make(ScriptedChat(say("Tháng 12 Đà Lạt khá lạnh. Bạn đi mấy ngày?")))
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="tháng 12 lạnh không?")
    assert ("say", {"delta": "Tháng 12 Đà Lạt khá lạnh. Bạn đi mấy ngày?"}) in ev
    assert ev[-1][1]["qid"] == "conversation"  # chat asks in words, never cards


def test_one_flow_a_reply_that_asks_nothing_brings_the_next_quick_question(make):
    chat = ScriptedChat(say("Bạn đi mấy ngày nè?"),
                        reply(fact("unmapped", "bồn tắm", "bồn tắm", op="add")),  # an unmapped wish ...
                        say("Mình ghi lại mong muốn có bồn tắm."),                     # ... said back, asking nothing
                        say("Đà Lạt tháng 12 khá lạnh."))                              # a plain reply: no ask either
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    first = run(e, sid, kind="text", text="đi Đà Lạt")[-1][1]
    assert first["qid"] == "conversation"  # the agent asked in words: the text box is the answer
    for text in ("tôi muốn có bồn tắm", "tháng 12 lạnh không?"):
        card = run(e, sid, kind="text", text=text)[-1][1]
        assert card["qid"] == "days" and card["chips"], text  # told, nothing asked: the bank's next question
    assert e.store.get(sid).state.meta.phase == "quiz"


def test_a_reply_the_guard_refuses_becomes_an_honest_line_not_silence(make):
    e = make(ScriptedChat(say("Tháng 12 Đà Lạt khoảng 10-20 độ.")))  # numbers the user never said
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="tháng 12 lạnh không?")
    assert ("say", {"replace": UNSURE_SAY}) in ev


def test_clef_answers_off_topic_and_figure_questions_with_a_fixed_reply_and_the_agent_is_not_called(make):
    chat = ScriptedChat(reply(text="Bạn đi mấy ngày?"))
    routes = iter([ClefRoute(), ClefRoute(reject="off_topic"), ClefRoute(asks_data=True)])
    e = make(chat, route=lambda text, card, hist: next(routes))
    sid = e.create("first", "nothing")["id"]
    first = run(e, sid, kind="text", text="đi Đà Lạt")[-1][1]
    for text, fixed in (("giá bitcoin hôm nay", REJECT_SAY), ("vé vào cổng bao nhiêu", NODATA_SAY)):
        ev = run(e, sid, kind="text", text=text)
        assert ("say", {"replace": fixed}) in ev and ev[-1][1]["text"] == first["text"], text  # the open card stays
    assert e.store.get(sid).state.days.known is False  # the Agent starts next to Clef, but a fixed reply drops what it did


def test_a_clue_the_keyword_rules_read_is_never_rejected_and_a_failing_clef_is_ignored(make):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày"), text="Rõ rồi, bạn đi cùng ai?"), say(""))
    e = make(chat, route=lambda text, card, hist: ClefRoute(reject="off_topic", asks_data=True))
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi 3 ngày")  # "3 ngày" is a trip clue: the Agent still answers
    assert chat.calls == 2 and e.store.get(sid).state.days.value == 3


def test_an_answer_to_our_own_open_question_is_not_rejected_as_off_topic(make):
    chat = ScriptedChat(reply(fact("unmapped", "anh họ", "anh họ", op="add"),
                              text="Mình ghi lại là đi với anh họ. Kiểu bạn bè chill chung, hay kiểu gia đình?"),
                        reply(text="Rõ rồi, đi kiểu gia đình ha. Bạn đi mấy ngày?"))
    routes = iter([ClefRoute(), ClefRoute(reject="off_topic")])
    e = make(chat, route=lambda text, card, hist: next(routes))
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="mình muốn đi với anh họ")
    ev = run(e, sid, kind="text", text="anh họ mà thân thiết kiểu gia đình á")
    assert ("say", {"replace": REJECT_SAY}) not in ev and chat.calls == 2
    said = [t["text"] for t in e.store.get(sid).transcript if t["role"] == "agent"][-1]
    assert "mấy ngày" in said


def test_the_next_turn_sees_last_turn_tool_results_in_context(make):
    import json
    chat = ScriptedChat(reply(fact("companions", "friends", "anh họ", op="add")),
                        reply(fact("unmapped", "anh họ", "anh họ", op="add"),
                              text="Mình ghi lại là đi với anh họ. Kiểu bạn bè hay gia đình?"),
                        reply(text="Bạn đi mấy ngày?"))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="mình muốn đi với anh họ")
    run(e, sid, kind="text", text="kiểu gia đình á")
    messages = chat.seen[-1][0]
    ctx = json.loads(next(m["content"] for m in messages if m.get("content", "").startswith("CURRENT CONTEXT"))
                     .removeprefix("CURRENT CONTEXT\n"))
    assert ctx["previous_turn"]["unmapped"] == ["anh họ"]
    assert "companions" in ctx["previous_turn"]["refused"]


def test_a_date_that_frames_a_figure_question_does_not_stop_clef_from_answering_it(make):
    chat = ScriptedChat(reply(text="Bạn đi mấy ngày?"))
    e = make(chat, route=lambda text, card, hist: ClefRoute(asks_data=True))
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="tháng 12 ở đà lạt nhiệt độ bao nhiêu")
    assert ("say", {"replace": NODATA_SAY}) in ev and ev[-1][1]["qid"] == "conversation"  # no card from the Agent reaches the screen
    assert e.store.get(sid).state.month.value == 12  # the keyword rules already wrote the month


def test_an_open_question_in_words_stays_in_the_chat_with_a_free_text_box(make):
    e = make(ScriptedChat(say("Bạn hình dung chuyến này thế nào?")))
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi Đà Lạt")
    assert ev[-1][1]["qid"] == "conversation"  # not `ask:*`: chat never deals cards
    assert e.store.get(sid).transcript[-2]["text"] == "Bạn hình dung chuyến này thế nào?"


def test_a_quiz_chip_answer_writes_its_drafts_without_the_agent(make):
    e = make(ScriptedChat(error=AgentError("down")))
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi 3 ngày")
    run(e, sid, kind="to_quiz")
    assert e.load(sid)["card"]["qid"] == "companions"  # days is known (the nights follow from it): the quiz skips it
    ev = run(e, sid, kind="answer", qid="companions", chips=("who:friends",))
    assert e.store.get(sid).state.companions.value == frozenset({"friends"})
    assert ev[-1][1]["qid"] == "care"  # the answered card closes; the one open health / diet question comes next


def test_skipping_a_quiz_card_leaves_the_field_unknown_and_it_is_never_asked_again(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="to_quiz")
    assert e.load(sid)["card"]["qid"] == "days"
    ev = run(e, sid, kind="answer", qid="days", chips=("skip",))
    say = next(d["replace"] for n, d in ev if n == "say")
    assert say == DECLINE_SAY
    assert ev[-1][1]["qid"] == "companions"  # the quiz moves on (nights needs days)
    st = e.store.get(sid).state
    assert not st.days.known and "days" in st.meta.asked and "Bạn định đi mấy ngày mấy đêm?" in st.meta.declined
    assert [t["text"] for t in e.store.get(sid).transcript if t["role"] == "user"][-1] == "Bỏ qua"
    run(e, sid, kind="to_chat")
    assert "Bạn đi cùng ai?" in e.store.get(sid).state.meta.declined  # the open card counts as declined on switch
    run(e, sid, kind="to_quiz")
    assert e.load(sid)["card"]["qid"] == "arrival"  # days and companions are never asked again


def test_an_answered_quiz_card_closes_and_moves_on_without_the_agent(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi 3 ngày")
    run(e, sid, kind="to_quiz")
    ev = run(e, sid, kind="answer", qid="companions", chips=("who:friends",))
    st = e.store.get(sid).state
    assert not st.nights.known and st.companions.value == frozenset({"friends"})  # nights are never asked: days - 1 stands
    assert ev[-1][1]["qid"] == "care"
    ev = run(e, sid, kind="answer", qid="care", chips=("none",))
    assert ev[-1][1]["qid"] == "arrival"
    cards = [t["text"] for t in e.store.get(sid).transcript if t.get("kind") == "card"]
    assert cards.count("Bạn đi cùng ai?") == 1


def test_a_typed_answer_the_agent_records_keeps_the_chat_card_free(make):
    chat = ScriptedChat(say("Mấy giờ cũng được, bạn rời lúc mấy giờ?"),
                        reply(fact("checkout_at", "16:00", "4 giờ chiều")))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi 3 ngày")
    ev = run(e, sid, kind="text", text="khoảng 4 giờ chiều")
    assert e.store.get(sid).state.checkout_at.value == "16:00"
    assert ev[-1][1]["qid"] == "conversation"  # chat asks in words, never cards


def test_a_pressed_quiz_option_needs_no_agent_at_all(make):
    e = make(ScriptedChat(error=AgentError("down")))  # the quiz is deterministic: a dead agent changes nothing
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="to_quiz")
    ev = run(e, sid, kind="answer", qid="days", chips=("days:3",))
    assert e.store.get(sid).state.days.value == 3 and ev[-1][1]["qid"] == "companions"


def test_the_user_declining_gets_a_plain_text_reply_and_no_forced_question(make):
    chat = ScriptedChat(say("Dạ không sao, khi nào muốn thì nhắn mình nhé."))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="tôi không muốn đi")
    assert ev[-1][1]["qid"] == "conversation" and chat.calls == 1
    assert not e.store.get(sid).state.days.known


def test_the_agent_is_told_what_is_still_needed_and_the_view_says_when_next_is_allowed(make):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày"), text="Đi cùng ai?"))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi 3 ngày")
    context = next(m["content"] for m in chat.seen[0][0] if m["content"].startswith("CURRENT CONTEXT"))
    # the keyword rules already read "3 ngày": it is not asked again
    assert '"still_needed": {"companions": "đi cùng ai", "mobility": "đi lại bằng gì", "when": "ngày hoặc tháng đi"}' in context
    view = next(d for n, d in ev if n == "state")["understanding"]
    assert view["ready"] is True and [m["target"] for m in view["missing"]] == ["companions", "mobility", "when"]


def test_next_is_refused_until_the_minimum_is_known_then_it_compiles(make):
    e = make(ScriptedChat(reply(fact("days", "3", "3 ngày"), text="Đi cùng ai?")))
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi 3 ngày")
    ev = run(e, sid, kind="show")
    assert names(ev) == ["done"]
    assert e.load(sid)["card"] is None
    for field, value in (("companions", "partner"), ("mobility", "car")):
        run(e, sid, kind="edit", target=field, value=value)
    run(e, sid, kind="edit", target="month", value="12")
    view = e.load(sid)["understanding"]
    assert view["ready"] is True and view["missing"] == []
    ev = run(e, sid, kind="show")
    assert names(ev) == ["done"] and ev[0][1]["search_input"]["context"]["days"] == 3
    assert e.load(sid)["card"] is None


def test_a_refused_tool_call_is_corrected_inside_the_same_turn(make):
    chat = ScriptedChat(reply(fact("days", "9", "9 ngày")),  # not in the message: refused, the agent reads the error
                        reply(fact("days", "3", "3 ngày")), say(""))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi 3 ngày")
    assert chat.calls == 3 and e.store.get(sid).state.days.value == 3
    tool_result = next(m for m in chat.seen[1][0] if m["role"] == "tool")
    assert "error" in tool_result["content"]


def test_a_plain_reply_is_followed_by_the_next_quick_question(make):
    e = make(ScriptedChat(say("Đà Lạt tháng 12 khá lạnh, khoảng 14 độ.")))
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="tháng 12 lạnh không?")
    assert ev[-1][1]["qid"] == "days"  # "tháng 12" was read, so the trip is being told


def test_agent_failure_keeps_what_was_written_and_says_so(make):
    e = make(ScriptedChat(reply(fact("days", "3", "3 ngày"))))  # the second call finds the script empty
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi 3 ngày")
    assert ("say", {"replace": FALLBACK_SAY}) in ev and ev[-1][1]["qid"] == "conversation"
    assert e.store.get(sid).state.days.value == 3


def test_agent_down_still_applies_the_keyword_rules(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi 3 ngày bằng xe máy")
    assert all(r["mark"] for r in ev[-2][1]["understanding"]["trip"])  # shown with the pencil until confirmed


def test_next_stays_locked_while_a_health_hint_is_open(make):
    chat = ScriptedChat(reply(fact("signal", "knee", "đau gối", op="add"), text="Đi bộ được bao lâu?"))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="mẹ đau gối")
    for field, value in (("days", "3"), ("companions", "parents"), ("mobility", "car"), ("month", "12")):
        run(e, sid, kind="edit", target=field, value=value)
    assert "điều cần lưu ý về sức khỏe" in [m["label"] for m in e.load(sid)["understanding"]["missing"]]
    ev = run(e, sid, kind="show")
    assert names(ev) == ["done"]


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
    run(e, sid, kind="answer", qid="pace", chips=("slow",))  # an earlier card in the chat still counts
    assert e.store.get(sid).state.pace.value == "slow"
    assert names(run(e, sid, kind="answer", qid="pace", chips=("packed",))) == ["error", "card"]  # answered: gone


def test_session_survives_restart(make, tmp_path):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày"), text="Rõ rồi, bạn đi cùng ai?"), say(""))
    sid = make().create("returning", "saved")["id"]
    run(make(chat), sid, kind="text", text="đi 3 ngày")
    v = make().load(sid)
    assert v["card"]["qid"] == "conversation" and v["understanding"]["trip"][0]["value"] == 3
    assert v["transcript"][-1]["text"] == "Rõ rồi, bạn đi cùng ai?"


def test_unknown_session_raises(make):
    with pytest.raises(KeyError):
        make().load("0123456789ab")


def test_client_gone_mid_turn_still_applies_and_saves_the_turn(make):
    e = make(ScriptedChat(reply(fact("days", "3", "3 ngày"), text="Mình ")))
    sid = e.create("first", "nothing")["id"]

    def emit(event, data):
        if event == "say":
            raise BrokenPipeError("client went away")
    e.turn(sid, TurnInput(kind="text", text="đi 3 ngày"), emit)  # a closed tab must not leave the turn half applied
    assert make().load(sid)["understanding"]["trip"][0]["value"] == 3


def test_an_answer_is_chips_or_text_never_both():
    with pytest.raises(ValueError):
        TurnInput(kind="answer", qid="x", chips=("a",), text="b")


@pytest.fixture
def ready_engine(make):
    e = make(ScriptedChat(reply(fact("days", "3", "3 ngày"), fact("companions", "partner", "bồ", op="add"),
                                fact("mobility", "car", "ô tô"), fact("month", "12", "tháng 12"))))
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="3 ngày với bồ bằng ô tô tháng 12")
    assert names(run(e, sid, kind="show")) == ["done"]
    return e, sid


def test_refine_updates_the_state_and_emits_done_without_a_card(ready_engine):
    e, sid = ready_engine
    e.chat = ScriptedChat(reply(fact("soft", "noise=quiet:love", "yên tĩnh hơn", op="add"), text="Mình ưu tiên chỗ yên tĩnh."))
    events = []
    e.refine(sid, "muốn yên tĩnh hơn", lambda ev, d: events.append((ev, d)))
    assert "done" in names(events) and "card" not in names(events)
    done = dict(events)["done"]
    assert any(w["feature"] == "noise" for w in done["search_input"]["soft_weights"])
    assert e.chat.seen[0][1] == ["record_fact", "resolve_relative_date", "search_places", "search_features", "drop_refusal"]  # no asking


def test_refine_never_ends_its_reply_with_a_question_no_card_will_answer(ready_engine):
    e, sid = ready_engine
    e.chat = ScriptedChat(reply(fact("soft", "noise=quiet:love", "yên tĩnh hơn", op="add"),
                                text="Mình ưu tiên chỗ yên tĩnh. Bạn muốn đi buổi nào?"))
    events = []
    e.refine(sid, "muốn yên tĩnh hơn", lambda ev, d: events.append((ev, d)))
    assert [d for ev, d in events if ev == "say"][-1] == {"replace": "Mình ưu tiên chỗ yên tĩnh."}


class FakeJudge:
    def __init__(self, unsupported=False, bad=None, features=()):
        self._u, self._b, self._f = unsupported, bad, list(features)

    def unsupported(self, quote, claim):
        return self._u

    def bad_reply(self, say):
        return self._b

    def features(self, wish, features):
        return self._f


def judged(make, chat, judge, route=None):
    e = make(chat, route=route)
    e.judge = judge
    return e


def test_what_the_agent_did_next_to_a_clef_reject_is_dropped_and_not_shown(make):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày"), text="Mình ghi lại rồi."))
    e = make(chat, route=lambda text, card, hist: ClefRoute(asks_data=True))
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="vé vào cổng bao nhiêu")
    s = e.store.get(sid)
    assert ("say", {"replace": NODATA_SAY}) in ev and not any(d.get("delta") for k, d in ev if k == "say")
    assert not s.state.days.known and s.card.qid == "conversation"


def test_a_fact_whose_quote_does_not_say_it_is_refused_so_the_agent_can_correct_itself(make):
    chat = ScriptedChat(reply(fact("soft", "noise=quiet:love", "yên tĩnh", how="inferred")), reply(text="Bạn đi mấy ngày?"))
    e = judged(make, chat, FakeJudge(unsupported=True))
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="mình thích chỗ yên tĩnh")
    log = [t["text"] for t in e.store.get(sid).transcript if t["role"] == "system"][0]
    assert "clef_unsupported" in log and "record_fact soft=noise=quiet:love:error" in log


def test_a_reply_clef_finds_promising_results_is_replaced(make):
    chat = ScriptedChat(say("Mình sẽ gợi ý lịch trình ngay nhé"), say("Mình sẽ gợi ý ngay nhé"))  # the retry promises too
    e = judged(make, chat, FakeJudge(bad="promises results"))
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="chào")
    assert ("say", {"replace": NOTED_TEXT_SAY}) in ev  # nothing was asked: a pointer to the summary, not "chưa trả lời được"


def test_search_features_falls_back_to_clef_when_the_keywords_find_nothing(make):
    chat = ScriptedChat(reply(call("search_features", query="zzzz")), reply(text="Bạn đi mấy ngày?"))
    e = judged(make, chat, FakeJudge(features=["scenic_view"]))
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="zzzz")
    tool_msg = [m for m in chat.seen[1][0] if m["role"] == "tool"][0]
    assert "scenic_view" in tool_msg["content"]


def test_a_question_asked_right_after_a_refused_fact_is_fixed_in_words(make):
    chat = ScriptedChat(reply(fact("companions", "family", "gia đình"), text="Đi cùng ai nè?"),
                        reply(fact("companions", "parents", "bố mẹ", op="add")), say(""))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi với gia đình, bố mẹ")
    s = e.store.get(sid)
    assert chat.calls == 3 and "parents" in str(s.state.companions.value)
    assert ev[-1][1]["qid"] == "conversation"  # chat asks in words, never cards
    assert "resolve_refusal ['companions']" in [t["text"] for t in s.transcript if t["role"] == "system"][-1]


def test_a_refusal_is_resolved_then_the_question_is_said_in_words_and_the_quiz_card_stays(make):
    # Typed text on an open quick-reply card is a chat message: the refused fact is dropped, the question goes in plain
    # text, and the card above still answers.
    chat = ScriptedChat(reply(fact("companions", "family", "gia đình")),
                        reply(call("drop_refusal", field="companions")),
                        say("Nhà mình gồm những ai?"))
    e = make(chat)
    e.judge = FakeJudge()
    e.judge.clear_for_field = lambda text, label: False
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="to_quiz")
    run(e, sid, kind="answer", qid="days", chips=("days:3",))
    ev = run(e, sid, kind="text", text="đi với gia đình")
    assert chat.calls == 3 and ev[-1][1]["qid"] == "conversation"  # asked in words: the text box answers
    assert e.store.get(sid).transcript[-2]["text"] == "Nhà mình gồm những ai?"
    run(e, sid, kind="answer", qid="companions", chips=("who:parents",))
    assert e.store.get(sid).state.companions.value == frozenset({"parents"})


def test_the_start_date_question_is_a_calendar_and_a_picked_day_is_written_without_the_agent(make):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày"), fact("companions", "friends", "bạn bè", op="add"),
                              fact("mobility", "motorbike", "xe máy")), say(""))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi 3 ngày với bạn bè bằng xe máy")
    run(e, sid, kind="to_quiz")
    assert e.load(sid)["card"]["qid"] == "care"  # days and companions are known: the quiz skips them
    run(e, sid, kind="answer", qid="care", chips=("none",))
    run(e, sid, kind="answer", qid="arrival", chips=("self",))
    assert e.load(sid)["card"]["qid"] == "origin"  # where the trip starts from (home), asked of every trip
    run(e, sid, kind="answer", qid="origin",
        value='{"text": "Quận 1, Hồ Chí Minh", "lat": 10.77, "lng": 106.7, "province": "Hồ Chí Minh"}')
    card = e.load(sid)["card"]
    assert card["qid"] == "dates" and card["input"] == "date" and card["exits"] is True  # "Chưa chắc" is offered next to the calendar
    calls_before_picker = chat.calls
    assert names(run(e, sid, kind="answer", qid=card["qid"], value="2026-10-01")) == ["error"]  # before today
    assert ("error", {"message": PAST_DATE}) in run(e, sid, kind="answer", qid=card["qid"], value="2026-10-01")
    ev = run(e, sid, kind="answer", qid=card["qid"], value="2026-10-25")
    st = e.store.get(sid).state
    assert st.start_date.value == date(2026, 10, 25) and st.start_date.locked and chat.calls == calls_before_picker
    assert ev[-1][1]["qid"] == "lodging" and "25/10/2026" in next(d["replace"] for n, d in ev if n == "say")


def test_a_theme_card_writes_its_fixed_tastes_without_reading_a_sentence(make, cfg):
    themes = {"rain": {"title": "Chỗ trong nhà khi mưa", "say": "ưu tiên nơi trong nhà",
                       "soft": ["setting=indoor:love", "weather_exposed=sheltered:love"], "groups": ["chill", "sights"]}}
    chat = ScriptedChat()
    e = make(chat)
    e.cfg = cfg.__class__(**{**cfg.__dict__, "themes": themes})
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="theme", value="rain")
    st = e.store.get(sid).state
    assert {k: f.value for k, f in st.soft.items()} == {"setting=indoor": "love", "weather_exposed=sheltered": "love"}
    assert st.liked_groups.value == ("chill", "sights") and chat.calls == 0
    assert "Chỗ trong nhà khi mưa" in next(d["replace"] for n, d in ev if n == "say") and ev[-1][1]["qid"] == "days"
    assert e.load(sid)["transcript"][-2] == {"role": "user", "text": "Chỗ trong nhà khi mưa", "turn": 1, "kind": "theme"}
    assert names(run(e, sid, kind="theme", value="nope")) == ["error"]


def test_a_correction_in_a_later_turn_updates_the_budget_scope_even_if_the_agent_fails(make):
    # T-2: the user's correction is read by the keyword rules before the agent, so it is never lost.
    # Who goes and kinds of place are agent-only suggestions now: without the agent, people stays
    # unknown (no per-person split yet) and liked_groups stays empty.
    e = make()
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="Đi Đà Lạt 3 ngày với bạn gái, ngân sách khoảng 5 triệu")
    u = e.load(sid)["understanding"]
    assert u["budget_vnd"]["value"] == {"amount": 5_000_000, "scope": "trip_total", "guessed": True,
                                        "per_person_day": None} and u["budget_vnd"]["mark"]
    run(e, sid, kind="text", text="5 triệu là tổng cả chuyến cho 2 người nha… Mình cũng rất thích cà phê.")
    st = e.store.get(sid).state
    assert st.budget_scope.value == "trip_total" and st.people.value == 2 and not st.liked_groups.value
    assert e.load(sid)["understanding"]["budget_vnd"]["value"]["guessed"] is False


def test_a_correction_of_something_known_records_nothing_new_and_stays_in_chat(make):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày"), text="Rõ rồi."), say(""),
                        reply(fact("days", "3", "3 ngày")), say(""))  # recorded again, nothing new
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi 3 ngày")
    ev = run(e, sid, kind="text", text="đúng rồi 3 ngày nha")
    assert ev[-1][1]["qid"] == "conversation"  # no open question to keep: chat never deals cards
    assert e.store.get(sid).state.meta.idle_streak == 1  # an adaptive turn that added nothing


def test_a_question_the_model_writes_as_plain_text_stays_in_the_chat(make):
    chat = ScriptedChat(say("Mình ghi rồi. Bạn muốn đi thong thả hay đi nhiều?"))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi 3 ngày")
    assert ev[-1][1]["qid"] == "conversation"  # chat asks in words: no card is made from the text
    assert e.store.get(sid).transcript[-2]["text"] == "Mình ghi rồi. Bạn muốn đi thong thả hay đi nhiều?"


def test_an_agent_that_uses_all_its_steps_without_replying_still_says_something(make):
    e = make(ScriptedChat(*[reply(call("search_features", query="chó")) for _ in range(6)]))
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="mình muốn có chó")
    assert ("say", {"replace": NOT_DONE_SAY}) in ev and ev[-1][1]["qid"] == "conversation"


def test_a_question_in_words_after_the_trip_was_told_is_kept_in_the_chat(make):
    e = make(ScriptedChat(reply(fact("days", "3", "3 ngày")), say("Ghi rồi."), say("Bạn đi vào tháng mấy?")))
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi 3 ngày")
    s = e.store.get(sid)
    s.state = with_meta(s.state, phase="quiz")  # the quiz phase: the trip is told, so no question card is asked in words
    e.store.save(s)
    ev = run(e, sid, kind="text", text="mình chưa rõ")
    assert ("say", {"replace": "Bạn đi vào tháng mấy?"}) not in ev
    assert e.store.get(sid).transcript[-2]["text"] == "Bạn đi vào tháng mấy?"


def test_a_group_the_quote_does_not_name_is_refused_and_kept_as_unmapped(make):
    chat = ScriptedChat(reply(fact("companions", "friends", "họ hàng xa", op="add")),
                        reply(fact("unmapped", "họ hàng xa", "họ hàng xa", op="add"),
                              text="Mình ghi lại là đi với họ hàng xa. Kiểu bạn bè đi chill chung, hay kiểu gia đình?"))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="tôi muốn đi với người họ hàng xa")
    s = e.store.get(sid)
    assert not s.state.companions.known
    assert [u.phrase for u in s.state.unmapped] == ["họ hàng xa"]
    said = [t["text"] for t in s.transcript if t["role"] == "agent"][-1]
    assert "kiểu gia đình" in said  # the agent's own consultative question stays: no template speaks for it


def test_an_unmapped_group_is_confirmed_once_the_user_names_it(make):
    chat = ScriptedChat(reply(fact("companions", "friends", "họ hàng xa", op="add")),
                        reply(fact("unmapped", "họ hàng xa", "họ hàng xa", op="add")),
                        reply(text="Mình ghi lại là đi với họ hàng xa. Kiểu bạn bè hay gia đình?"),
                        reply(fact("companions", "friends", "kiểu bạn bè đi", op="add")), say("Bạn đi mấy ngày?"))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="tôi muốn đi với người họ hàng xa")
    run(e, sid, kind="text", text="kiểu bạn bè đi")
    s = e.store.get(sid)
    assert s.state.companions.known and s.state.companions.source == "user"
    assert all(not u.group for u in s.state.unmapped)


def test_an_unmapped_group_close_to_a_value_keeps_the_agents_own_confirming_question(make):
    chat = ScriptedChat(reply(fact("companions", "friends", "họ hàng xa", op="add")),
                        reply(fact("unmapped", "kiểu bạn đi", "kiểu bạn đi", op="add"),
                              text="Mình ghi lại là đi kiểu bạn. Có phải ý bạn là đi như bạn bè không?"))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="tôi đi với anh họ kiểu bạn đi")
    said = [t["text"] for t in e.store.get(sid).transcript if t["role"] == "agent"][-1]
    assert "như bạn bè không?" in said


def test_an_agent_that_already_asks_keeps_its_own_question(make):
    chat = ScriptedChat(reply(fact("unmapped", "anh họ", "anh họ", op="add"),
                              text="Anh họ là đi kiểu bạn bè chill chung, hay kiểu gia đình có người lớn cần lo?"))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="tôi muốn đi với anh họ của tôi")
    s = e.store.get(sid)
    said = [t["text"] for t in s.transcript if t["role"] == "agent"][-1]
    assert "kiểu gia đình" in said
    assert [u.phrase for u in s.state.unmapped] == ["anh họ"]


def test_a_turn_that_runs_out_of_steps_after_a_write_says_what_was_written(make):
    chat = ScriptedChat(*[reply(fact("companions", "friends", "bạn bè", op="add")) for _ in range(9)])
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="tôi muốn đi với anh họ theo kiểu bạn bè đó")
    said = [t["text"] for t in e.store.get(sid).transcript if t["role"] == "agent"][-1]
    assert "người đi cùng" in said


def test_a_turn_that_writes_facts_and_no_reply_says_what_was_written(make):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày")), reply(text=""))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi 3 ngày")
    said = [t["text"] for t in e.store.get(sid).transcript if t["role"] == "agent"]
    assert said and "số ngày" in said[-1]
