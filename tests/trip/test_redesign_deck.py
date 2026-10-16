"""Trip redesign part 3: one deck card, built by code; ask_user is post-checked; confirm questions by plan consequence.

Test ids DK1-DK20 of docs/superpowers/specs/2026-10-15-trip-understanding-architecture.md §5.4. A good deck asks
the fewest questions that change the plan, never repeats what the user said, and never blocks the user.
"""

from datetime import date
from pathlib import Path

import pytest
from trip_fixtures import ScriptedChat, call, reply, say

from trip import TripState
from trip.agent import AgentError
from trip.api.engine import Engine, TurnInput
from trip.domain import ask, deck
from trip.domain.state import Draft, Evidence, Update, apply
from trip.infrastructure.sessions import SessionStore

TODAY = date(2026, 10, 15)


def said(value, source="user", quote="q", turn=1):
    return {"value": value, "source": source, "confidence": "high" if source == "user" else "medium",
            "status": "confirmed" if source == "user" else "unknown", "evidence": [{"turn": turn, "quote": quote}]}


DATES = {"start_date": said("2026-11-20"), "days": said(3), "checkin_at": said("14:00"), "checkout_at": said("12:00")}
READY = {**DATES, "companions": said(["partner"]), "people": said(2), "mobility": said("motorbike"),
         "care": said("none"), "pace": said("normal"), "budget_unlimited": said(True),
         "lodging": said({"text": "Khách sạn Colline", "kind": "address"})}


def st(**data):
    return TripState.model_validate(data)


def qids(d):
    return [t.qid for t in d.tabs]


def build(state, catalog, cfg, **kw):
    return deck.build(state, catalog, cfg, **kw)


# ---------- DK1-DK5: required tabs ----------

def test_dk1_an_empty_trip_opens_no_required_tab_without_the_agent(catalog, cfg):
    d = build(TripState(), catalog, cfg)
    assert qids(d) == []  # Only the agent opens a required topic in chat.
    assert qids(build(TripState(), catalog, cfg, ask="mobility")) == ["mobility"]  # the topic the agent chose
    assert qids(build(TripState(), catalog, cfg, at="gate"))[:4] == ["trip", "companions", "mobility", "care"]
    assert (d.left, d.total) == (7, 7)


def test_dk2_a_said_answer_is_never_asked_again(catalog, cfg):
    d = build(st(**DATES, mobility=said("motorbike"), companions=said(["friends"]), people=said(4)), catalog, cfg)
    assert "trip" not in qids(d) and "mobility" not in qids(d) and "companions" not in qids(d)
    assert d.left == 4


def test_dk3_a_guess_is_a_prefilled_chip_that_says_why(catalog, cfg):
    d = build(st(**{k: v for k, v in READY.items() if k != "pace"}, pace=said("slow", source="inferred", quote="thong thả thôi")), catalog, cfg,
              at="gate")
    tab = next(t for t in d.tabs if t.qid == "pace")
    pre = [o for o in tab.options if o.prefilled]
    assert [o.id for o in pre] == ["slow"] and "thong thả thôi" in pre[0].because


def test_dk4_a_contradiction_is_asked_with_nothing_chosen_for_the_user(catalog, cfg):
    state = st(**{k: v for k, v in READY.items() if k != "pace"}, meta={"conflicts": ["pace"]})
    tab = next(t for t in build(state, catalog, cfg, at="gate").tabs if t.qid == "pace")
    assert not any(o.prefilled for o in tab.options) and "cả hai" in tab.why


def test_dk5_a_skipped_required_tab_waits_for_the_gate(catalog, cfg):
    state = st(**DATES, meta={"declined": ["companions"]})
    assert "companions" not in qids(build(state, catalog, cfg, at="understand"))
    assert "companions" in qids(build(state, catalog, cfg, at="gate"))


def test_dk5_the_gate_deck_shows_only_what_is_missing(catalog, cfg):
    d = build(st(**{k: v for k, v in READY.items() if k != "pace"}), catalog, cfg, at="gate")
    assert qids(d) == ["pace"] and d.left == 1


def test_dk19_a_date_the_user_typed_is_theirs_not_a_guess(catalog, cfg, tmp_path):
    chat = ScriptedChat(say("Bạn đi lại bằng gì?"), say(""))
    e = Engine(catalog, cfg, SessionStore(Path(tmp_path)), chat, today=lambda: TODAY)
    sid = e.create("first", "nothing")["id"]
    e.turn(sid, TurnInput(kind="text", text="đi Đà Lạt 20-22/11, 2 người, ngân sách 10 triệu"), lambda *_: None)
    state = e.store.get(sid).state
    assert all(getattr(state, f).source == "user" for f in ("start_date", "days", "people", "budget_vnd"))
    tab = next(t for t in build(state, catalog, cfg, ask="trip").tabs if t.qid == "trip")
    assert "dates" not in tab.inputs  # only the two hours are left to ask on tab ①


# ---------- DK6-DK11: confirm questions, each tied to what it changes in the plan ----------

def test_dk6_cloud_hunting_asks_which_day_to_wake_early(catalog, cfg):
    tabs = deck.confirm_tabs(st(**READY, soft={"cloud_hunting=present": said("love", quote="săn mây")}), catalog, cfg)
    tab = next(t for t in tabs if t.qid == "confirm.early")
    assert {"day.0", "day.1", "day.2", "any", "no"} <= {o.id for o in tab.options}
    day2 = next(o for o in tab.options if o.id == "day.1")
    after = _tap(st(**READY), day2)
    assert after.frame.days[0].index == 1 and after.frame.days[0].start <= "05:30"


def test_dk7_small_kids_ask_about_a_nap_at_the_lodging(catalog, cfg):
    tabs = deck.confirm_tabs(st(**{**READY, "companions": said(["partner", "baby"]), "people": said(3)}), catalog, cfg)
    tab = next(t for t in tabs if t.qid == "confirm.nap")
    after = _tap(st(**READY), next(o for o in tab.options if o.id == "yes"))
    (b,) = after.frame.busy
    assert (b.kind in ("rest", "nap"), b.where, b.on, b.start, b.end) == (True, "lodging", "all", "12:00", "14:00")


def test_dk8_night_plans_on_a_motorbike_warn_about_dark_roads(catalog, cfg):
    tabs = deck.confirm_tabs(st(**READY, soft={"live_music=present": said("love", quote="nhạc sống")}), catalog, cfg)
    tab = next(t for t in tabs if t.qid == "confirm.evening")
    assert "tối" in tab.why and ("đường" in tab.why or "đèo" in tab.why)
    after = _tap(st(**READY), next(o for o in tab.options if o.id == "22"))
    assert after.day_end.value == "22:00"


def test_dk8_night_plans_by_hired_car_ask_without_the_road_warning(catalog, cfg):
    state = st(**{**READY, "mobility": said("car"), "driver": said("hired")},
               soft={"live_music=present": said("love", quote="nhạc sống")})
    tab = next(t for t in deck.confirm_tabs(state, catalog, cfg) if t.qid == "confirm.evening")
    assert "đèo" not in tab.why and "đường tối" not in tab.why


def test_dk9_more_must_go_places_than_the_days_hold_asks_what_to_keep(catalog, cfg):
    anchors = [{"text": f"Quán Yên Tĩnh Số {i}", "place_id": f"0x{i:x}:0x1", "state": "matched"} for i in range(1, 7)]
    state = st(**{**READY, "days": said(1), "start_date": said("2026-11-20"), "pace": said("slow")}, anchors=anchors)
    assert "confirm.priority" in [t.qid for t in deck.confirm_tabs(state, catalog, cfg)]


def test_dk10_an_overnight_coach_asks_rest_first_or_go(catalog, cfg):
    state = st(**READY, frame={"arrive": said({"at": "2026-11-20T04:00", "how": "bus"})})
    tab = next(t for t in deck.confirm_tabs(state, catalog, cfg) if t.qid == "confirm.arrive")
    rest = _tap(state, next(o for o in tab.options if o.id == "rest"))
    assert rest.frame.days[0].index == 0 and rest.frame.days[0].start >= "08:00"


def test_dk11_a_confirm_question_is_not_asked_when_the_answer_is_known(catalog, cfg):
    state = st(**READY, soft={"cloud_hunting=present": said("love", quote="săn mây")},
               frame={"days": [{"index": 1, "start": "05:00", "evidence": [{"turn": 1, "quote": "5h sáng ngày 2"}]}]})
    assert "confirm.early" not in [t.qid for t in deck.confirm_tabs(state, catalog, cfg)]


def test_dk11_a_skipped_confirm_question_never_comes_back(catalog, cfg):
    state = st(**READY, soft={"cloud_hunting=present": said("love", quote="săn mây")},
               meta={"declined": ["confirm.early"]})
    assert "confirm.early" not in [t.qid for t in deck.confirm_tabs(state, catalog, cfg)]


# ---------- DK12-DK14: how many questions ----------

def test_dk12_required_first_then_confirm_at_most_four_tabs(catalog, cfg):
    state = st(**{k: v for k, v in READY.items() if k not in ("pace", "budget_unlimited", "companions", "people")},
               companions=said(["partner", "baby"]), people=said(3),
               soft={"cloud_hunting=present": said("love", quote="săn mây"),
                     "live_music=present": said("love", quote="nhạc sống")})
    d = build(state, catalog, cfg, at="gate")
    assert qids(d)[:2] == ["pace", "budget"] and len(d.tabs) <= 4
    assert all(t.kind == "confirm" for t in d.tabs[2:])


def test_dk13_two_skips_stop_the_optional_questions_not_the_required_ones(catalog, cfg):
    state = st(**{k: v for k, v in READY.items() if k != "pace"},
               soft={"cloud_hunting=present": said("love", quote="săn mây")},
               meta={"soft_skips": 2})
    d = build(state, catalog, cfg, at="gate")
    assert qids(d) == ["pace"]


def test_dk14_a_user_in_a_hurry_gets_no_optional_question(catalog, cfg, tmp_path):
    chat = ScriptedChat(say("Ok, mình tìm luôn nhé."), say(""))
    e = Engine(catalog, cfg, SessionStore(Path(tmp_path)), chat, today=lambda: TODAY)
    sid = e.create("first", "nothing")["id"]
    e.turn(sid, TurnInput(kind="text", text="săn mây, gợi ý luôn đi khỏi hỏi"), lambda *_: None)
    d = build(e.store.get(sid).state, catalog, cfg)
    assert d.tabs == ()


# ---------- DK15: the agent's own questions are checked by code ----------

def q(*options, question="Bạn thích quán kiểu nào?", header="Kiểu quán", why="Để chọn đúng quán"):
    return {"question": question, "header": header, "why": why, "multi": False,
            "options": [{"label": label, "description": "", "writes": writes} for label, writes in options]}


def soft(key):
    return [{"field": "soft", "op": "add", "value": f"{key}:love"}]


def test_dk15_a_question_about_something_the_user_said_is_dropped(catalog, cfg):
    state = st(**READY)
    out = ask.check([q(("Xe máy", [{"field": "mobility", "op": "set", "value": "motorbike"}]),
                       ("Ô tô", [{"field": "mobility", "op": "set", "value": "car"}]))], state, catalog, cfg)
    assert out == ()


def test_dk15_options_that_cannot_be_written_or_find_nothing_are_dropped(catalog, cfg):
    out = ask.check([q(("Yên tĩnh", soft("noise=quiet")), ("Nhạc sống", soft("live_music=present")),
                       ("Không có thật", soft("no_such_feature=present")), ("Cắm trại", soft("camping=present")))],
                    TripState(), catalog, cfg)
    (tab,) = out
    labels = [o.label for o in tab.options if o.id not in ("other", "skip")]
    assert labels == ["Yên tĩnh", "Nhạc sống"] and all(o.count for o in tab.options if o.label in labels)
    assert {"other", "skip"} <= {o.id for o in tab.options}


def test_dk15_the_words_of_an_agent_option_are_the_apps_never_the_models(catalog, cfg):
    # the model picks the readings; "Ngày 1" is a label it made up, the write behind it has no fixed wording
    out = ask.check([q(("Ngày 1", soft("noise=quiet")), ("Chỗ siêu xịn nhất", soft("live_music=present")),
                       ("Một nửa", [{"field": "soft", "op": "add", "value": "noise=quiet:love"},
                                    {"field": "soft", "op": "add", "value": "live_music=present:love"}]))],
                    TripState(), catalog, cfg)
    (tab,) = out
    assert [o.label for o in tab.options if o.id not in ("other", "skip")] == ["Yên tĩnh", "Nhạc sống"]
    assert all(o.description.startswith("Mình ưu tiên") for o in tab.options if o.id not in ("other", "skip"))


def test_dk15_an_agent_option_can_never_write_a_hard_limit(catalog, cfg):
    hard = [{"field": "hard", "op": "add", "value": "steep_or_stairs!=present"}]
    out = ask.check([q(("Tránh dốc", hard), ("Yên tĩnh", soft("noise=quiet")), ("Nhạc sống", soft("live_music=present")))],
                    TripState(), catalog, cfg)
    assert "Tránh dốc" not in [o.label for t in out for o in t.options]


def test_dk15_a_question_whose_options_give_the_same_places_is_dropped(catalog, cfg):
    out = ask.check([q(("Yên tĩnh", soft("noise=quiet")), ("Ngồi lâu", soft("long_stay_chill=present")))],
                    TripState(), catalog, cfg)
    assert out == ()


def test_dk15_too_long_or_field_named_questions_are_dropped(catalog, cfg):
    long_q = q(("Yên tĩnh", soft("noise=quiet")), ("Nhạc sống", soft("live_music=present")), question="x" * 120)
    leaky = q(("Yên tĩnh", soft("noise=quiet")), ("Nhạc sống", soft("live_music=present")),
              question="Bạn chọn noise hay live_music?")
    assert ask.check([long_q, leaky], TripState(), catalog, cfg) == ()


# ---------- DK16-DK18: through the engine ----------

def test_dk20_a_confirmation_can_open_without_an_agent_required_question(catalog, cfg):
    # A confirmation of the user's taste can open while required topics are still missing.
    state = st(soft={"cloud_hunting=present": said("love", quote="săn mây")}, **DATES)
    assert qids(build(state, catalog, cfg)) == ["confirm.early"]
    answered = st(soft={"cloud_hunting=present": said("love", quote="săn mây")}, **DATES)
    assert [t.qid for t in deck.confirm_tabs(answered, catalog, cfg)] == ["confirm.early"]


def test_dk20_with_nothing_of_the_users_own_the_first_deck_has_no_tabs(catalog, cfg):
    assert build(TripState(), catalog, cfg).tabs == ()


def test_dk16_an_agent_question_is_the_one_tab_and_a_tap_is_written_by_code(catalog, cfg, tmp_path):
    question = q(("Yên tĩnh", soft("noise=quiet")), ("Nhạc sống", soft("live_music=present")))
    chat = ScriptedChat(reply(call("ask_user", questions=[question])), say("Bạn thích quán kiểu nào?"))
    e = Engine(catalog, cfg, SessionStore(Path(tmp_path)), chat, today=lambda: TODAY)
    sid = e.create("first", "nothing")["id"]
    e.turn(sid, TurnInput(kind="text", text="đi cà phê chill"), lambda *_: None)
    card = e.load(sid)["card"]
    assert card["kind"] == "deck" and [t["kind"] for t in card["tabs"]] == ["agent"]
    calls = chat.calls
    agent_tab = card["tabs"][-1]
    quiet = next(o for o in agent_tab["options"] if o["label"] == "Yên tĩnh")
    e.turn(sid, TurnInput(kind="deck", answers={agent_tab["qid"]: [quiet["id"]]}), lambda *_: None)
    state = e.store.get(sid).state
    # written by code as the user's answer; the agent then reacts once (the scripted reply above)
    assert chat.calls == calls + 1 and state.soft["noise=quiet"].source == "user"


def test_dk17_typing_another_answer_goes_through_the_agent(catalog, cfg, tmp_path):
    question = q(("Yên tĩnh", soft("noise=quiet")), ("Nhạc sống", soft("live_music=present")))
    chat = ScriptedChat(reply(call("ask_user", questions=[question])), say("ok"), say("Ghi nhận."), say(""))
    e = Engine(catalog, cfg, SessionStore(Path(tmp_path)), chat, today=lambda: TODAY)
    sid = e.create("first", "nothing")["id"]
    e.turn(sid, TurnInput(kind="text", text="đi cà phê chill"), lambda *_: None)
    tab = e.load(sid)["card"]["tabs"][-1]
    before = chat.calls
    e.turn(sid, TurnInput(kind="deck", answers={tab["qid"]: ["other"]}, text="quán có mèo"), lambda *_: None)
    assert chat.calls > before


def test_dk18_a_second_busy_block_is_added_not_written_over():
    ev = Evidence(turn=1, tool="deck:test")
    nap = {"label": "nghỉ trưa", "kind": "rest", "where": "lodging", "start": "12:00", "end": "14:00", "on": "all"}
    dinner = {"label": "đặt bàn", "kind": "event", "where": "Nhà hàng X", "start": "19:00", "end": "20:30", "on": [1]}
    s = TripState()
    for b in (nap, dinner, nap):
        s = apply(s, Update(field="frame.busy", op="add", value=b, source="user", confidence="high", evidence=ev))
    assert [b.label for b in s.frame.busy] == ["nghỉ trưa", "đặt bàn"]
    s = apply(s, Update(field="frame.busy", op="remove", value="đặt bàn", source="user", confidence="high",
                        evidence=ev))
    assert [b.label for b in s.frame.busy] == ["nghỉ trưa"]


def test_dk18_a_day_plan_is_merged_by_its_index():
    ev = Evidence(turn=1, tool="deck:test")
    s = TripState()
    s = apply(s, Update(field="frame.days", op="add", value={"index": 1, "start": "05:00"}, source="user",
                        confidence="high", evidence=ev))
    s = apply(s, Update(field="frame.days", op="add", value={"index": 2, "intensity": "free"}, source="user",
                        confidence="high", evidence=ev))
    s = apply(s, Update(field="frame.days", op="add", value={"index": 1, "end": "19:00"}, source="user",
                        confidence="high", evidence=ev))
    by = {d.index: d for d in s.frame.days}
    assert (by[1].start, by[1].end, by[2].intensity) == ("05:00", "19:00", "free")


def _tap(state, option):
    """Apply an option's writes as the user's tap (what the engine does for a deck answer)."""
    from trip.domain.state import apply_drafts
    return apply_drafts(state, option.writes, state.meta.turn + 1, tool="deck:test")
