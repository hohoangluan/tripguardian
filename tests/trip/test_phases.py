"""The 2-phase flow: the opening telling (the only turn that may ask in words) -> quiz (chips, other-gate) -> review -> done."""

from datetime import date

from test_engine import make, names, run  # noqa: F401  (shared fixtures and helpers)
from trip_fixtures import ScriptedChat


class ClearJudge:
    """A Judge stub for the quiz other-gate only."""

    def __init__(self, clear):
        self.clear = clear

    def clear_for_field(self, text, label):
        return self.clear


def told(e, sid):
    ev = run(e, sid, kind="text", text="3 ngày 2 đêm với bạn gái bằng ô tô tháng 12")
    e.chat.calls = 0  # the foundation turn may call the agent; quiz turns below must not
    return ev


def foundation_text(e, sid):
    """The telling, then the logistics cards (how they arrive, where they sleep, the hours) answered: the next card is
    the tastes, which is where most of these tests start."""
    ev = told(e, sid)
    assert [ev[-1][1]["qid"]] == ["arrival"]
    run(e, sid, kind="answer", qid="arrival", chips=("self",))
    run(e, sid, kind="answer", qid="lodging", chips=("none",))
    return run(e, sid, kind="answer", qid="stay_times", chips=("skip",))


def test_the_opening_telling_goes_straight_to_the_chip_cards(make):
    e = make()  # the agent is down: only the keyword rules read, the cards ask the rest
    sid = e.create("first", "nothing")["id"]
    card = told(e, sid)[-1][1]
    assert card["qid"] == "arrival" and e.load(sid)["phase"] == "quiz"
    st = e.store.get(sid).state
    assert (st.days.value, st.mobility.value, st.month.value) == (3, "car", 12) and st.meta.told


def test_the_agent_can_open_the_quiz_from_chat_before_the_first_card(make):
    from trip_fixtures import call, reply

    e = make()
    e.chat = ScriptedChat(reply(call("open_quiz"), text="Mình mở phần câu hỏi nhé."))
    sid = e.create("first", "nothing")["id"]
    card = run(e, sid, kind="text", text="mở phần câu hỏi")[-1][1]
    assert e.load(sid)["phase"] == "quiz" and card["qid"] != "conversation"
    assert "open_quiz" in e.chat.seen[-1][1]


def test_only_the_opening_turn_may_ask_in_words(make):
    from trip_fixtures import ask, fact, reply

    e = make()
    e.chat = ScriptedChat(reply(fact("days", "3", "3 ngày"), ask("Chill nghĩa là sao với bạn?", "Ít người", "View đẹp")))
    sid = e.create("first", "nothing")["id"]
    card = run(e, sid, kind="text", text="3 ngày đi chill")[-1][1]
    assert card["qid"].startswith("ask:") and e.load(sid)["phase"] == "chat"
    e.chat = ScriptedChat(reply(text="Mình ghi rồi."))
    card = run(e, sid, kind="text", text="kiểu yên yên")[-1][1]
    assert e.load(sid)["phase"] == "quiz" and not card["qid"].startswith("ask:")
    assert not {"ask_choice", "ask_text"} & set(e.chat.seen[-1][1])


def test_entering_the_quiz_starts_with_purpose(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    card = foundation_text(e, sid)[-1][1]
    assert card["qid"] == "purpose" and e.load(sid)["phase"] == "quiz"


def test_a_quiz_chip_writes_without_the_model(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    foundation_text(e, sid)
    card = run(e, sid, kind="answer", qid="purpose", chips=("relax",))[-1][1]
    st = e.store.get(sid).state
    assert st.purpose.value == "relax" and st.pace.value == "slow"  # the chip's drafts, no LLM
    assert card["qid"] == "crowd"  # vibe is skipped: relax already wishes long_stay + quiet


def test_skipping_a_quiz_card_advances_and_never_returns(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    foundation_text(e, sid)
    ev = run(e, sid, kind="answer", qid="purpose", chips=("skip",))
    assert ev[-1][1]["qid"] == "vibe"
    st = e.store.get(sid).state
    assert not st.purpose.known and "purpose" in st.meta.asked


def test_purpose_accepts_several_picks_first_is_primary(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    foundation_text(e, sid)
    card = run(e, sid, kind="answer", qid="offer_quiz", chips=("to_quiz",))[-1][1]
    assert card["multi"] is True
    card = run(e, sid, kind="answer", qid="purpose", chips=("relax", "photo"))[-1][1]
    st = e.store.get(sid).state
    assert st.purpose.value == "relax"  # first pick wins the single value
    assert {k: f.value for k, f in st.soft.items()} == {
        "long_stay_chill=present": "love", "noise=quiet": "love",
        "photo_spot=present": "love", "scenic_view=present": "love"}
    assert not st.pace.known  # conflicting inferred paces are dropped; pace_q asks later
    assert card["qid"] == "crowd"


def test_pressing_other_without_text_invites_typing(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    foundation_text(e, sid)
    ev = run(e, sid, kind="answer", qid="purpose", chips=("other",))
    assert ev[-1][1]["qid"] == "purpose"  # the card stays: the user types next


def test_a_clear_typed_answer_fills_through_prepass_without_the_model(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    foundation_text(e, sid)
    run(e, sid, kind="answer", qid="purpose", chips=("bond",))
    run(e, sid, kind="answer", qid="vibe", chips=("skip",))
    run(e, sid, kind="answer", qid="crowd", chips=("skip",))
    card = run(e, sid, kind="text", text="đi thong thả")[-1][1]  # typed on the pace card
    st = e.store.get(sid).state
    assert st.pace.value == "slow" and card["qid"] == "budget"
    assert e.chat.calls == 0


def test_an_unclear_typed_answer_goes_to_the_chat_then_resumes_the_quiz(make):
    from trip.api.engine import FALLBACK_SAY

    e = make()
    sid = e.create("first", "nothing")["id"]
    foundation_text(e, sid)
    run(e, sid, kind="answer", qid="purpose", chips=("bond",))
    ev = run(e, sid, kind="text", text="muốn chill chill")  # ambiguous: no single-key read
    assert ev[-1][1]["qid"] == "vibe"  # the chips stay available
    assert ("say", {"replace": FALLBACK_SAY}) in ev  # the agent is down; a live one clarifies
    assert e.store.get(sid).state.meta.other_qid == "vibe" and e.chat.calls == 1
    card = run(e, sid, kind="text", text="ít người")[-1][1]  # the gate reads crowd=low
    st = e.store.get(sid).state
    assert st.soft["crowd=low"].value == "love" and st.meta.other_qid is None
    assert card["qid"] == "crowd" and e.chat.calls == 1


def test_a_judged_clear_answer_fills_what_prepass_misses(make):
    e = make()
    e.judge = ClearJudge(True)
    sid = e.create("first", "nothing")["id"]
    foundation_text(e, sid)
    run(e, sid, kind="answer", qid="purpose", chips=("bond",))
    run(e, sid, kind="answer", qid="vibe", chips=("skip",))
    run(e, sid, kind="answer", qid="crowd", chips=("skip",))
    card = run(e, sid, kind="text", text="slow")[-1][1]  # no keyword read; Clef says clear
    assert e.store.get(sid).state.pace.value == "slow" and card["qid"] == "budget"
    assert e.chat.calls == 0


def test_a_judged_unclear_answer_goes_to_the_agent_with_resolving_other(make):
    from trip.api.engine import FALLBACK_SAY

    e = make()
    e.judge = ClearJudge(False)
    sid = e.create("first", "nothing")["id"]
    foundation_text(e, sid)
    run(e, sid, kind="answer", qid="purpose", chips=("bond",))
    ev = run(e, sid, kind="answer", qid="vibe", chips=("other",))  # no text yet: keep the card
    assert ev[-1][1]["qid"] == "vibe"
    ev = run(e, sid, kind="text", text="kiểu gì cũng được")  # Clef says unclear
    assert ("say", {"replace": FALLBACK_SAY}) in ev  # the agent is down; a live one clarifies
    assert e.store.get(sid).state.meta.other_qid == "vibe" and ev[-1][1]["qid"] == "vibe"


def test_skipping_through_the_queue_ends_in_review_then_done(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    foundation_text(e, sid)
    for _ in range(12):
        card = e.load(sid)["card"]
        if card["qid"] == "review":
            break
        run(e, sid, kind="answer", qid=card["qid"], chips=("skip",))
    else:
        raise AssertionError("the queue never ended")
    assert e.load(sid)["phase"] == "review"
    ev = run(e, sid, kind="answer", qid="review", chips=("show",))
    assert names(ev) == ["done"]


def test_a_removed_month_brings_back_the_dates_calendar(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    foundation_text(e, sid)
    run(e, sid, kind="edit", target="month", value=None)
    card = run(e, sid, kind="answer", qid="purpose", chips=("skip",))[-1][1]
    assert card["qid"] == "dates" and card["input"] == "date"
    ev = run(e, sid, kind="answer", qid="dates", value="2026-12-25")
    assert e.store.get(sid).state.start_date.value == date(2026, 12, 25)
    assert ev[-1][1]["qid"] == "vibe"


def test_show_compiles_with_unknowns_and_answers_an_open_signal_with_its_strictest_choice(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    ev = run(e, sid, kind="show")
    assert names(ev) == ["done"]  # nothing known: still done, unknowns ride along
    run(e, sid, kind="text", text="mẹ đau gối")
    assert e.load(sid)["understanding"]["ready"] is False
    ev = run(e, sid, kind="show")
    assert names(ev) == ["done"]
    hard = {(h["feature"], h["op"]) for h in ev[0][1]["search_input"]["hard_filters"]}
    assert {("steep_or_stairs", "ne"), ("long_walk", "ne")} <= hard  # only ever stricter, never looser


def test_when_the_chat_resolves_the_pending_card_the_quiz_moves_on(make):
    from trip_fixtures import fact, reply

    e = make()
    sid = e.create("first", "nothing")["id"]
    foundation_text(e, sid)
    run(e, sid, kind="answer", qid="purpose", chips=("bond",))
    run(e, sid, kind="text", text="muốn chill chill")  # unclear: pending vibe, agent clarifies
    assert e.store.get(sid).state.meta.other_qid == "vibe"
    e.chat = ScriptedChat(reply(fact("soft", "noise=quiet:love", "đẹp", op="add"),
                                text="Mình ghi chỗ yên tĩnh nhé."))
    card = run(e, sid, kind="text", text="chỗ nào cũng được miễn là đẹp")[-1][1]
    st = e.store.get(sid).state
    assert st.soft["noise=quiet"].value == "love" and st.meta.other_qid is None
    assert "vibe" in st.meta.asked and card["qid"] == "crowd"  # one card further, no repeat


def test_more_leaves_the_agents_question_and_starts_the_quiz(make):
    from trip_fixtures import ask, fact, reply

    e = make()
    e.chat = ScriptedChat(reply(fact("days", "3", "3 ngày"), ask("Chill nghĩa là sao với bạn?", "Ít người", "View đẹp")))
    sid = e.create("first", "nothing")["id"]
    card = run(e, sid, kind="text", text="3 ngày đi chill")[-1][1]
    assert card["qid"].startswith("ask:") and e.load(sid)["phase"] == "chat"
    ev = run(e, sid, kind="more")
    assert e.load(sid)["phase"] == "quiz" and not ev[-1][1]["qid"].startswith("ask:")
    assert not e.store.get(sid).state.meta.declined  # left open, not declined
    assert run(e, sid, kind="more")[-1][1]["qid"] == ev[-1][1]["qid"]  # in the quiz already: the same card


def drain_to_review(e, sid, limit=16):
    for _ in range(limit):
        card = e.load(sid)["card"]
        if card["qid"] == "review":
            return
        run(e, sid, kind="answer", qid=card["qid"], chips=("skip",))
    raise AssertionError("the queue never ended")


def test_requiz_brings_answered_cards_back_so_answers_can_change(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    foundation_text(e, sid)
    run(e, sid, kind="answer", qid="purpose", chips=("relax",))
    drain_to_review(e, sid)
    st = e.store.get(sid).state
    assert e.load(sid)["phase"] == "review" and st.purpose.value == "relax" and st.meta.asked
    card = run(e, sid, kind="requiz")[-1][1]
    assert e.load(sid)["phase"] == "quiz" and card["qid"] == "days"  # asked again although known
    st = e.store.get(sid).state
    assert st.meta.asked == () and st.meta.declined == () and st.meta.requiz
    assert st.days.value == 3 and st.purpose.value == "relax"  # values stay until picked otherwise
    assert any(t["role"] == "user" and t["text"] == "Làm lại trắc nghiệm" for t in e.store.get(sid).transcript)
    card = run(e, sid, kind="answer", qid="days", chips=("days:4",))[-1][1]  # change the answer
    assert e.store.get(sid).state.days.value == 4
    assert card["qid"] == "nights"  # the redo pass goes on, no repeat


def test_requiz_reasks_skipped_cards_then_review_then_done(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    foundation_text(e, sid)
    drain_to_review(e, sid)
    assert "purpose" in e.store.get(sid).state.meta.asked  # skipped once
    run(e, sid, kind="requiz")
    assert e.load(sid)["phase"] == "quiz"
    drain_to_review(e, sid)
    assert e.load(sid)["phase"] == "review"
    assert not e.store.get(sid).state.meta.requiz  # the flag clears at the review
    ev = run(e, sid, kind="answer", qid="review", chips=("show",))
    assert names(ev) == ["done"]


def test_the_agent_opens_the_quiz_when_asked(make):
    from trip_fixtures import call, reply

    e = make()
    sid = e.create("first", "nothing")["id"]
    foundation_text(e, sid)
    drain_to_review(e, sid)
    assert e.load(sid)["phase"] == "review"
    e.chat = ScriptedChat(reply(call("open_quiz"), text="Để mình mở lại trắc nghiệm nhé."))
    card = run(e, sid, kind="text", text="cho làm lại trắc nghiệm")[-1][1]
    assert "open_quiz" in e.chat.seen[-1][1]
    assert e.load(sid)["phase"] == "quiz" and card["qid"] == "days"
    assert e.store.get(sid).state.meta.requiz


def test_pause_keeps_quiz_progress_and_the_chat_goes_on(make):
    from trip_fixtures import ask, reply

    e = make()
    sid = e.create("first", "nothing")["id"]
    foundation_text(e, sid)
    run(e, sid, kind="answer", qid="purpose", chips=("relax",))
    assert e.load(sid)["card"]["qid"] == "crowd"
    ev = run(e, sid, kind="pause")
    st = e.store.get(sid).state
    assert e.load(sid)["phase"] == "paused" and st.meta.asked
    assert st.purpose.value == "relax"  # values stay
    assert e.load(sid)["card"]["qid"] == "conversation"
    assert any(a == "say" for a, _ in ev)
    assert any(t["role"] == "user" and t["text"] == "Tạm nghỉ trắc nghiệm" for t in e.store.get(sid).transcript)
    # paused chat: the agent may ask, pointed at what is still unknown
    e.chat = ScriptedChat(reply(ask("Bạn muốn đi kiểu nào?", "Thong thả", "Đi nhiều")))
    card = run(e, sid, kind="text", text="chưa biết chọn sao")[-1][1]
    assert card["qid"].startswith("ask:") and e.load(sid)["phase"] == "paused"


def test_resume_continues_the_quiz_where_paused(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    foundation_text(e, sid)
    assert e.load(sid)["card"]["qid"] == "purpose"
    run(e, sid, kind="pause")
    card = run(e, sid, kind="more")[-1][1]
    assert card["qid"] == "purpose"  # same card back: asked was kept, nothing re-asked
    assert e.load(sid)["phase"] == "quiz"


def test_pause_drops_a_half_resolved_typed_answer(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    foundation_text(e, sid)
    run(e, sid, kind="answer", qid="purpose", chips=("bond",))
    run(e, sid, kind="text", text="muốn chill chill")  # unclear: pending vibe
    assert e.store.get(sid).state.meta.other_qid == "vibe"
    run(e, sid, kind="pause")
    st = e.store.get(sid).state
    assert st.meta.other_qid is None and e.load(sid)["phase"] == "paused"


def test_pause_outside_quiz_keeps_the_card(make):
    e = make()
    sid = e.create("first", "nothing")["id"]
    assert e.load(sid)["card"]["qid"] == "frame"
    ev = run(e, sid, kind="pause")
    assert e.load(sid)["phase"] == "chat" and e.load(sid)["card"]["qid"] == "frame"
    assert [a for a, _ in ev] == ["card"]
