"""Part 4 integration and read-only corpus adapters; all data and scores are local."""

import json
from datetime import date
from types import SimpleNamespace

import pytest
from trip_fixtures import ScriptedChat, call, rec, reply, say

from trip import Catalog, TripState, compile_search_input
from trip.agent.tools import TurnTools
from trip.api.engine import Engine, TurnInput
from trip.domain import deck, drill
from trip.infrastructure.looks import Looks
from trip.infrastructure.sessions import SessionStore

from test_redesign_drill import FakeLooks, big, ids, variant


def visual_question():
    return {"header": "Săn mây", "question": "Săn mây kiểu nào?", "why": "Vì bạn nói săn mây.",
            "visual": True, "topic": "săn mây", "multi": True,
            "options": [variant(label, cue) for label, cue in
                        (("Sương sớm", "sương"), ("Trời trong", "trong"),
                         ("Hoàng hôn", "hoàng hôn"), ("Bình minh", "bình minh"))]}


@pytest.mark.parametrize("action", ["select", "skip"])
def test_visual_drill_survives_reload_and_the_agent_reads_its_answer(big, cfg, tmp_path, action):
    looks = FakeLooks({cue: [(p, .2) for p in ids(1, 41)]
                       for cue in ("sương", "trong", "hoàng hôn", "bình minh")})
    chat = ScriptedChat(reply(call("ask_user", questions=[visual_question()])), say("Rõ rồi."))
    engine = Engine(big, cfg, SessionStore(tmp_path), chat, today=lambda: date(2026, 10, 15), looks=looks)
    sid = engine.create("first", "nothing")["id"]
    engine.turn(sid, TurnInput(kind="text", text="muốn săn mây"), lambda *_: None)
    tab = next(t for t in engine.load(sid)["card"]["tabs"] if t["kind"] == "drill")
    # every variant with a real photo is shown (the stage shows them all), then Other and Skip
    assert len(tab["options"]) == 6 and all(o.get("photo") for o in tab["options"][:4])
    assert all("writes" not in o for o in tab["options"])
    assert engine.store.get(sid).state.drills[0].tab is not None
    before_calls, photo_calls = chat.calls, len(looks.calls)
    reloaded = SessionStore(tmp_path).get(sid)
    assert reloaded.state.drills[0].tab.options[0].photo
    engine.store.restore(reloaded)
    picked = "skip" if action == "skip" else tab["options"][0]["id"]
    engine.turn(sid, TurnInput(kind="deck", answers={tab["qid"]: [picked]}), lambda *_: None)
    st = engine.store.get(sid).state
    assert st.drills[0].status == ("skipped" if action == "skip" else "done")
    # Code writes the choice and reuses the stored photos; the agent reads the answer once.
    assert chat.calls == before_calls + 1 == 2 and len(looks.calls) == photo_calls
    assert [(t["qid"], t["kind"]) for t in engine.load(sid)["card"]["tabs"]] == [("confirm.early", "confirm")]
    assert "drill" not in [t.kind for t in deck.build(st, big, cfg).tabs]
    assert drill.note(st, "săn mây", 3).drills == st.drills
    if action == "select":
        assert compile_search_input(st).vibes[0].places


def test_second_visual_request_never_rebuilds_the_topic(big, cfg, tmp_path):
    looks = FakeLooks({cue: [(p, .2) for p in ids(1, 41)]
                       for cue in ("sương", "trong", "hoàng hôn", "bình minh")})
    engine = Engine(big, cfg, SessionStore(tmp_path), ScriptedChat(), looks=looks)
    sid = engine.create("first", "nothing")["id"]
    session = engine.store.get(sid)
    session.state = drill.note(TripState(), "săn mây", 1)
    tools = TurnTools(session.state, "săn mây", 1, big, date(2026, 10, 15))
    tools.asked = {"kind": "agent", "questions": [visual_question()]}
    engine._asked(session, tools, 1)
    calls = len(looks.calls)
    engine._asked(session, tools, 2)
    assert len(looks.calls) == calls and session.state.drills[0].status == "pending"


def test_no_matching_photos_closes_the_topic(big, cfg, tmp_path):
    engine = Engine(big, cfg, SessionStore(tmp_path), ScriptedChat(), looks=FakeLooks({}))
    sid = engine.create("first", "nothing")["id"]
    session = engine.store.get(sid)
    session.state = drill.note(TripState(), "săn mây", 1)
    tools = TurnTools(session.state, "săn mây", 1, big, date(2026, 10, 15))
    tools.asked = {"kind": "agent", "questions": [visual_question()]}
    engine._asked(session, tools, 1)
    assert session.state.drills[0].status == "none"


def test_dish_tool_runs_through_the_text_turn(big, cfg, tmp_path):
    chat = ScriptedChat(reply(call("record_fact", say="Bánh căn nhé.", facts=[
        {"field": "dish", "op": "add", "value": "bánh căn", "quote": "bánh căn", "how": "said"}])))
    engine = Engine(big, cfg, SessionStore(tmp_path), chat)
    sid = engine.create("first", "nothing")["id"]
    engine.turn(sid, TurnInput(kind="text", text="muốn ăn bánh căn"), lambda *_: None)
    assert engine.store.get(sid).state.wishes.dishes[0].dish == "bánh căn"


def test_photo_scores_use_best_hit_and_keep_the_minimum_threshold(catalog):
    a, b = (p.id for p in catalog.places[:2])
    def hit(pid, score):
        return SimpleNamespace(place_id=pid, score=score)
    ix = SimpleNamespace(cfg={"search": {"min_text_photo": .08}}, embed_text=lambda q: q,
                         search_photos=lambda vec, within: [hit(a, .1), hit(a, .3), hit(b, .07), hit("outside", .9)])
    assert Looks(catalog, index=ix).scored_by_cues(["sương"]) == [(a, .3)]


def test_retrieval_scores_are_returned_without_replacing_them(catalog):
    pid = catalog.places[0].id
    seen = []
    def semantic(q, within, mode):
        seen.append((within, mode))
        return [SimpleNamespace(place_id=pid, score=.42), SimpleNamespace(place_id="outside", score=.9)]
    looks = Looks(catalog, warm=False, retrieval=SimpleNamespace(semantic=semantic))
    assert looks.scored_by_cues(["sương"], {pid, "outside"}) == [(pid, .42)]
    assert seen == [({pid}, "vibe")]


def test_dish_review_order_is_kept_alongside_the_menu():
    record = rec(1, "Quán A", {})
    record["details"] = {"order": [{"text": "Lẩu gà lá é", "n": 3}]}
    catalog = Catalog.from_records([record], 1)
    assert catalog.dishes("lẩu gà lá é")[0]["evidence"][0]["source"] == "review_order"


def test_gaps_reject_unquoted_data_without_mutating_state(catalog, tmp_path):
    tools = TurnTools(TripState(), "cần halal", 1, catalog, date(2026, 10, 15), gaps=tmp_path / "gaps.jsonl")
    result = tools.run("record_fact", {"field": "unmapped", "op": "add", "how": "said", "quote": "cần halal",
                                        "value": "bồn tắm", "gap": "no_data"})
    assert "error" in result and tools.state == TripState()
    assert not list(tmp_path.iterdir())


def test_a_gap_is_counted_once_per_turn(catalog, tmp_path):
    tools = TurnTools(TripState(), "cần halal", 1, catalog, date(2026, 10, 15), gaps=tmp_path / "gaps.jsonl")
    args = {"field": "unmapped", "op": "add", "how": "said", "quote": "cần halal", "value": "halal", "gap": "no_data"}
    tools.run("record_fact", args)
    tools.run("record_fact", args)
    assert json.loads((tmp_path / "gaps.jsonl").read_text())["count"] == 1


def test_drill_never_offers_a_place_failing_a_hard_limit(big, cfg):
    state = TripState.model_validate({"hard": [{"feature": "long_walk", "op": "ne", "value": "present",
                                               "evidence": [{"turn": 1, "quote": "không đi bộ xa"}]}]})
    looks = FakeLooks({"sương": [(p, .3) for p in ids(1, 41)]})
    assert drill.choose([variant("Sương", "sương"), variant("Trời trong", "sương")], "săn mây", state, big, looks, cfg) == []


def test_a_specific_taste_and_a_broad_taste_in_one_clause():
    assert drill.topics("cà phê vintage rồi đi săn mây") == ["săn mây"]


def test_lodging_adjectives_do_not_create_a_photo_drill():
    assert drill.topics("muốn homestay chill, rồi đi cà phê") == ["cà phê"]


def test_time_variant_requires_a_contextual_soft_write(big, cfg):
    looks = FakeLooks({"sương": [(p, .3) for p in ids(1, 41)]})
    variants = [{**variant(label, "sương", axis="time"), "period": period, "writes": []}
                for label, period in (("Sáng", "morning"), ("Chiều", "afternoon"))]
    assert drill.choose(variants, "săn mây", TripState(), big, looks, cfg) == []


def test_duplicate_topics_in_a_batch_search_only_once(big, cfg):
    from trip.domain import ask
    looks = FakeLooks({cue: [(p, .3) for p in ids(1, 41)]
                       for cue in ("sương", "trong", "hoàng hôn", "bình minh")})
    state = drill.note(TripState(), "săn mây", 1)
    tabs = ask.check([visual_question(), visual_question()], state, big, cfg, looks)
    assert len(tabs) == 1 and len(looks.calls) == 4


def test_drill_answer_keeps_the_original_words_for_confirmation(big, cfg, tmp_path):
    q = visual_question()
    for option in q["options"]:
        option["writes"] = [{"field": "soft", "op": "add", "value": "cloud_hunting=present:love"}]
    looks = FakeLooks({cue: [(p, .3) for p in ids(1, 41)]
                       for cue in ("sương", "trong", "hoàng hôn", "bình minh")})
    chat = ScriptedChat(reply(call("ask_user", questions=[q])))
    engine = Engine(big, cfg, SessionStore(tmp_path), chat, looks=looks)
    sid = engine.create("first", "nothing")["id"]
    engine.turn(sid, TurnInput(kind="text", text="muốn săn mây"), lambda *_: None)
    tab = next(t for t in engine.load(sid)["card"]["tabs"] if t["kind"] == "drill")
    engine.turn(sid, TurnInput(kind="deck", answers={tab["qid"]: [tab["options"][0]["id"]]}), lambda *_: None)
    early = next(t for t in deck.confirm_tabs(engine.store.get(sid).state, big, cfg) if t.qid == "confirm.early")
    assert "săn mây" in early.why


def test_question_schema_keeps_visual_and_text_option_limits():
    from pydantic import ValidationError
    from trip.agent.tool_schemas import UserQuestion
    q = visual_question()
    assert UserQuestion.model_validate(q).visual
    # too few variants for a photo drill: asked as a plain question instead of refused (review4 S4)
    assert not UserQuestion.model_validate({**q, "options": q["options"][:2]}).visual
    # a plain question shows the three best options and Other: extra options are cut, not refused
    assert len(UserQuestion.model_validate({**q, "visual": False, "options": q["options"] * 2}).options) == 3
    with pytest.raises(ValidationError):
        UserQuestion.model_validate({**q, "visual": False, "options": q["options"][:1]})


def test_a_physical_departure_is_not_offered_as_an_impossible_default(catalog, cfg):
    st = TripState.model_validate({"start_date": {"value": "2026-11-20"}, "days": {"value": 2},
                                   "frame": {"leave": {"value": {"at": "2026-11-21T06:00", "how": "plane"}}}})
    trip = next(t for t in deck.build(st, catalog, cfg, ask="trip").tabs if t.qid == "trip")
    ends = [o for o in trip.options if o.id.startswith("end")]
    assert not any("05:" in o.label or "04:" in o.label for o in ends)


def test_church_photos_do_not_count_toward_a_temple_variant(cfg):
    records = [rec(i, f"Nhà thờ {i}", {}) for i in range(1, 13)] + [rec(13, "Chùa A", {})]
    for record in records:
        record["identity"]["category"] = "Chùa" if record["place_fid"] == "0xd:0x1" else "Nhà thờ"
    catalog = Catalog.from_records(records, 1)
    looks = FakeLooks({cue: [(p, .3) for p in ids(1, 14)] for cue in ("chùa", "nhà thờ")})
    options = drill.choose([variant("Chùa ve chai", "chùa"), variant("Nhà thờ cổ", "nhà thờ")],
                           "tâm linh", TripState(), catalog, looks, cfg)
    assert options == []


def test_visual_option_cannot_reverse_a_said_preference(big, cfg):
    state = TripState.model_validate({"soft": {"scenic_view=present": {
        "value": "avoid", "source": "user", "confidence": "high", "status": "confirmed",
        "evidence": [{"turn": 1, "quote": "không thích view"}]}}})
    looks = FakeLooks({"sương": [(p, .3) for p in ids(1, 41)]})
    assert drill.choose([variant("Sương", "sương"), variant("Trời trong", "sương")],
                        "săn mây", state, big, looks, cfg) == []


def test_a_cached_drill_is_closed_when_new_hard_limits_remove_its_places(big, cfg, tmp_path):
    looks = FakeLooks({cue: [(p, .3) for p in ids(1, 41)]
                       for cue in ("sương", "trong", "hoàng hôn", "bình minh")})
    engine = Engine(big, cfg, SessionStore(tmp_path), ScriptedChat(), looks=looks)
    sid = engine.create("first", "nothing")["id"]
    session = engine.store.get(sid)
    session.state = drill.note(TripState(), "săn mây", 1)
    tools = TurnTools(session.state, "săn mây", 1, big, date(2026, 10, 15))
    tools.asked = {"kind": "agent", "questions": [visual_question()]}
    engine._asked(session, tools, 1)
    photo_calls = len(looks.calls)
    raw = session.state.model_dump()
    raw["hard"] = [{"feature": "long_walk", "op": "ne", "value": "present",
                    "evidence": [{"turn": 2, "quote": "không đi bộ xa"}]}]
    session.state = TripState.model_validate(raw)
    assert not any(t.kind == "drill" for t in deck.build(session.state, big, cfg).tabs)
    engine._next(session, "")
    assert session.state.drills[0].status == "none" and len(looks.calls) == photo_calls


def test_a_broad_taste_gets_its_photo_card_from_config_and_it_comes_before_the_agents_question(big, cfg, tmp_path):
    from dataclasses import replace
    cfg = replace(cfg, drills={"săn mây": {"header": "Kiểu săn mây", "question": "Săn mây kiểu nào?", "variants": [
        variant(label, cue) for label, cue in (("Sương sớm", "sương"), ("Trời trong", "trong"), ("Hoàng hôn", "hoàng hôn"))]}})
    looks = FakeLooks({cue: [(p, .2) for p in ids(1, 41)] for cue in ("sương", "trong", "hoàng hôn")})
    chat = ScriptedChat(say("Săn mây thì bạn thích sáng sớm hay chiều tà?"))  # it asks in words anyway
    engine = Engine(big, cfg, SessionStore(tmp_path), chat, today=lambda: date(2026, 10, 15), looks=looks)
    sid = engine.create("first", "nothing")["id"]
    events = []
    engine.turn(sid, TurnInput(kind="text", text="muốn săn mây"), lambda ev, d: events.append((ev, d)))
    card = events[-1][1]
    tab = card["tabs"][0]
    # built by code from the config variants and real photos: one model call, the agent wrote no variant
    assert card["kind"] == "deck" and tab["qid"] == "drill.săn mây" and tab["question"] == "Săn mây kiểu nào?"
    assert len(tab["options"]) == 5 and all(o.get("photo") for o in tab["options"][:3]) and chat.calls == 1
    s = engine.store.get(sid)
    assert ("say", {"replace": ""}) in events  # its question in words gives way to the photos
    assert "drill_first" in [t["text"] for t in s.transcript if t["role"] == "system"][-1]


def test_a_taste_without_enough_photos_closes_its_drill(big, cfg, tmp_path):
    from dataclasses import replace
    cfg = replace(cfg, drills={"săn mây": {"header": "Kiểu săn mây", "question": "Săn mây kiểu nào?",
                                           "variants": [variant("Sương sớm", "sương"), variant("Trời trong", "trong")]}})
    st = drill.note(TripState(), "muốn săn mây", 1)
    built = drill.build(st, big, FakeLooks({"sương": [(p, .2) for p in ids(1, 41)]}), cfg)
    assert built.drills[0].status == "none" and built.drills[0].tab is None
    assert drill.build(st, big, None, cfg) == st  # no looks: nothing changes


def test_photos_answered_in_words_are_not_shown_again(big, cfg, tmp_path):
    from dataclasses import replace
    cfg = replace(cfg, drills={"săn mây": {"header": "Kiểu săn mây", "question": "Săn mây kiểu nào?", "variants": [
        variant(label, cue) for label, cue in (("Sương sớm", "sương"), ("Trời trong", "trong"))]}})
    looks = FakeLooks({cue: [(p, .2) for p in ids(1, 41)] for cue in ("sương", "trong")})
    chat = ScriptedChat(say("Săn mây nhé."), say("Rõ rồi."))
    engine = Engine(big, cfg, SessionStore(tmp_path), chat, today=lambda: date(2026, 10, 15), looks=looks)
    sid = engine.create("first", "nothing")["id"]
    engine.turn(sid, TurnInput(kind="text", text="muốn săn mây"), lambda *_: None)
    assert engine.load(sid)["card"]["tabs"][0]["kind"] == "drill"
    engine.turn(sid, TurnInput(kind="text", text="tùy, chỗ nào cũng được"), lambda *_: None)
    assert [(t["qid"], t["kind"]) for t in engine.load(sid)["card"]["tabs"]] == [("confirm.early", "confirm")]
    assert engine.store.get(sid).state.drills[0].status == "skipped"


def test_a_wanted_dish_is_looked_up_before_the_model_and_recorded_with_the_other_facts(big):
    from trip.agent import lookups
    assert lookups("mình muốn ăn bánh căn", big)["dishes"] == [{"dish": "bánh căn", "places": 6}]
    assert lookups("đi chill thôi", big) == {"dishes": [], "kinds": []}
    t = TurnTools(TripState(), "mình muốn ăn bánh căn", 1, big, date(2026, 10, 15))
    out = t.run("record_fact", {"facts": [{"field": "dish", "op": "add", "value": "bánh căn", "quote": "bánh căn"}]})
    assert "error" not in out and out["results"][0]["count"] == 6
    assert t.state.wishes.dishes[0].dish == "bánh căn" and len(t.state.wishes.dishes[0].place_ids) == 6


def test_photo_card_scores_are_cached_and_survive_a_save(big):
    looks = Looks(big, warm=False, retrieval=SimpleNamespace(semantic=lambda q, within, mode: [
        SimpleNamespace(place_id=p, score=.3) for p in sorted(within)]))
    calls = []
    real = looks._score
    looks._score = lambda cues, scope: calls.append(cues) or real(cues, scope)
    within = set(ids(1, 5))
    first = looks.scored_by_cues(["sương"], within)
    assert looks.scored_by_cues(["sương"], within) == first and len(calls) == 1  # the same variant is scored once
    saved = json.loads(json.dumps(looks.kept_scores()))
    fresh = Looks(big, warm=False, retrieval=SimpleNamespace(semantic=lambda *a, **k: []))
    assert fresh.keep_scores(saved) == 1 and fresh.scored_by_cues(["sương"], within) == first
