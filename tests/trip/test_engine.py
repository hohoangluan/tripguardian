from datetime import date

import pytest
from trip_fixtures import ScriptedChat, ask, call, fact, reply, say

from trip.agent import AgentError
from trip.api.engine import (BUSY_SAY, DECLINE_SAY, FALLBACK_SAY, NODATA_SAY, NOTED_TEXT_SAY, PAST_DATE, REJECT_SAY, UNSURE_SAY, Engine,
                             TurnInput)
from trip.infrastructure.clef import ClefRoute
from trip.domain.state import pending_signals
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


def test_a_turn_records_facts_then_shows_the_card_the_agent_asked(make):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày"), fact("mobility", "car", "ô tô"),
                              ask("Bạn đi cùng ai?", "Một mình", "Người yêu", "Bạn bè"), text="Mình ghi lại rồi."))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="3 ngày đi một mình bằng ô tô")
    assert names(ev) == ["preview", "state", "say", "state", "card"]  # what the keywords read shows before the agent
    card = ev[-1][1]
    assert card["text"] == "Bạn đi cùng ai?" and [c["label"] for c in card["chips"]] == ["Một mình", "Người yêu", "Bạn bè"]
    st = e.store.get(sid).state
    assert st.days.value == 3 and st.mobility.value == "car"
    assert chat.calls == 1


def test_the_agent_sees_the_state_and_the_tools_it_may_call(make):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày"), ask("Đi cùng ai?", "Một mình", "Bạn bè")),
                        reply(ask("Đi bằng gì?", "Xe máy", "Ô tô")))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi 3 ngày")
    run(e, sid, kind="text", text="bạn bè")
    messages, tool_names = chat.seen[1]
    assert chat.seen[0][1][-3:] == ["ask_choice", "ask_text", "open_quiz"]  # opening turn may ask or open the quiz
    assert tool_names == ["record_fact", "resolve_relative_date", "search_places", "search_features"]
    context = next(m["content"] for m in messages if m["content"].startswith("CURRENT CONTEXT"))
    assert '"days"' in context and "Đi cùng ai?" in context
    assert [m["role"] for m in messages[1:-2]] == ["assistant", "assistant", "user", "assistant"]


def test_a_wish_no_feature_expresses_ends_the_turn_with_a_fixed_reply_and_no_more_model_calls(make):
    chat = ScriptedChat(reply(fact("unmapped", "chó", "muốn có chó", op="add"),
                              text="Đà Lạt có nhiều nông trại cún!"),
                        reply(ask("Bạn đi mấy ngày?", "1-2", "3-4")))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="mình muốn có chó")
    fixed = next(d["replace"] for n, d in ev if n == "say" and "replace" in d)
    assert "“muốn có chó”" in fixed and "chưa dùng được" in fixed and "nông trại" not in fixed
    assert chat.calls == 1 and ev[-1][1]["qid"] == "days"  # the trip was told: the chip cards ask the rest
    assert [u.phrase for u in e.store.get(sid).state.unmapped] == ["chó"]


def test_a_card_text_is_only_the_question_the_rest_goes_to_the_chat(make):
    e = make(ScriptedChat(reply(ask("Tháng 12 Đà Lạt khá lạnh. Bạn đi mấy ngày?", "1-2", "3-4"), text="Mình hiểu rồi.")))
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="tháng 12 lạnh không?")
    assert ev[-1][1]["text"] == "Bạn đi mấy ngày?"
    assert ("say", {"replace": "Mình hiểu rồi. Tháng 12 Đà Lạt khá lạnh."}) in ev


def test_after_the_opening_question_a_message_that_asks_nothing_leads_to_the_chip_cards(make):
    chat = ScriptedChat(reply(ask("Bạn đi mấy ngày?", "1-2", "3-4")),
                        reply(fact("unmapped", "bồn tắm", "bồn tắm", op="add")))  # an unmapped wish: fixed reply, no ask
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    assert run(e, sid, kind="text", text="đi Đà Lạt")[-1][1]["text"] == "Bạn đi mấy ngày?"
    card = run(e, sid, kind="text", text="tôi muốn có bồn tắm")[-1][1]
    assert card["qid"] == "days" and e.load(sid)["phase"] == "quiz"  # a chip card, never an empty box


def test_a_reply_the_guard_refuses_becomes_an_honest_line_not_silence(make):
    e = make(ScriptedChat(say("Tháng 12 Đà Lạt khoảng 10-20 độ.")))  # numbers the user never said
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="tháng 12 lạnh không?")
    assert ("say", {"replace": UNSURE_SAY}) in ev


def test_clef_answers_off_topic_and_figure_questions_with_a_fixed_reply_and_the_agent_is_not_called(make):
    chat = ScriptedChat(reply(ask("Bạn đi mấy ngày?", "1-2", "3-4")))
    routes = iter([ClefRoute(), ClefRoute(reject="off_topic"), ClefRoute(asks_data=True)])
    e = make(chat, route=lambda text, card: next(routes))
    sid = e.create("first", "nothing")["id"]
    first = run(e, sid, kind="text", text="đi Đà Lạt")[-1][1]
    for text, fixed in (("giá bitcoin hôm nay", REJECT_SAY), ("vé vào cổng bao nhiêu", NODATA_SAY)):
        ev = run(e, sid, kind="text", text=text)
        assert ("say", {"replace": fixed}) in ev and ev[-1][1]["text"] == first["text"], text  # the open card stays
    assert e.store.get(sid).state.days.known is False  # the Agent starts next to Clef, but a fixed reply drops what it did


def test_a_clue_the_keyword_rules_read_is_never_rejected_and_a_failing_clef_is_ignored(make):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày"), ask("Đi cùng ai?", "Một mình", "Bạn bè")))
    e = make(chat, route=lambda text, card: ClefRoute(reject="off_topic", asks_data=True))
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi 3 ngày")  # "3 ngày" is a trip clue: the Agent still answers
    assert chat.calls == 1 and e.store.get(sid).state.days.value == 3


def test_a_date_that_frames_a_figure_question_does_not_stop_clef_from_answering_it(make):
    chat = ScriptedChat(reply(ask("Bạn đi mấy ngày?", "1-2", "3-4")))
    e = make(chat, route=lambda text, card: ClefRoute(asks_data=True))
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="tháng 12 ở đà lạt nhiệt độ bao nhiêu")
    assert ("say", {"replace": NODATA_SAY}) in ev and ev[-1][1]["qid"] == "conversation"  # no card from the Agent reaches the screen
    assert e.store.get(sid).state.month.value == 12  # the keyword rules already wrote the month


def test_an_open_question_is_a_card_with_the_question_as_its_title_and_a_free_text_box(make):
    e = make(ScriptedChat(reply(ask("Bạn hình dung chuyến này thế nào?"), text="Mình ghi lại rồi.")))
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi Đà Lạt")
    card = ev[-1][1]
    assert card["text"] == "Bạn hình dung chuyến này thế nào?" and card["chips"] == [] and card["input"] == "text"
    assert card["qid"].startswith("ask:")  # not `conversation`: the web draws that one as an untitled box
    assert e.store.get(sid).transcript[-2]["text"] == "Mình ghi lại rồi."  # the model's own words stay a chat message


def test_an_answer_from_a_card_goes_to_the_agent_as_text(make):
    chat = ScriptedChat(reply(ask("Đi cùng ai?", "Một mình", "Bạn bè")),
                        reply(fact("companions", "friends", "Bạn bè", op="add")))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    card = run(e, sid, kind="text", text="đi 3 ngày")[-1][1]
    run(e, sid, kind="answer", qid=card["qid"], chips=("c1",))
    assert chat.seen[1][0][-1] == {"role": "user", "content": "Bạn bè"}
    assert e.store.get(sid).state.companions.value == frozenset({"friends"})


def test_skipping_a_card_leaves_the_field_unknown_without_the_agent_and_it_is_never_asked_again(make):
    chat = ScriptedChat(reply(ask("Đi cùng ai?", "Một mình", "Bạn bè")),
                        reply(ask("Đi cùng ai?", "Một mình", "Bạn bè")),  # asked again: refused, the agent asks another
                        reply(ask("Đi bằng gì?", "Xe máy", "Ô tô")))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    card = run(e, sid, kind="text", text="đi Đà Lạt")[-1][1]
    ev = run(e, sid, kind="answer", qid=card["qid"], chips=("skip",))
    say = next(d["replace"] for n, d in ev if n == "say")
    assert chat.calls == 1 and say == DECLINE_SAY  # instant
    assert ev[-1][1]["qid"] == "days" and e.load(sid)["phase"] == "quiz"  # the chip cards ask the rest
    st = e.store.get(sid).state
    assert not st.companions.known and st.meta.declined == ("Đi cùng ai?",)
    assert [t["text"] for t in e.store.get(sid).transcript if t["role"] == "user"][-1] == "Bỏ qua"


def test_an_answered_card_closes_and_is_not_asked_again_when_the_agent_asks_nothing(make):
    # T-3: the agent recorded the answer but asked nothing new; the old question must not come back
    chat = ScriptedChat(reply(ask("Ngày cuối bạn rời Đà Lạt lúc mấy giờ?", "Buổi sáng", "Buổi chiều (12h - 17h)")),
                        reply(fact("checkout_at", "14:30", "Buổi chiều (12h - 17h)", how="inferred")), say("Mình ghi rồi."))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    card = run(e, sid, kind="text", text="đi 3 ngày 2 đêm")[-1][1]
    ev = run(e, sid, kind="answer", qid=card["qid"], chips=("c1",))
    assert ev[-1][1]["qid"] == "companions" and e.store.get(sid).state.checkout_at.value == "14:30"
    cards = [t["text"] for t in e.store.get(sid).transcript if t.get("kind") == "card"]
    assert cards.count("Ngày cuối bạn rời Đà Lạt lúc mấy giờ?") == 1


def test_a_typed_answer_the_agent_records_closes_the_open_card(make):
    chat = ScriptedChat(reply(ask("Ngày cuối bạn rời Đà Lạt lúc mấy giờ?", "Sáng", "Chiều")),
                        reply(fact("checkout_at", "16:00", "4 giờ chiều")))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi 3 ngày 2 đêm")
    ev = run(e, sid, kind="text", text="khoảng 4 giờ chiều")
    assert ev[-1][1]["qid"] == "companions"


def test_a_pressed_option_the_agent_could_not_read_keeps_the_card_and_never_blames_the_typing(make):
    chat = ScriptedChat(reply(ask("Đi cùng ai?", "Một mình", "Bạn bè")))  # then the script ends: AgentError
    routes = []
    e = make(chat, route=lambda text, card: routes.append(text) or ClefRoute())
    sid = e.create("first", "nothing")["id"]
    card = run(e, sid, kind="text", text="đi Đà Lạt")[-1][1]
    ev = run(e, sid, kind="answer", qid=card["qid"], chips=("c1",))
    assert ("say", {"replace": BUSY_SAY}) in ev and ev[-1][1]["text"] == "Đi cùng ai?"
    assert routes == ["đi Đà Lạt"]  # a pressed option is never sent to Clef


def test_the_user_declining_gets_a_plain_text_reply_and_no_forced_question(make):
    chat = ScriptedChat(say("Dạ không sao, khi nào muốn thì nhắn mình nhé."))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="tôi không muốn đi")
    assert ev[-1][1]["qid"] == "conversation" and chat.calls == 1
    assert not e.store.get(sid).state.days.known


def test_the_agent_is_told_what_is_still_needed_and_the_view_says_when_next_is_allowed(make):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày"), ask("Đi cùng ai?", "Một mình", "Bạn bè")))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi 3 ngày")
    context = next(m["content"] for m in chat.seen[0][0] if m["content"].startswith("CURRENT CONTEXT"))
    # the keyword rules already read "3 ngày": it is not asked again
    assert '"still_needed": {"companions": "đi cùng ai", "mobility": "đi lại bằng gì", "when": "ngày hoặc tháng đi"}' in context
    view = next(d for n, d in ev if n == "state")["understanding"]
    assert view["ready"] is True  # Next is always open; only a health hint blocks
    assert [m["target"] for m in view["missing"]] == ["companions", "mobility", "when"]


def test_next_is_always_open_and_compiles_with_unknowns(make):
    e = make(ScriptedChat(reply(fact("days", "3", "3 ngày"), ask("Đi cùng ai?", "Một mình", "Bạn bè"))))
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi 3 ngày")
    ev = run(e, sid, kind="show")
    assert names(ev) == ["done"] and ev[0][1]["search_input"]["context"]["days"] == 3
    assert ev[0][1]["search_input"]["unknowns"] != ()
    assert e.load(sid)["card"] is None


def test_a_refused_tool_call_is_corrected_inside_the_same_turn(make):
    chat = ScriptedChat(reply(fact("days", "9", "9 ngày")),  # not in the message: refused, the agent reads the error
                        reply(fact("days", "3", "3 ngày"), ask("Đi cùng ai?", "Một mình", "Bạn bè")))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi 3 ngày")
    assert chat.calls == 2 and e.store.get(sid).state.days.value == 3
    tool_result = next(m for m in chat.seen[1][0] if m["role"] == "tool")
    assert "error" in tool_result["content"]


def test_a_plain_reply_to_a_message_that_tells_nothing_leaves_a_free_text_card(make):
    e = make(ScriptedChat(say("Chào bạn, bạn kể về chuyến đi nhé.")))
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="chào")
    assert ev[-1][1]["qid"] == "conversation" and not e.store.get(sid).state.meta.told


def test_agent_failure_keeps_what_was_written_and_says_so(make):
    e = make(ScriptedChat(reply(fact("days", "3", "3 ngày"))))  # the second call finds the script empty
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi 3 ngày 2 đêm")
    assert ("say", {"replace": FALLBACK_SAY}) in ev and ev[-1][1]["qid"] == "companions"
    assert e.store.get(sid).state.days.value == 3


def test_agent_down_still_applies_the_keyword_rules(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi 3 ngày bằng xe máy")
    assert all(r["mark"] for r in ev[-2][1]["understanding"]["trip"])  # shown with the pencil until confirmed


def test_next_with_an_open_health_hint_applies_its_strictest_choice(make):
    chat = ScriptedChat(reply(fact("signal", "knee", "đau gối", op="add"), ask("Đi bộ được bao lâu?", "Ít", "Nhiều")))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="mẹ đau gối")
    assert "điều cần lưu ý về sức khỏe" in [m["label"] for m in e.load(sid)["understanding"]["missing"]]
    ev = run(e, sid, kind="show")
    assert names(ev) == ["done"]
    st = e.store.get(sid).state
    assert {h.feature for h in st.hard} >= {"steep_or_stairs", "long_walk"} and not pending_signals(st)


def test_edit_soft_and_bad_value(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="edit", target="soft:noise=quiet", value="love")
    assert e.load(sid)["understanding"]["soft"][0]["key"] == "noise=quiet"
    run(e, sid, kind="edit", target="soft:noise=quiet", value=None)
    assert e.load(sid)["understanding"]["soft"] == []
    assert names(run(e, sid, kind="edit", target="days", value="mười"))[0] == "error"


def test_a_typed_time_for_a_coach_or_flight_sets_the_day_window(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    assert "error" not in names(run(e, sid, kind="edit", target="inbound", value='{"time": "9h30"}'))
    assert "error" not in names(run(e, sid, kind="edit", target="outbound", value='{"time": "17:00"}'))
    st = e.store.get(sid).state
    assert st.checkin_at.value == "09:30" and st.checkout_at.value == "17:00" and not st.inbound.known
    assert names(run(e, sid, kind="edit", target="inbound", value='{"time": "25:00"}'))[0] == "error"


def test_stale_answer_is_rejected(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    assert names(run(e, sid, kind="answer", qid="pace", chips=("slow",))) == ["error", "card"]


def test_session_survives_restart(make, tmp_path):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày"), ask("Đi cùng ai?", "Một mình", "Bạn bè")))
    sid = make().create("returning", "saved")["id"]
    run(make(chat), sid, kind="text", text="đi 3 ngày")
    v = make().load(sid)
    assert v["card"]["text"] == "Đi cùng ai?" and v["understanding"]["trip"][0]["value"] == 3


def test_unknown_session_raises(make):
    with pytest.raises(KeyError):
        make().load("0123456789ab")


def test_client_gone_mid_turn_still_applies_and_saves_the_turn(make):
    e = make(ScriptedChat(reply(fact("days", "3", "3 ngày"), ask("Đi cùng ai?", "Một mình", "Bạn bè"), text="Mình ")))
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
    assert e.chat.seen[0][1] == ["record_fact", "resolve_relative_date", "search_places", "search_features"]  # no asking


def test_refine_never_ends_its_reply_with_a_question_no_card_will_answer(ready_engine):
    e, sid = ready_engine
    e.chat = ScriptedChat(reply(fact("soft", "noise=quiet:love", "yên tĩnh hơn", op="add"),
                                text="Mình ưu tiên chỗ yên tĩnh. Bạn muốn đi buổi nào?"))
    events = []
    e.refine(sid, "muốn yên tĩnh hơn", lambda ev, d: events.append((ev, d)))
    assert [d for ev, d in events if ev == "say"][-1] == {"replace": "Mình ưu tiên chỗ yên tĩnh."}


class FakeJudge:
    def __init__(self, unsupported=False, bad=None, repeats=False, features=()):
        self._u, self._b, self._r, self._f = unsupported, bad, repeats, list(features)

    def unsupported(self, quote, claim):
        return self._u

    def bad_reply(self, say):
        return self._b

    def repeats(self, question, known):
        return self._r

    def features(self, wish, features):
        return self._f


def judged(make, chat, judge, route=None):
    e = make(chat, route=route)
    e.judge = judge
    return e


def test_what_the_agent_did_next_to_a_clef_reject_is_dropped_and_not_shown(make):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày"), ask("Đi cùng ai?", "Một mình", "Bạn bè"), text="Mình ghi lại rồi."))
    e = make(chat, route=lambda text, card: ClefRoute(asks_data=True))
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="vé vào cổng bao nhiêu")
    s = e.store.get(sid)
    assert ("say", {"replace": NODATA_SAY}) in ev and not any(d.get("delta") for k, d in ev if k == "say")
    assert not s.state.days.known and s.card.qid == "conversation"


def test_a_fact_whose_quote_does_not_say_it_is_refused_so_the_agent_can_correct_itself(make):
    chat = ScriptedChat(reply(fact("soft", "noise=quiet:love", "yên tĩnh", how="inferred")), reply(ask("Bạn đi mấy ngày?", "1-2", "3-4")))
    e = judged(make, chat, FakeJudge(unsupported=True))
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="mình thích chỗ yên tĩnh")
    log = [t["text"] for t in e.store.get(sid).transcript if t["role"] == "system"][0]
    assert "clef_unsupported" in log and "record_fact soft=noise=quiet:love:error" in log


def test_a_question_the_state_already_answers_is_sent_back_to_the_agent(make):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày"), ask("Bạn đi mấy ngày?", "1-2", "3-4")),
                        reply(ask("Bạn đi với ai?", "Một mình", "Bạn bè")))
    once = iter([True, False])
    judge = FakeJudge()
    judge.repeats = lambda question, known: next(once)
    e = judged(make, chat, judge)
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi 3 ngày")
    assert chat.calls == 2 and ev[-1][1]["text"] == "Bạn đi với ai?"


def test_a_reply_clef_finds_promising_results_is_replaced(make):
    chat = ScriptedChat(say("Mình sẽ gợi ý lịch trình ngay nhé"))
    e = judged(make, chat, FakeJudge(bad="promises results"))
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="chào")
    assert ("say", {"replace": NOTED_TEXT_SAY}) in ev  # nothing was asked: a pointer to the summary, not "chưa trả lời được"


def test_search_features_falls_back_to_clef_when_the_keywords_find_nothing(make):
    chat = ScriptedChat(reply(call("search_features", query="zzzz")), reply(ask("Bạn đi mấy ngày?", "1-2", "3-4")))
    e = judged(make, chat, FakeJudge(features=["scenic_view"]))
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="zzzz")
    tool_msg = [m for m in chat.seen[1][0] if m["role"] == "tool"][0]
    assert "scenic_view" in tool_msg["content"]


def test_a_question_asked_right_after_a_refused_fact_is_sent_back_once_so_the_fact_gets_fixed(make):
    chat = ScriptedChat(reply(fact("companions", "family", "gia đình"), ask("Đi cùng ai?", "Bố mẹ", "Con nhỏ")),
                        reply(fact("companions", "parents", "gia đình")), reply(ask("Đi bằng gì?", "Xe máy", "Ô tô")))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi với gia đình")
    s = e.store.get(sid)
    assert chat.calls == 3 and "parents" in str(s.state.companions.value)
    assert ev[-1][1]["text"] == "Đi bằng gì?" and "ask_choice:refused_first" in [t["text"] for t in s.transcript if t["role"] == "system"][-1]


def test_questions_are_sent_back_at_most_twice_while_a_refused_fact_stays_unfixed_then_the_turn_goes_on(make):
    chat = ScriptedChat(reply(fact("companions", "family", "gia đình"), ask("Bạn đi tháng mấy?", "11", "12")),
                        reply(ask("Bạn đi tháng mấy?", "11", "12")), reply(ask("Bạn đi tháng mấy?", "11", "12")))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi với gia đình")
    assert chat.calls == 3 and ev[-1][1]["text"] == "Bạn đi tháng mấy?"  # two sent back, the third goes through


def test_the_agent_may_not_ask_the_start_date_the_quiz_asks_it_on_a_calendar(make):
    chat = ScriptedChat(reply(call("ask_text", text="Bạn khởi hành ngày nào?", placeholder="25/10", kind="date")))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    card = run(e, sid, kind="text", text="đi 3 ngày 2 đêm")[-1][1]
    assert not card["qid"].startswith("ask:")  # refused: the agent only clarifies what the user wrote
    while card["qid"] != "dates":
        card = run(e, sid, kind="answer", qid=card["qid"], chips=("skip",))[-1][1]
    assert card["input"] == "date" and card["exits"] is False  # no "Chưa chắc" next to the calendar: "Chưa chốt ngày" is the way past
    assert ("error", {"message": PAST_DATE}) in run(e, sid, kind="answer", qid="dates", value="2026-10-01")
    run(e, sid, kind="answer", qid="dates", value="2026-10-25")
    st = e.store.get(sid).state
    assert st.start_date.value == date(2026, 10, 25) and st.start_date.locked


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


def test_a_correction_in_a_later_turn_updates_the_budget_scope_and_the_liked_kinds_even_if_the_agent_fails(make):
    # T-2: the user's correction is read by the keyword rules before the agent, so it is never lost
    e = make()
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="Đi Đà Lạt 3 ngày với bạn gái, ngân sách khoảng 5 triệu")
    u = e.load(sid)["understanding"]
    assert u["budget_vnd"]["value"] == {"amount": 5_000_000, "scope": "trip_total", "guessed": True,
                                        "per_person_day": 833_333} and u["budget_vnd"]["mark"]
    run(e, sid, kind="text", text="5 triệu là tổng cả chuyến cho 2 người nha… Mình cũng rất thích cà phê.")
    st = e.store.get(sid).state
    assert st.budget_scope.value == "trip_total" and st.liked_groups.value == ("chill",)
    assert e.load(sid)["understanding"]["budget_vnd"]["value"]["guessed"] is False


def test_a_correction_of_something_known_leaves_the_open_question_open(make):
    chat = ScriptedChat(reply(fact("days", "3", "3 ngày"), ask("Bạn muốn đi thong thả hay đi nhiều?", "Thong thả", "Đi nhiều")),
                        reply(fact("days", "3", "3 ngày")))  # recorded again, nothing new
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi 3 ngày")
    ev = run(e, sid, kind="text", text="đúng rồi 3 ngày nha")
    assert ev[-1][1]["text"] == "Bạn muốn đi thong thả hay đi nhiều?"


def test_a_question_the_model_writes_as_plain_text_becomes_the_open_card(make):
    chat = ScriptedChat(say("Mình ghi rồi. Bạn muốn đi thong thả hay đi nhiều?"))
    e = make(chat)
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi 3 ngày")
    assert ev[-1][1]["text"] == "Bạn muốn đi thong thả hay đi nhiều?" and ev[-1][1]["qid"] == "ask:1"
    assert e.store.get(sid).transcript[-2]["text"] == "Mình ghi rồi."  # the chat keeps only the lead
