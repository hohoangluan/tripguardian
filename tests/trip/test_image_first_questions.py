"""A question the agent proposes must reach the user: cut to what the post-check accepts, never dropped in silence;
a broad taste named in everyday words gets its photo card."""

from datetime import date
from pathlib import Path

from trip_fixtures import ScriptedChat, call, reply

from trip.agent.tool_schemas import AskUser
from trip.api.engine import Engine, TurnInput
from trip.domain import ask, drill
from trip.domain.state import TripState
from trip.infrastructure.sessions import SessionStore

TODAY = date(2026, 10, 16)


def question(header="Trải nghiệm đặc biệt", text="Một trải nghiệm đặc biệt với hai bạn nghiêng về kiểu nào dưới đây?", keys=("noise=quiet", "live_music=present")):
    return {"question": text, "header": header, "options": [
        {"label": "x", "writes": [{"field": "soft", "op": "add", "value": k + ":love"}]} for k in keys]}


def test_a_long_header_and_question_are_cut_to_what_the_post_check_accepts(catalog, cfg):
    parsed = AskUser.model_validate({"questions": [question(text="Câu hỏi " + "rất dài " * 20)]}).model_dump()["questions"]
    assert len(parsed[0]["header"]) <= 12 and len(parsed[0]["question"]) <= 90
    assert ask.check(parsed, TripState(), catalog, cfg), "the cut question must survive ask.check"


def test_a_question_the_post_check_drops_still_gets_the_agents_words(catalog, cfg, tmp_path):
    bad = question(keys=("food_street=present", "night_market=present"))  # no fixed wording: both options are dropped
    chat = ScriptedChat(reply(call("ask_user", questions=[bad])))
    e = Engine(catalog, cfg, SessionStore(Path(tmp_path)), chat, today=lambda: TODAY)
    sid = e.create("first", "nothing")["id"]
    said = []
    e.turn(sid, TurnInput(kind="text", text="trải nghiệm gì đó đặc biệt đi"), lambda ev, d: said.append(d) if ev == "say" else None)
    assert "".join(d.get("replace", "") + d.get("delta", "") for d in said).strip() or e.load(sid)["transcript"][-1]["text"]
    assert any(t["role"] == "agent" and t["text"] == bad["question"] for t in e.store.get(sid).transcript)


def test_everyday_food_and_night_words_open_their_photo_topics():
    assert drill.topics("Mình muốn ăn cho đã: quán ngon, đồ nướng và chợ đêm.") == ["ăn uống", "về đêm"]
    assert drill.topics("đi cafe") == ["cà phê"]
    assert drill.topics("không muốn ăn ngon") == []
