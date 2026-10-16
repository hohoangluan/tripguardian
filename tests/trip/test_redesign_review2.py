"""Review round 2 of the Trip redesign: defects found by running the 76 personas on the LAN Gemma agent.

R5 a tool call whose arguments are not valid JSON (Gemma does this under load) crashed the whole turn: the next model
call rebuilt the history with the broken arguments and LangChain raised JSONDecodeError. The turn must survive, the
model must be told the call was malformed, and the history it sees must stay valid JSON.
"""

import json
from datetime import date
from pathlib import Path

from trip_fixtures import ScriptedChat, say

from trip.api.engine import Engine, TurnInput
from trip.infrastructure.sessions import SessionStore

BROKEN = {"id": "call_bad", "name": "record_fact", "args": '{"field": "days", "op": "set", "value": "3",, "quote"'}


def _reply(*calls, text=""):
    from langchain_core.messages import AIMessageChunk
    return AIMessageChunk(content=text, tool_call_chunks=[dict(c, index=i) for i, c in enumerate(calls)])


def test_r5_malformed_tool_arguments_do_not_crash_the_turn(catalog, cfg, tmp_path):
    chat = ScriptedChat(_reply(BROKEN), say("Bạn đi mấy ngày?"))
    e = Engine(catalog, cfg, SessionStore(Path(tmp_path)), chat, today=lambda: date(2026, 10, 15))
    sid = e.create("first", "nothing")["id"]
    events = []
    e.turn(sid, TurnInput(kind="text", text="đi 3 ngày nha"), lambda ev, d: events.append((ev, d)))
    assert chat.calls == 2  # the model got a second chance
    history = chat.seen[1][0]
    for m in history:
        for c in m.get("tool_calls") or ():
            json.loads(c["function"]["arguments"] if "function" in c else json.dumps(c.get("args", {})))
    told = [m for m in history if m.get("role") == "tool"]
    assert told and any("json" in str(m.get("content")).lower() for m in told)
    s = e.store.get(sid)
    assert s.transcript[-1]["role"] == "agent" and s.transcript[-1]["text"]


# ---------- R6: who goes is read by code first (bench: 9/47 personas lost it to the model) ----------

import pytest  # noqa: E402

from trip import TripState  # noqa: E402
from trip.domain import deck  # noqa: E402
from trip.domain.guard import bad_say, trim_say  # noqa: E402
from trip.domain.prepass import prepass  # noqa: E402

TODAY = date(2026, 10, 15)


@pytest.mark.parametrize("text, who", [
    ("mẹ mình ngồi xe lăn, cả nhà 4 người muốn đưa mẹ đi đà lạt 3 ngày", {"parents"}),
    ("vợ đang mang bầu 5 tháng, muốn đi nhẹ nhàng 2 ngày", {"partner"}),
    ("tụi tui 4 đứa đi đl quẩy tới bến", {"friends"}),
    ("di da lat 3 ngay 2 dem voi gia dinh co con nho 4 tuoi, di oto", {"kids"}),
    ("đi một mình 3 ngày, đi bộ với taxi", {"solo"}),
    ("nhóm 2 cặp đôi với 1 bé 5 tuổi và 1 ông 70 tuổi, đi 2 xe ô tô", {"partner", "friends", "kids", "parents"}),
    ("mẹ mình đi được chừng 1 tiếng là phải ngồi nghỉ", {"parents"}),
    ("đi với bố 2 ngày", {"parents"}),
    ("thích ăn bò nướng, mang kem chống nắng", set()),
    ("2 mẹ con đi chợ", set()),  # me + my mother, or me + my child: never guessed
])
def test_r6_prepass_suggests_who_goes_from_the_real_phrases(text, who):
    got = {p.value for p in prepass(text, TODAY).suggestions if p.field == "companions"}
    assert got == who


def test_r6_the_companions_tab_is_prefilled_from_what_code_read(catalog, cfg):
    from trip.api.engine import Engine
    chat = ScriptedChat(say("Bạn đi lại bằng gì?"), say(""))  # the deck is built from the state, not this reply
    e = Engine(catalog, cfg, SessionStore(_tmp()), chat, today=lambda: TODAY)
    sid = e.create("first", "nothing")["id"]
    e.turn(sid, TurnInput(kind="text", text="tụi tui 4 đứa đi 3 ngày"), lambda *_: None)
    state = e.store.get(sid).state
    tab = next(t for t in deck.build(state, catalog, cfg, ask="companions").tabs if t.qid == "companions")
    pre = [o for o in tab.options if o.prefilled]
    assert [o.id for o in pre] == ["friends"] and "tụi tui 4 đứa" in pre[0].because
    assert state.people.value == 4 and state.people.source == "user"


def _tmp():
    import tempfile
    return Path(tempfile.mkdtemp())


# ---------- R7: answer in the user's language (bench: 2/2 English personas got Vietnamese) ----------

def test_r7_a_vietnamese_reply_to_an_english_message_is_refused(catalog):
    heard = "We are 2 couples from Korea, 3 days in Dalat, we love coffee and night markets"
    assert bad_say("Mình đã ghi nhận chuyến đi của bạn, bạn đi lại bằng gì?", heard, TripState(), catalog, set())
    assert bad_say("Got it. How will you get around in Dalat?", heard, TripState(), catalog, set()) is None


def test_r7_a_vietnamese_message_typed_without_marks_is_still_vietnamese(catalog):
    heard = "di da lat 3 ngay 2 dem voi gia dinh co con nho 4 tuoi"
    assert bad_say("Mình ghi nhận rồi, cả nhà đi lại bằng gì?", heard, TripState(), catalog, set()) is None


def test_r7_the_agent_is_told_the_language_to_answer_in(catalog, cfg, tmp_path):
    chat = ScriptedChat(say("Got it. How will you get around?"), say(""))
    e = Engine(catalog, cfg, SessionStore(Path(tmp_path)), chat, today=lambda: TODAY)
    sid = e.create("first", "nothing")["id"]
    e.turn(sid, TurnInput(kind="text", text="We are 2 couples, 3 days in Dalat, we love coffee"), lambda *_: None)
    system = chat.seen[0][0][0]["content"]
    assert "English" in system


# ---------- R8: at most two sentences, 250 characters (bench: 22/102 replies were longer) ----------

def test_r8_a_long_reply_is_cut_to_two_sentences_keeping_the_question():
    long = ("Mình đã ghi nhận là bạn muốn đi Đà Lạt 3 ngày cùng người yêu bằng xe máy. "
            "Đà Lạt tháng 12 rất đẹp với hoa dã quỳ nở vàng khắp các con đường và đồi núi. "
            "Ngoài ra thời tiết khá lạnh nên bạn nhớ mang áo ấm và găng tay khi đi xe máy buổi tối. "
            "Bạn muốn đi kiểu thong thả hay đi nhiều chỗ?")
    out = trim_say(long)
    assert len(out) <= 250 and out.endswith("Bạn muốn đi kiểu thong thả hay đi nhiều chỗ?")
    assert len([s for s in out.replace("?", ".").split(".") if s.strip()]) <= 2


def test_r8_a_short_reply_is_left_alone():
    assert trim_say("Ok, mình tìm luôn nhé.") == "Ok, mình tìm luôn nhé."
