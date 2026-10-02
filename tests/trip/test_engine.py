from datetime import date

import pytest
from trip_fixtures import FakeAgent

from trip.agent import AgentError
from trip.engine import FALLBACK_SAY, Engine, TurnInput
from trip.sessions import SessionStore


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
    return run(e, sid, kind="answer", qid="frame", chips=("days:3", "who:solo", "mobility:car"))


def test_create_opens_with_frame(make):
    v = make().create("first", "nothing")
    assert v["card"]["qid"] == "frame" and v["transcript"][0]["role"] == "agent"
    assert all(set(c) == {"id", "label", "row"} for c in v["card"]["chips"])


def test_chip_answer_needs_no_agent(make):
    agent = FakeAgent(error=AssertionError("must not be called"))
    e = make(agent)
    sid = e.create("first", "nothing")["id"]
    ev = answer_frame(e, sid)
    assert names(ev) == ["state", "card"] and ev[1][1]["qid"] == "dates" and agent.calls == 0


def test_text_turn_streams_say_then_state_then_card(make):
    agent = FakeAgent(plan(updates=[{"field": "days", "op": "set", "value": "3", "quote": "3 ngày", "how": "said"}]),
                      chunks=("Mình ", "hiểu rồi."))
    e = make(agent)
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi 3 ngày")
    assert names(ev) == ["preview", "say", "say", "state", "card"]
    assert ev[3][1]["understanding"]["trip"][0]["value"] == 3
    assert agent.fields["text"] == "đi 3 ngày"


def test_agent_failure_falls_back_to_policy(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="text", text="đi 3 ngày bằng xe máy")
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
    assert v["card"]["qid"] == "dates" and [t["role"] for t in v["transcript"]] == ["agent", "agent", "user"]


def test_unknown_session_raises(make):
    with pytest.raises(KeyError):
        make().load("0123456789ab")
