"""Required questions belong to the agent; the app supplies answer controls and the gate defaults."""

from dataclasses import replace
from datetime import date

import pytest
from pydantic import ValidationError
from trip_fixtures import ScriptedChat, call, reply, say

from trip.agent.tool_schemas import AskRequired
from trip.agent.tools import TurnTools
from trip.api.engine import Engine
from trip.domain import deck
from trip.domain.state import TripState
from trip.infrastructure.sessions import SessionStore

from test_one_question_flow import context_of, run

TODAY = date(2026, 10, 15)
QUESTION = "Ba ngày này bạn đi lại bằng gì cho tiện?"
FACTS = [{"field": "days", "op": "set", "value": "3", "quote": "3 ngày", "how": "said"}]


@pytest.mark.parametrize("path", ["ask_required", "record_fact"])
def test_a_missing_question_is_an_error_and_does_not_settle_the_turn(catalog, path):
    tools = TurnTools(TripState(), "đi 3 ngày", 1, catalog, TODAY)
    if path == "ask_required":
        out = tools.run(path, {"topic": "mobility"})
    else:
        out = tools.run(path, {"facts": FACTS, "say": "Ba ngày nhé.", "ask_required": "mobility"})
        assert tools.state.days.value == 3  # Valid facts survive the question error.
        out = out["ask_required"]
    assert "error" in out and "question" in out["error"]
    assert tools.asked is None and tools.settled is False
    assert tools.run("ask_required", {"topic": "mobility", "question": QUESTION})["ok"] is True
    assert tools.asked == {"kind": "required", "topic": "mobility", "question": QUESTION}


def test_the_required_question_schema_requires_agent_wording():
    with pytest.raises(ValidationError):
        AskRequired.model_validate({"topic": "mobility"})
    assert AskRequired.model_validate({"topic": "mobility", "question": QUESTION}).question == QUESTION


@pytest.mark.parametrize("path", ["ask_required", "record_fact"])
def test_the_agent_repairs_missing_wording_and_the_question_survives_rebuild_and_reload(catalog, cfg, tmp_path, path):
    if path == "ask_required":
        bad = call(path, topic="mobility")
        good = call(path, topic="mobility", question=QUESTION)
    else:
        bad = call(path, facts=FACTS, say="Ba ngày nhé.", ask_required="mobility")
        good = call(path, facts=FACTS, say="Ba ngày nhé.", ask_required="mobility", ask_question=QUESTION)
    chat = ScriptedChat(reply(bad), reply(good))
    e = Engine(catalog, cfg, SessionStore(tmp_path), chat, today=lambda: TODAY)
    sid = e.create("first", "nothing")["id"]
    card = run(e, sid, kind="text", text="đi 3 ngày")[-1][1]
    assert chat.calls == 2  # The first call's error must return to the model in the same turn.
    errors = [m["content"] for m in chat.seen[1][0] if m["role"] == "tool"]
    assert len(errors) == 1 and "error" in errors[0].lower() and "question" in errors[0]
    assert [t["qid"] for t in card["tabs"]] == ["mobility"]
    assert card["tabs"][0]["question"] == QUESTION
    session = e.store.get(sid)
    assert session.card.ask_question == QUESTION
    assert e._card(session.state, session.card)["tabs"][0]["question"] == QUESTION
    fresh = Engine(catalog, cfg, SessionStore(tmp_path), ScriptedChat(), today=lambda: TODAY)
    assert fresh.load(sid)["card"]["tabs"][0]["question"] == QUESTION


@pytest.mark.parametrize("answer", ["motorbike", "skip"])
def test_required_card_answers_reach_the_agent_once_and_open_no_default_topic(catalog, cfg, tmp_path, answer):
    chat = ScriptedChat(reply(call("ask_required", topic="mobility", question=QUESTION)), say("Được nhé."))
    e = Engine(catalog, cfg, SessionStore(tmp_path), chat, today=lambda: TODAY)
    sid = e.create("first", "nothing")["id"]
    run(e, sid, kind="text", text="đi 3 ngày")
    ev = run(e, sid, kind="deck", answers={"mobility": [answer]})
    assert chat.calls == 2
    context = context_of(chat.seen[-1][0])
    assert context["picked"] == ("The latest user message is what they chose on the card; the app already recorded it. "
                                 "Do not record it again; record only what it implies beyond that.")
    state = e.store.get(sid).state
    if answer == "skip":
        assert not state.mobility.known and "mobility" in state.meta.declined
    else:
        assert state.mobility.value == answer and state.mobility.source == "user"
    assert context["still_needed"]  # Missing logistics never cause the app to open a required tab.
    assert ev[-1][1]["qid"] == "conversation" and ev[-1][1]["input"] == "text"
    assert ("say", {"replace": "Được nhé."}) in ev


@pytest.mark.parametrize("text", ["", "Rõ rồi."])
def test_next_with_no_pending_question_returns_the_text_box_despite_missing_topics(catalog, cfg, tmp_path, text):
    e = Engine(catalog, cfg, SessionStore(tmp_path), ScriptedChat(), today=lambda: TODAY)
    sid = e.create("first", "nothing")["id"]
    session = e.store.get(sid)
    assert deck.build(session.state, catalog, cfg).left == 7
    card = e._card(session.state, e._next(session, text))
    assert card["qid"] == "conversation" and card["input"] == "text" and card["chips"] == []


def test_gate_keeps_every_missing_topic_with_its_default_question(catalog, cfg):
    cfg = replace(cfg, max_tabs=7)
    gate = deck.build(TripState(), catalog, cfg, at="gate", ask="mobility", question=QUESTION)
    assert {t.qid: t.question for t in gate.tabs} == {
        "trip": "Bạn ở Đà Lạt từ ngày nào đến ngày nào? Ngày đầu bắt đầu và ngày cuối xong lúc mấy giờ?",
        "companions": "Ai đi cùng bạn, tổng cộng mấy người?",
        "mobility": "Bạn đi lại bằng gì ở Đà Lạt?",
        "care": "Có điều gì về sức khỏe, đi lại hay ăn uống cần lưu ý?",
        "pace": "Bạn muốn đi thong thả hay ghé nhiều nơi?",
        "budget": "Bạn muốn chi khoảng bao nhiêu và tính cho ai?",
        "lodging": "Bạn ở đâu trong chuyến đi?",
    }
    assert all(t.kind == "required" for t in gate.tabs) and gate.left == gate.total == 7


class PhotoLooks:
    """Every place has a photo named after it."""

    def best_photo(self, pid):
        return f"gmaps/places/{pid}/photos/1.jpg"


def agent_tab(*keys):
    from trip.domain import ask
    from trip.domain.state import Draft, Option, Tab

    options = tuple(Option(id=f"o{i}", label=k, writes=(Draft(field="soft", op="add", value=(k, "love")),))
                    for i, k in enumerate(keys))
    return Tab(qid="agent.x", kind="agent", header="Kiểu", question="Bạn nghiêng về kiểu nào?", options=options), ask


def test_a_taste_question_shows_a_real_place_photo_for_each_option(catalog, cfg):
    tab, ask = agent_tab("noise=quiet", "live_music=present")
    shown = ask.with_photos(tab, TripState(), catalog, PhotoLooks())
    assert shown.visual and [o.photo[1].endswith("1.jpg") for o in shown.options] == [True, True]
    assert len({o.photo[0] for o in shown.options}) == 2  # a different place for each option
    assert ask.with_photos(tab, TripState(), catalog, PhotoLooks()) == shown  # the same photos on every rebuild


def test_a_taste_question_stays_in_words_when_one_option_has_no_photo(catalog, cfg):
    tab, ask = agent_tab("noise=quiet", "live_music=present")

    class Partial:
        def best_photo(self, pid):
            return None if catalog.by_id[pid].value("live_music") == "present" else "a.jpg"

    assert ask.with_photos(tab, TripState(), catalog, Partial()) == tab
    assert ask.with_photos(tab, TripState(), catalog, None) == tab


@pytest.mark.parametrize("user, shows_confirm", [("tôi thích săn mây", True), ("săn mây có nên đi không?", False),
                                                  ("bạn có đề xuất gì không", False)])
def test_the_apps_own_confirmation_waits_while_the_user_is_asking(catalog, cfg, tmp_path, user, shows_confirm):
    from trip.domain.state import with_meta

    e = Engine(catalog, cfg, SessionStore(tmp_path), ScriptedChat(), today=lambda: TODAY)
    sid = e.create("first", "nothing")["id"]
    s = e.store.get(sid)
    from trip.domain.state import Draft, apply_drafts

    s.state = apply_drafts(with_meta(s.state, turn=1), [Draft(field="days", value=3),
                                                       Draft(field="soft", op="add", value=("cloud_hunting=present", "love"))], 1, tool="test")
    s.transcript.append({"role": "user", "text": user, "turn": 1, "kind": "text"})
    card = e._next(s, "Rõ rồi.")
    assert bool(getattr(card, "tabs", ()) and card.tabs[0].qid == "confirm.early") is shows_confirm
