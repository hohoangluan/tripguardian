"""One question at a time: the agent picks the next question (its own follow-up or a required topic), a tap on the
card is written by code and then read by the agent, and the Agent role reaches a reasoning model with a cache key."""

import asyncio
import json
from datetime import date

import pytest

from trip_fixtures import ScriptedChat, call, reply, say

from trip.api.engine import Engine, TurnInput, asks_in_text, picked_text
from trip.domain import deck
from trip.domain.state import TripState
from trip.infrastructure.sessions import SessionStore
from trip.infrastructure.settings import Settings


def run(e, sid, **inp):
    events = []
    e.turn(sid, TurnInput(**inp), lambda ev, d: events.append((ev, d)))
    return events


def context_of(messages):
    return json.loads(next(m["content"] for m in messages if str(m["content"]).startswith("CURRENT CONTEXT"))
                      .removeprefix("CURRENT CONTEXT\n"))


def test_the_agent_chooses_which_required_topic_comes_next(catalog, cfg, tmp_path):
    chat = ScriptedChat(reply(call("ask_required", topic="mobility", question="Bạn đi lại bằng gì?"), text="Đi với người yêu thì đi lại cho tiện là chính."))
    e = Engine(catalog, cfg, SessionStore(tmp_path), chat, today=lambda: date(2026, 10, 15))
    sid = e.create("first", "nothing")["id"]
    card = run(e, sid, kind="text", text="đi với người yêu")[-1][1]
    assert card["kind"] == "deck" and [t["qid"] for t in card["tabs"]] == ["mobility"]  # not the first missing (trip)
    assert card["tabs"][0]["question"] == "Bạn đi lại bằng gì?"
    assert "ask" not in card  # the chosen topic stays on the server
    assert e.load(sid)["card"]["tabs"][0]["qid"] == "mobility"  # and survives a reload


def test_ask_required_refuses_a_topic_that_is_not_needed(catalog, cfg, tmp_path):
    from trip.agent.tools import TurnTools
    st = TripState.model_validate({"mobility": {"value": "motorbike", "source": "user",
                                                "evidence": [{"turn": 1, "quote": "xe máy"}]}})
    tools = TurnTools(st, "x", 2, catalog, date(2026, 10, 15))
    assert "error" in tools.run("ask_required", {"topic": "mobility", "question": "Bạn đi lại bằng gì?"}) and tools.asked is None
    assert tools.run("ask_required", {"topic": "budget", "question": "Ngân sách của bạn khoảng bao nhiêu?"}) == {
        "ok": True, "note": "the app adds the answer controls under your question; end the turn now"}
    assert "error" in tools.run("ask_required", {"topic": "pace", "question": "Bạn muốn đi thong thả không?"})  # one card per turn


def test_a_tap_on_a_required_card_is_written_once_then_read_by_the_agent(catalog, cfg, tmp_path):
    chat = ScriptedChat(reply(call("ask_required", topic="mobility", question="Bạn đi lại bằng gì?"), text="Rõ rồi."), say("Đi xe máy nhé."))
    e = Engine(catalog, cfg, SessionStore(tmp_path), chat, today=lambda: date(2026, 10, 15))
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi với người yêu")
    turn = e.store.get(sid).state.meta.turn
    ev = run(e, sid, kind="deck", answers={"mobility": ["motorbike"]})
    s = e.store.get(sid)
    assert chat.calls == 2  # Code writes the tap; the agent reads it exactly once.
    assert context_of(chat.seen[-1][0])["picked"].startswith("The latest user message is what they chose on the card")
    assert s.state.mobility.value == "motorbike" and s.state.mobility.source == "user"
    assert s.state.meta.turn == turn + 1
    users = [t["text"] for t in s.transcript if t["role"] == "user"]
    assert users[-1] == "Phương tiện: Xe máy" and users.count("Phương tiện: Xe máy") == 1
    assert ("say", {"replace": "Đi xe máy nhé."}) in ev
    card = ev[-1][1]
    assert card["qid"] == "conversation" and card["input"] == "text"
    assert s.state.meta.followups == 0


def test_follow_ups_in_a_row_reach_the_agent_and_a_required_card_resets_them(catalog, cfg, tmp_path):
    chat = ScriptedChat(say("Chill với bạn là ngồi cà phê hay dạo hồ?"), say("Cà phê kiểu yên tĩnh hay có nhạc?"),
                        reply(call("ask_required", topic="trip", question="Bạn định đi ngày nào?"), text="Giờ mình chốt ngày nhé."))
    e = Engine(catalog, cfg, SessionStore(tmp_path), chat, today=lambda: date(2026, 10, 15))
    sid = e.create("first", "nothing")["id"]
    for text in ("đi chill", "cà phê", "yên tĩnh"):
        run(e, sid, kind="text", text=text)
    assert [context_of(m)["followups_in_a_row"] for m, _ in chat.seen] == [0, 1, 2]
    assert e.store.get(sid).state.meta.followups == 0


def test_picked_text_reads_the_options_the_user_chose(catalog, cfg):
    d = deck.build(TripState(), catalog, cfg, ask="companions")
    assert picked_text(d, {"companions.who": ["partner"], "companions.people": "2"}) == "Đi với: Người yêu, vợ chồng · 2 người"
    d = deck.build(TripState(), catalog, cfg, ask="trip")
    assert picked_text(d, {"trip.dates": "2026-11-20..2026-11-22", "trip.start": "10:00"}) == \
        "Ngày đi: 20/11 – 22/11 · bắt đầu 10:00"
    assert asks_in_text("Rõ rồi.\nBạn đi mấy ngày?") and not asks_in_text("Mình đã ghi lại (số ngày).")


def test_the_agent_call_asks_for_low_reasoning_with_a_cache_key_and_its_own_http_client(monkeypatch):
    from trip.agent import loop as loop_mod
    seen = {}

    class FakeLLM:
        def bind_tools(self, tools, **kw):
            return self

        async def astream(self, msgs):
            return
            yield

    class FakeClient:
        base_url, api_key = "http://x", "k"

        async def close(self):
            pass

    monkeypatch.setattr(loop_mod, "ChatOpenAI", lambda **kw: seen.update(kw) or FakeLLM())
    monkeypatch.setattr(loop_mod, "AGENT", type("Role", (), {
        "client": staticmethod(lambda: (FakeClient(), "cx/gpt-6.1-sol")), "reasoning": staticmethod(lambda: "low"),
        "cache_key": staticmethod(lambda task: {"prompt_cache_key": f"tripguardian-{task}"})}))
    asyncio.run(loop_mod.langchain_chat(Settings())([{"role": "user", "content": "x"}], [], lambda _: None))
    assert seen["reasoning_effort"] == "low" and seen["extra_body"] == {"prompt_cache_key": "tripguardian-trip_turn"}
    assert seen["http_async_client"].is_closed  # made for this call, closed with it


def test_a_role_without_reasoning_sends_neither(monkeypatch):
    from corpus.llm import roles
    monkeypatch.setenv("AGENT_REASONING_EFFORT", "")
    monkeypatch.setattr(roles, "load_dotenv", lambda *a, **k: None)
    assert roles.AGENT.reasoning() is None and roles.AGENT.cache_key("trip_turn") == {}
    monkeypatch.setenv("AGENT_REASONING_EFFORT", "low")
    assert roles.AGENT.cache_key("decision_turn") == {"prompt_cache_key": "tripguardian-decision_turn"}


def test_record_fact_writes_every_fact_of_a_message_in_one_call(catalog):
    from trip.agent.tools import TurnTools
    from trip.agent.tool_schemas import RecordFact
    t = TurnTools(TripState(), "đi 3 ngày với người yêu bằng xe máy", 1, catalog, date(2026, 10, 15))
    args = RecordFact.model_validate({"facts": [
        {"field": "days", "op": "set", "value": "3", "quote": "3 ngày"},
        {"field": "companions", "op": "add", "value": "partner", "quote": "người yêu"},
        {"field": "mobility", "op": "set", "value": "motorbike", "quote": "máy bay"}]}).model_dump(exclude_none=True)
    out = t.run("record_fact", args)
    assert "error" not in out and [("error" in r) for r in out["results"]] == [False, False, True]  # quote not said
    assert t.state.days.value == 3 and "partner" in t.state.companions.value and not t.state.mobility.known
    assert t.recorded == ["days", "companions"] and "mobility" in t.refused
    assert "error" in t.run("record_fact", {"facts": [{"field": "mobility", "op": "set", "value": "car", "quote": "xe hơi"}]})


def test_a_card_shows_the_three_best_options_of_each_group_and_keeps_other(catalog, cfg):
    who = deck.build(TripState(), catalog, cfg, ask="companions").tabs[0]
    assert [o.id for o in who.options] == ["partner", "friends", "parents", "other", "skip"]  # common answers first
    guessed = TripState.model_validate({"companions": {"value": ["kids"], "source": "inferred",
                                                       "evidence": [{"turn": 1, "quote": "2 bé"}]}})
    assert [o.id for o in deck.build(guessed, catalog, cfg, ask="companions").tabs[0].options][0] == "kids"
    trip = deck.build(TripState(), catalog, cfg, ask="trip").tabs[0]
    ids = [o.id for o in trip.options]
    assert sum(i.startswith("start.") for i in ids) == 3 and sum(i.startswith("end.") for i in ids) == 3
    assert len(deck.build(TripState(), catalog, cfg, at="gate").tabs[1].options) > 5  # the gate keeps every option


def test_plain_words_that_are_also_a_place_name_are_not_a_named_place():
    from trip.domain.guard import bad_say
    names = type("Names", (), {"name_keys": [("khu vui choi", "p1"), ("dac san da lat", "p2"), ("cafe tung xua", "p3")]})()
    assert bad_say("Mình ưu tiên chỗ có khu vui chơi cho hai bé.", "đi với hai bé", TripState(), names, set()) is None
    assert bad_say("Bạn muốn mua đặc sản Đà Lạt không?", "đi ăn", TripState(), names, set()) is None
    assert bad_say("Bạn ghé Cafe Tùng Xưa nhé.", "đi cà phê", TripState(), names, set()) == "names place p3"
    assert bad_say("Ở gần Cafe Tùng Xưa nhé.", "muốn ở gần cafe Tùng Xưa", TripState(), names, set()) is None  # said back


def test_the_agent_may_keep_following_the_user_past_two_questions(catalog, cfg, tmp_path):
    chat = ScriptedChat(say("Chill với bạn là cà phê hay dạo hồ?"), say("Cà phê yên tĩnh hay có nhạc?"),
                        say("Rõ rồi, quán yên tĩnh. Bạn thích view đồi hay view hồ?"))
    e = Engine(catalog, cfg, SessionStore(tmp_path), chat, today=lambda: date(2026, 10, 15))
    sid = e.create("first", "nothing")["id"]
    for text in ("đi chill", "cà phê"):
        assert run(e, sid, kind="text", text=text)[-1][1]["qid"] == "conversation"
    ev = run(e, sid, kind="text", text="yên tĩnh")
    assert ev[-1][1]["qid"] == "conversation"  # no cap: the required topics wait for the user's thread
    s = e.store.get(sid)
    assert s.transcript[-1]["text"] == "Rõ rồi, quán yên tĩnh. Bạn thích view đồi hay view hồ?"
    assert s.state.meta.followups == 3


def test_facts_and_reply_in_one_call_end_the_turn_without_a_second_call(catalog, cfg, tmp_path):
    facts = [{"field": "companions", "op": "add", "value": "partner", "quote": "người yêu"},
             {"field": "days", "op": "set", "value": "3", "quote": "3 ngày"}]
    chat = ScriptedChat(reply(call("record_fact", facts=facts, say="Hai bạn đi 3 ngày. Chill là cà phê hay dạo hồ?")))
    e = Engine(catalog, cfg, SessionStore(tmp_path), chat, today=lambda: date(2026, 10, 15))
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi với người yêu 3 ngày, muốn chill")
    assert chat.calls == 1 and ev[-1][1]["qid"] == "conversation"
    assert e.store.get(sid).transcript[-1]["text"] == "Hai bạn đi 3 ngày. Chill là cà phê hay dạo hồ?"
    st = e.store.get(sid).state
    assert st.days.value == 3 and "partner" in st.companions.value


def test_the_required_card_can_ride_with_the_facts(catalog, cfg, tmp_path):
    facts = [{"field": "days", "op": "set", "value": "3", "quote": "3 ngày"}]
    chat = ScriptedChat(reply(call("record_fact", facts=facts, say="Rõ rồi, 3 ngày.", ask_required="mobility", ask_question="Ba ngày này bạn đi lại bằng gì?")))
    e = Engine(catalog, cfg, SessionStore(tmp_path), chat, today=lambda: date(2026, 10, 15))
    sid = e.create("first", "nothing")["id"]
    card = run(e, sid, kind="text", text="đi 3 ngày")[-1][1]
    assert chat.calls == 1 and [t["qid"] for t in card["tabs"]] == ["mobility"]
    assert card["tabs"][0]["question"] == "Ba ngày này bạn đi lại bằng gì?"


def test_a_refused_fact_keeps_the_loop_going_for_a_corrected_reply(catalog, cfg, tmp_path):
    bad = [{"field": "mobility", "op": "set", "value": "car", "quote": "máy bay"}]  # the quote is not the user's
    chat = ScriptedChat(reply(call("record_fact", facts=bad, say="Bạn đi ô tô nhé.")),
                        say("Bạn đi lại ở Đà Lạt bằng gì?"))
    e = Engine(catalog, cfg, SessionStore(tmp_path), chat, today=lambda: date(2026, 10, 15))
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi xe gì cũng được")
    assert chat.calls == 2 and e.store.get(sid).transcript[-1]["text"] == "Bạn đi lại ở Đà Lạt bằng gì?"


def test_children_and_grandparents_said_the_everyday_way_name_their_group():
    from trip.domain.guard import names_group
    assert names_group("có bà ngoại lớn tuổi với 2 đứa nhỏ", "kids") and names_group("hai bé 6 và 9 tuổi", "kids")
    assert names_group("con trai mình", "kids") and names_group("có bà ngoại lớn tuổi", "parents")
    assert not names_group("nhóm mình 6 đứa", "kids") and not names_group("nhóm ba người", "parents")
    assert names_group("đi đà lạt 1 mình để ăn", "solo") and names_group("nhóm mình 6 đứa", "friends")
    assert not names_group("2 đứa nhỏ", "friends") and names_group("nhóm mình đi săn mây", "friends")
    assert not names_group("nhóm mình đi săn mây", "solo") and not names_group("đi một mình", "friends")


def test_dates_the_keyword_rules_wrote_are_marked_so_the_agent_does_not_compute_them_again(catalog, cfg, tmp_path):
    chat = ScriptedChat(say("Rõ rồi."))
    e = Engine(catalog, cfg, SessionStore(tmp_path), chat, today=lambda: date(2026, 10, 15))
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="nhà mình đi 4 ngày, từ 24 đến 27/12")
    hints = {h["field"]: h for h in context_of(chat.seen[0][0])["keyword_hints"]}
    assert hints["start_date"]["written"] and hints["days"]["written"]
    assert e.store.get(sid).state.start_date.value == date(2026, 12, 24)


@pytest.mark.parametrize("last", ["tùy", "chưa biết nữa",
                                "gợi ý giúp mình kiểu nào hợp với hai đứa",
                                "mình thích ngồi lâu đọc sách, nghe nhạc nhẹ, nhìn ra đồi thông buổi chiều cho thư thả"])
def test_the_app_never_replaces_the_agents_question_with_a_required_topic(catalog, cfg, tmp_path, last):
    chat = ScriptedChat(say("Chill với bạn là cà phê hay dạo hồ?"), say("Cà phê yên tĩnh hay có nhạc?"),
                        say("View đồi hay view hồ?"), say("Rõ rồi. Bạn thích đi sáng hay chiều?"))
    e = Engine(catalog, cfg, SessionStore(tmp_path), chat, today=lambda: date(2026, 10, 15))
    sid = e.create("first", "nothing")["id"]
    for text in ("đi chill", "cà phê", "yên tĩnh"):
        run(e, sid, kind="text", text=text)
    ev = run(e, sid, kind="text", text=last)
    card = ev[-1][1]
    assert card["qid"] == "conversation"
    assert ("say", {"replace": "Rõ rồi. Bạn thích đi sáng hay chiều?"}) in ev
    assert e.store.get(sid).transcript[-1]["text"] == "Rõ rồi. Bạn thích đi sáng hay chiều?"
    assert not any("thread_done" in t["text"] for t in e.store.get(sid).transcript if t["role"] == "system")


def test_a_required_card_put_off_in_words_moves_on_like_its_skip(catalog, cfg, tmp_path):
    chat = ScriptedChat(reply(call("ask_required", topic="trip", question="Bạn định đi ngày nào?"), text="Mình hỏi ngày đi nhé."), say("Được nhé."))
    e = Engine(catalog, cfg, SessionStore(tmp_path), chat, today=lambda: date(2026, 10, 15))
    sid = e.create("first", "nothing")["id"]
    assert run(e, sid, kind="text", text="đi đà lạt")[-1][1]["tabs"][0]["qid"] == "trip"
    card = run(e, sid, kind="text", text="mình chưa chốt ngày nha, bỏ qua đi")[-1][1]
    assert card["qid"] == "conversation" and card["input"] == "text"
    assert "trip" in e.store.get(sid).state.meta.declined  # the read-back before planning asks it again


def test_record_fact_reads_the_users_own_date_words_with_no_date_tool_first(catalog):
    from trip.agent.tools import TurnTools
    t = TurnTools(TripState(), "thứ 4 tuần sau mình đi", 1, catalog, date(2026, 10, 15))
    out = t.run("record_fact", {"facts": [{"field": "start_date", "op": "set", "value": "thứ 4 tuần sau",
                                           "quote": "thứ 4 tuần sau", "how": "said"}]})
    assert "error" not in out and t.state.start_date.value == date(2026, 10, 21)
    bad = t.run("record_fact", {"facts": [{"field": "start_date", "op": "set", "value": "hôm nào đó",
                                           "quote": "thứ 4 tuần sau", "how": "said"}]})
    assert "error" in bad  # not the user's words: refused, nothing guessed
    t2 = TurnTools(TripState(), "nhà mình đi từ 24 đến 27/12/2026", 1, catalog, date(2026, 10, 15))
    out = t2.run("record_fact", {"facts": [{"field": "start_date", "op": "set", "value": "24/12/2026",
                                            "quote": "từ 24 đến 27/12/2026", "how": "said"}]})
    assert "error" not in out and t2.state.start_date.value == date(2026, 12, 24)  # tidied by the model, still theirs


def test_a_taste_is_never_a_hard_filter_but_a_limit_is(catalog):
    from trip.agent.tools import TurnTools
    t = TurnTools(TripState(), "Nhất định phải thử bánh căn, mà đi bộ ít thôi", 1, catalog, date(2026, 10, 15))
    out = t.run("record_fact", {"facts": [
        {"field": "hard", "op": "add", "value": "local_specialty_food=present", "quote": "Nhất định phải thử bánh căn", "how": "said"},
        {"field": "hard", "op": "add", "value": "long_walk!=present", "quote": "đi bộ ít thôi", "how": "said"}]})
    assert "error" in out["results"][0] and "never a hard filter" in out["results"][0]["error"]
    assert "error" not in out["results"][1] and [h.feature for h in t.state.hard] == ["long_walk"]


def test_a_refused_taste_is_kept_as_a_wish_without_a_second_call(catalog, cfg, tmp_path):
    chat = ScriptedChat(reply(call("record_fact", say="Ba ngày, chỗ yên tĩnh nhé.", facts=[
        {"field": "days", "op": "set", "value": "3", "quote": "3 ngày", "how": "said"},
        {"field": "soft", "op": "add", "value": "noise=silent:love", "quote": "yên tĩnh", "how": "said"}])))
    e = Engine(catalog, cfg, SessionStore(tmp_path), chat, today=lambda: date(2026, 10, 15))
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi 3 ngày, thích chỗ yên tĩnh")
    s = e.store.get(sid)
    assert chat.calls == 1 and s.state.days.value == 3 and [u.phrase for u in s.state.unmapped] == ["yên tĩnh"]
    assert "refusal_kept" in [t["text"] for t in s.transcript if t["role"] == "system"][-1]


def test_a_refused_trip_fact_is_still_fixed_in_the_same_turn(catalog, cfg, tmp_path):
    chat = ScriptedChat(reply(call("record_fact", say="Rõ rồi.", facts=[
        {"field": "mobility", "op": "set", "value": "car", "quote": "ô tô", "how": "said"}])),  # not their words
        reply(call("record_fact", say="Đi xe máy nhé.", facts=[
            {"field": "mobility", "op": "set", "value": "motorbike", "quote": "xe máy", "how": "said"}])))
    e = Engine(catalog, cfg, SessionStore(tmp_path), chat, today=lambda: date(2026, 10, 15))
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="mình đi xe máy")
    assert chat.calls == 2 and e.store.get(sid).state.mobility.value == "motorbike"


def test_the_user_never_sees_a_reply_that_is_then_replaced(catalog, cfg, tmp_path):
    # the agent claims a write it never made: its words are dropped and it writes again; only the final words go out
    chat = ScriptedChat(say("Mình đã ghi nhận rồi."), say("Bạn đi mấy ngày?"))
    e = Engine(catalog, cfg, SessionStore(tmp_path), chat, today=lambda: date(2026, 10, 15))
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi đà lạt")
    assert [d for n, d in ev if n == "say"] == [{"replace": "Bạn đi mấy ngày?"}]
    assert [n for n, _ in ev if n in ("say", "card")] == ["say", "card"]


def test_a_changed_taste_replaces_the_value_it_contradicts(catalog):
    from trip.agent.tools import TurnTools
    t = TurnTools(TripState(), "thích chỗ đông vui náo nhiệt", 1, catalog, date(2026, 10, 15))
    t.run("record_fact", {"facts": [{"field": "soft", "op": "add", "value": "noise=loud:love", "quote": "náo nhiệt", "how": "said"}]})
    t2 = TurnTools(t.state, "à không, mình thích chỗ yên tĩnh hơn", 2, catalog, date(2026, 10, 15))
    t2.run("record_fact", {"facts": [{"field": "soft", "op": "add", "value": "noise=quiet:love", "quote": "yên tĩnh", "how": "said"}]})
    assert {k: f.value for k, f in t2.state.soft.items()} == {"noise=quiet": "love"}


def test_a_checked_reply_streams_word_by_word_and_is_never_taken_back(catalog, cfg, tmp_path):
    from dataclasses import replace
    chat = ScriptedChat(say("Mình đã ghi nhận rồi."), say("Hai bạn đi mấy ngày vậy?"))  # the first is sent back
    e = Engine(catalog, replace(cfg, say_stream_s=0.02), SessionStore(tmp_path), chat, today=lambda: date(2026, 10, 15))
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi đà lạt")
    says = [d for n, d in ev if n == "say"]
    assert says[0] == {"replace": "Hai "} and all("delta" in d for d in says[1:])  # only the final words, in order
    assert "Hai " + "".join(d["delta"] for d in says[1:]) == "Hai bạn đi mấy ngày vậy?"
    assert [n for n, _ in ev if n in ("say", "card")][-1] == "card"
