"""Deck integration at the server boundary, including queued and persisted choices."""

from datetime import date

import pytest

from trip_fixtures import ScriptedChat, call, reply

from trip.api.engine import Engine, TurnInput
from trip.domain import ask, deck
from trip.domain.state import Evidence, TripState, Update, apply
from trip.infrastructure.sessions import SessionStore


def ready():
    def said(value):
        return {"value": value, "source": "user", "confidence": "high", "evidence": [{"turn": 1, "quote": "q"}]}
    return TripState.model_validate({k: said(v) for k, v in {
        "start_date": "2026-11-20", "days": 3, "checkin_at": "14:00", "checkout_at": "12:00",
        "companions": ["partner"], "people": 2, "mobility": "motorbike", "care": "none", "pace": "normal",
        "budget_unlimited": True, "lodging": {"text": "nhà người quen"}}.items()})


def question():
    return {"header": "Kiểu quán", "question": "Bạn thích quán kiểu nào?", "why": "Để chọn quán", "options": [
        {"label": label, "writes": [{"field": "soft", "op": "add", "value": key + ":love"}]}
        for label, key in (("Yên tĩnh", "noise=quiet"), ("Nhạc sống", "live_music=present"))]}


def engine(catalog, cfg, root, state=None):
    chat = ScriptedChat(reply(call("ask_user", questions=[question()])))
    e = Engine(catalog, cfg, SessionStore(root), chat, today=lambda: date(2026, 10, 15))
    sid = e.create("first", "nothing")["id"]
    if state:
        e.store.get(sid).state = state
    return e, sid, chat


def test_agent_tab_is_shown_alone_and_survives_reload(catalog, cfg, tmp_path):
    e, sid, chat = engine(catalog, cfg, tmp_path)
    e.turn(sid, TurnInput(kind="text", text="đi cà phê chill"), lambda *_: None)
    card = e.load(sid)["card"]
    assert [t["kind"] for t in card["tabs"]] == ["agent"]  # one question at a time: the agent's follow-up
    s = SessionStore(tmp_path).get(sid)
    assert s.card.agent and s.card.agent[0].kind == "agent"
    s.state = ready()
    s.card = deck.build(s.state, catalog, cfg, agent=s.card.agent)
    e.store.restore(s)
    tab = e.load(sid)["card"]["tabs"][0]
    assert tab["kind"] == "agent" and "writes" not in tab["options"][0]
    before = chat.calls
    e.turn(sid, TurnInput(kind="deck", answers={tab["qid"]: [tab["options"][0]["id"]]}), lambda *_: None)
    # the tap is written by code; the agent then runs once to react and choose the next question
    assert chat.calls == before + 1 and e.store.get(sid).state.soft["noise=quiet"].source == "user"


def test_two_optional_skips_suppress_the_rest_but_required_skip_waits_for_gate(catalog, cfg, tmp_path):
    e, sid, _ = engine(catalog, cfg, tmp_path, ready())
    s = e.store.get(sid)
    s.state = s.state.model_copy(update={"companions": ready().companions.model_copy(update={"value": frozenset({"baby"})})})
    s.state = apply(s.state, Update(field="soft", op="add", value=("cloud_hunting=present", "love"),
                                  source="user", confidence="high", evidence=Evidence(turn=1, tool="deck:test")))
    s.card = deck.build(s.state, catalog, cfg)
    assert [t.qid for t in s.card.tabs] == ["confirm.early"]  # one question at a time
    e.turn(sid, TurnInput(kind="deck", answers={"confirm.early": ["skip"]}), lambda *_: None)
    s = e.store.get(sid)
    assert [t.qid for t in deck.build(s.state, catalog, cfg).tabs] == ["confirm.nap"]
    s.card = deck.build(s.state, catalog, cfg)
    e.turn(sid, TurnInput(kind="deck", answers={"confirm.nap": ["skip"]}), lambda *_: None)
    s = e.store.get(sid)
    assert s.state.meta.soft_skips == 2 and not deck.build(s.state, catalog, cfg).tabs
    e2, sid2, _ = engine(catalog, cfg, tmp_path / "second")
    s2 = e2.store.get(sid2)
    s2.card = deck.build(s2.state, catalog, cfg)
    e2.turn(sid2, TurnInput(kind="deck", answers={"trip": ["skip"]}), lambda *_: None)
    assert s2.state.meta.soft_skips == 0 and "trip" not in [t.qid for t in s2.card.tabs]
    assert "trip" in [t.qid for t in deck.build(s2.state, catalog, cfg, at="gate").tabs]


def test_a_known_soft_answer_cannot_be_reasked(catalog, cfg):
    state = apply(ready(), Update(field="soft", op="add", value=("noise=quiet", "love"), source="user",
                                  confidence="high", evidence=Evidence(turn=1, tool="deck:test")))
    assert not ask.check([question()], state, catalog, cfg)


def test_busy_periods_and_visit_are_additive(catalog, cfg):
    state = TripState()
    for field, value in (("frame.periods", {"period": "sunrise"}), ("frame.periods", {"period": "evening"}),
                         ("frame.periods", {"period": "sunrise"}), ("frame.visit", {"cafe": 120}),
                         ("frame.visit", {"meal": 60})):
        state = apply(state, Update(field=field, op="add", value=value, source="user", confidence="high",
                                     evidence=Evidence(turn=1, tool="deck:test")))
    assert len(state.frame.periods) == 2 and state.frame.visit == {"cafe": 120, "meal": 60}


def test_a_declined_agent_question_is_not_reintroduced_on_a_later_turn(catalog, cfg, tmp_path):
    e, sid, _ = engine(catalog, cfg, tmp_path, ready())
    e.turn(sid, TurnInput(kind="text", text="đi cà phê chill"), lambda *_: None)
    tab = e.store.get(sid).card.tabs[0]
    e.turn(sid, TurnInput(kind="deck", answers={tab.qid: ["skip"]}), lambda *_: None)
    assert not ask.check([question()], e.store.get(sid).state, catalog, cfg)


def test_an_edit_refreshes_the_deck_instead_of_reasking_a_said_answer(catalog, cfg, tmp_path):
    e, sid, _ = engine(catalog, cfg, tmp_path)
    s = e.store.get(sid)
    s.card = deck.build(s.state, catalog, cfg)
    e.turn(sid, TurnInput(kind="edit", target="mobility", value="motorbike"), lambda *_: None)
    assert "mobility" not in [t["qid"] for t in e.load(sid)["card"]["tabs"]]


def test_a_deck_cannot_write_a_hidden_required_tab(catalog, cfg, tmp_path):
    e, sid, _ = engine(catalog, cfg, tmp_path)
    s = e.store.get(sid)
    s.card = deck.build(s.state, catalog, cfg)
    events = []
    e.turn(sid, TurnInput(kind="deck", answers={"budget.amount": "10000000"}), lambda *ev: events.append(ev))
    assert not s.state.budget_vnd.known
    assert any(ev == "deck_issues" and d["issues"] == [{"key": "budget.amount", "code": "invalid"}] for ev, d in events)


def test_selecting_who_and_a_prefilled_count_replaces_guesses_and_keeps_implied_signals_as_guesses(catalog, cfg, tmp_path):
    state = TripState.model_validate({"companions": {"value": ["parents"], "source": "profile", "evidence": [{"turn": 0, "tool": "profile"}]},
                                     "people": {"value": 3, "source": "inferred", "evidence": [{"turn": 1, "quote": "3 người"}]}})
    e, sid, _ = engine(catalog, cfg, tmp_path, state)
    s = e.store.get(sid)
    s.card = deck.build(state, catalog, cfg, ask="companions")  # the agent chose to ask who goes
    # the guess (parents) is one of the three options the card shows; choosing it makes it the user's answer
    e.turn(sid, TurnInput(kind="deck", answers={"companions": ["parents", "people.prefilled"]}), lambda *_: None)
    s = e.store.get(sid)
    assert s.state.companions.value == frozenset({"parents"}) and s.state.companions.source == "user"
    assert s.state.people.source == "user"
    assert s.state.signals[0].source == "inferred"


@pytest.mark.parametrize("arguments", ["", "[]", "null"])
def test_invalid_argument_values_always_get_a_json_error_and_valid_history(catalog, cfg, tmp_path, arguments):
    import json

    from langchain_core.messages import AIMessageChunk

    malformed = AIMessageChunk(content="", tool_call_chunks=[{
        "id": "broken", "name": "record_fact", "args": arguments, "index": 0}])
    chat = ScriptedChat(malformed, reply(text="Bạn muốn đi ngày nào?"))
    e = Engine(catalog, cfg, SessionStore(tmp_path), chat, today=lambda: date(2026, 10, 15))
    sid = e.create("first", "nothing")["id"]
    e.turn(sid, TurnInput(kind="text", text="đi Đà Lạt"), lambda *_: None)
    history = chat.seen[1][0]
    for message in history:
        for tool in message.get("tool_calls", ()):
            assert json.loads(tool["function"]["arguments"]) == {}
    assert any(message["role"] == "tool" and "not valid JSON" in message["content"] for message in history)
