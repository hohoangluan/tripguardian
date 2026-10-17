import threading

import pytest
from fixtures import hard, love, si, srec

from decision.agent import AgentError
from decision.curation import ActionError
from decision.engine import PROMPT_PER_GROUP, Engine, NoSession, NotConfirmable, VersionMismatch, diff
from decision.guard import PlanUpdate, TurnPlan
from decision.pipeline import Data
from decision.session import Store
from decision.settings import default

CFG = default()


def data():
    recs = [srec(f"C{i}", name=f"Quán Cà Phê Số {i}", features={"scenic_view": "present", "steep_or_stairs": "absent"},
                 lng=108.44 + i / 1000) for i in range(6)]
    return Data(recs + [srec("M", name="Quán Ăn Bình Dân", usable=("meal",))])


def trip(**over):
    return si(activities={f"C{i}": "coffee" for i in range(6)}, hard_filters=[hard("steep_or_stairs", "present")], soft_weights=[love("scenic_view")], **over).model_dump(mode="json")


class FakeAgent:
    def __init__(self, plan=None, error=None):
        self.plan, self.error, self.calls = plan, error, []

    async def __call__(self, fields, on_say):
        self.calls.append(fields)
        if self.error:
            raise self.error
        on_say(self.plan.say)
        return self.plan


def engine(agent=None):
    return Engine(data(), CFG, Store(None), agent)


def test_create_selects_anchors_and_counts_first_shortlist():
    e = engine()
    out = e.create(trip(anchors=[{"place_id": "C0", "priority": "must"}]))
    s = e.store.get(out["id"])
    assert s.state.selected == ["C0"] and s.state.locked == ["C0"] and s.first_shortlist == sum(1 for g in out["view"]["groups"] for c in g["cards"] if c["top"] or c["anchor"])
    with pytest.raises(VersionMismatch):
        e.create({**trip(), "ontology_version": 1})


def test_act_versions_diff_and_undo():
    e = engine()
    sid = e.create(trip())["id"]
    r = e.act(sid, {"type": "select", "place_id": "C1"})
    assert r["view"]["selected"] == ["C1"] and r["diff"]["delta"]["places"] == 1 and r["diff"]["scope"]["from"] == "diversify"
    assert r["diff"]["text"].startswith("+1 nơi")
    r = e.act(sid, {"type": "undo"})
    assert r["view"]["selected"] == [] and len(e.store.get(sid).log) == 2
    with pytest.raises(ActionError):
        e.act(sid, {"type": "undo"})
    with pytest.raises(ActionError):
        e.act(sid, {"type": "select", "place_id": "NOPE"})
    assert e.store.get(sid).history == []
    with pytest.raises(NoSession):
        e.act("0123456789ab", {"type": "undo"})


def test_parallel_acts_keep_every_step():
    e = engine()
    sid = e.create(trip())["id"]
    ts = [threading.Thread(target=e.act, args=(sid, {"type": "select", "place_id": f"C{i}"})) for i in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    s = e.store.get(sid)
    assert sorted(s.state.selected) == ["C0", "C1", "C2", "C3"] and len(s.history) == 4


def test_turn_with_agent_applies_guarded_actions():
    plan = TurnPlan(say="Mình đã bỏ quán đó.", updates=(PlanUpdate(op="drop", place="P1", value="far", quote="xa quá"),))
    agent = FakeAgent(plan)
    e = engine(agent)
    sid = e.create(trip())["id"]
    first = e.load(sid)["view"]["shortlist"][0]
    events = []
    e.turn(sid, "quán đầu xa quá", lambda ev, d: events.append((ev, d)))
    assert [ev for ev, _ in events] == ["say", "view", "done"]
    view = events[1][1]["view"]
    assert view["dropped"] == [{"id": first, "name": view["dropped"][0]["name"], "reason": "far"}]
    assert "P1 |" in agent.calls[0]["places"] and e.store.get(sid).state.profile.travel_mult == CFG.far_step


def test_turn_falls_back_to_policy():
    e = engine(FakeAgent(error=AgentError("down")))
    sid = e.create(trip())["id"]
    events = []
    e.turn(sid, "Quán Cà Phê Số 2 xa quá", lambda ev, d: events.append((ev, d)))
    assert events[0] == ("say", {"replace": "Mình đã ghi nhận, danh sách đã cập nhật."})
    assert e.store.get(sid).state.dropped[0].place_id == "C2"


def test_compare_why_not_confirm():
    e = engine()
    sid = e.create(trip(context={"days": 1}))["id"]
    assert e.compare(sid, "C0", "C1")["a"]["id"] == "C0"
    with pytest.raises(ActionError):
        e.compare(sid, "C0", "NOPE")
    assert e.why_not(sid, "NOPE")["known"] is False
    e.act(sid, {"type": "select", "place_id": "C0"})
    out = e.confirm(sid)
    assert out["confirmed"][0]["id"] == "C0" and e.store.get(sid).output == out
    for i in range(1, 6):
        e.act(sid, {"type": "select", "place_id": f"C{i}"})
    assert e.draft(sid) == e.confirm(sid)
    assert len(e.confirm(sid)["confirmed"]) == 6


def test_overload_draft_preserves_selection_estimate_and_actual_utility():
    from decision import DecisionOutput, Tools

    e = engine()
    sid = e.create(trip(context={"days": 1, "day_end": "10:00"}))["id"]
    for i in range(6):
        e.act(sid, {"type": "select", "place_id": f"C{i}"})
    before = e.load(sid)["view"]
    assert before["feasibility"]["status"] == "infeasible"
    draft = Tools(e).read(sid, "draft", {})["output"]
    assert draft is not None
    assert draft["feasibility"] == before["feasibility"]
    assert [p["id"] for p in draft["confirmed"]] == before["selected"]
    assert e.store.get(sid).output is None
    result = e._result(e.store.get(sid))
    for place in draft["confirmed"]:
        assert place["utility"] == result.cands[place["id"]].score
        assert place["utility_source"] == "decision_score"
        assert "novelty" not in place
    assert DecisionOutput.model_validate(e.confirm(sid))


@pytest.mark.parametrize("check", ["hours", "relax", "physical", "hard", "future_check"])
def test_blocking_conflict_cannot_pass_alongside_selection_overload(check):
    e = engine()
    sid = e.create(trip())["id"]
    e.act(sid, {"type": "select", "place_id": "C0"})
    res = e._result(e.store.get(sid))
    res.view["feasibility"].update(status="partial", conflicts=[
        {"check": "time", "physical": True}, {"check": check, "physical": True}])
    assert e.draft(sid) is None
    with pytest.raises(NotConfirmable):
        e.confirm(sid)


@pytest.mark.parametrize("check", ["time", "per_day", "far_areas", "time_windows", "budget"])
def test_selection_overload_checks_share_draft_and_confirm_rule(check):
    e = engine()
    sid = e.create(trip())["id"]
    e.act(sid, {"type": "select", "place_id": "C0"})
    res = e._result(e.store.get(sid))
    res.view["feasibility"].update(status="partial", conflicts=[{"check": check, "physical": True}])
    assert e.draft(sid) is not None
    assert e.draft(sid) == e.confirm(sid)


def test_closed_and_hard_failed_selected_places_still_block_handoff():
    for rec, filters in [(srec("X", hours={"sun": [["08:00", "18:00"]]}), []),
                         (srec("X", features={"steep_or_stairs": "present"}),
                          [hard("steep_or_stairs", "present")])]:
        e = Engine(Data([rec]), CFG, Store(None))
        sid = e.create(si(context={"days": 1}, hard_filters=filters,
                          anchors=[{"place_id": "X", "priority": "must"}]).model_dump(mode="json"))["id"]
        assert e.draft(sid) is None
        with pytest.raises(NotConfirmable):
            e.confirm(sid)


def test_rethink_back_sends_the_user_to_understanding():
    e = engine()
    sid = e.create(trip())["id"]
    s = e.store.get(sid)
    s.first_shortlist = 2
    for i in range(6):
        e.act(sid, {"type": "drop", "place_id": f"C{i}"})
    view = e.load(sid)["view"]
    assert view["pending"]["qid"] == "rethink"
    assert e.act(sid, {"type": "answer", "qid": "rethink", "chip": "back"})["goto"] == "understand"


def test_dropped_say_is_replaced_by_a_sentence_never_empty():
    plan = TurnPlan(say="Còn 45 phút trống.", updates=(PlanUpdate(op="drop", place="P1", value="far", quote="xa quá"),))
    e = engine(FakeAgent(plan))
    sid = e.create(trip())["id"]
    events = []
    e.turn(sid, "quán đầu xa quá", lambda ev, d: events.append((ev, d)))
    replace = [d for ev, d in events if ev == "say" and "replace" in d][-1]["replace"]
    assert replace == "Mình đã ghi nhận, danh sách đã cập nhật."
    nothing = engine(FakeAgent(TurnPlan(say="Còn 45 phút trống.", updates=())))
    sid = nothing.create(trip())["id"]
    events = []
    nothing.turn(sid, "ừm", lambda ev, d: events.append((ev, d)))
    assert [d["replace"] for ev, d in events if ev == "say" and "replace" in d][-1].startswith("Mình chưa hiểu")


def test_page_extends_the_window_and_is_kept_in_the_session():
    recs = [srec(f"C{i:02d}", features={"scenic_view": "present", "steep_or_stairs": "absent"}, lng=108.44 + i / 1000)
            for i in range(60)]
    e = Engine(Data(recs), CFG, Store(None), None)
    out = e.create(trip())
    g = next(x for x in out["view"]["groups"] if x["id"] == "cafe")  # the tab is the place kind (config tabs)
    assert len(g["cards"]) == CFG.page_size
    more = e.page(out["id"], "cafe")["view"]
    g2 = next(x for x in more["groups"] if x["id"] == "cafe")
    # a page replaces the previous one (docs/PLACE_DECISION.md §9.4): the next 24 places, not the first 24 plus 24
    ranked = e._result(e.store.get(out["id"])).ranked["cafe"]
    assert [c["id"] for c in g["cards"]] == ranked[:CFG.page_size]
    assert [c["id"] for c in g2["cards"]] == ranked[CFG.page_size:2 * CFG.page_size]
    assert (g2["page"], g2["offset"], g2["total"], g2["pages"]) == (1, CFG.page_size, 60, 3)
    assert e.load(out["id"])["view"]["groups"] == more["groups"]


def test_first_shortlist_counts_top_and_anchors_not_the_whole_window():
    recs = [srec(f"C{i:02d}", features={"scenic_view": "present", "steep_or_stairs": "absent"}, lng=108.44 + i / 1000)
            for i in range(60)]
    e = Engine(Data(recs), CFG, Store(None), None)
    out = e.create(trip())
    s = e.store.get(out["id"])
    assert s.first_shortlist == sum(1 for g in out["view"]["groups"] for c in g["cards"] if c["top"] or c["anchor"])
    assert s.first_shortlist < len(out["view"]["shortlist"])


def test_turn_with_a_trip_wish_emits_trip_before_view_and_still_applies_place_ops():
    say_plan = TurnPlan(say="Mình hiểu rồi.", updates=(
        PlanUpdate(op="trip", place="", value="", quote="muốn yên tĩnh hơn"),
        PlanUpdate(op="drop", place="P1", value="", quote="bỏ quán số 0")))
    e = engine(FakeAgent(say_plan))
    out = e.create(trip())
    events = []
    e.turn(out["id"], "bỏ quán số 0, muốn yên tĩnh hơn", lambda ev, d: events.append((ev, d)))
    names = [ev for ev, _ in events]
    assert ("trip", {"texts": ["muốn yên tĩnh hơn"]}) in events and names.index("trip") < names.index("view")
    assert [d.place_id for d in e.store.get(out["id"]).state.dropped] != []


def _v(ids, change):
    return {"shortlist": ids, "feasibility": {"status": "feasible", "totals": {"places": 0, "visit": 0, "travel": 0}},
            "change": change}


def test_rebuilt_diff_says_how_many_shown_places_stayed_and_changed():
    one = {"chill": {"kept": 23, "added": 1, "removed": 1, "replaced_all": False},
           "meal": {"kept": 22, "added": 2, "removed": 2, "replaced_all": False}}
    assert diff(_v(["A"], {}), _v(["B"], one), None, rebuilt=True)["text"] == "Giữ 45 nơi, thay 3 nơi hợp hơn"
    same = {"chill": {"kept": 24, "added": 0, "removed": 0, "replaced_all": False}}
    assert diff(_v(["A"], {}), _v(["A"], same), None, rebuilt=True)["text"] == "Các nơi đang gợi ý vẫn hợp, không cần đổi"
    swap = {"chill": {"kept": 0, "added": 24, "removed": 24, "replaced_all": True}}
    assert diff(_v(["A"], {}), _v(["B"], swap), None, rebuilt=True)["text"] == "Danh sách đổi theo ý bạn: 24 nơi mới"


def test_a_change_that_moves_nothing_has_no_text():
    assert diff(_v(["A"], {}), _v(["A"], {}), None)["text"] == ""


def test_rebase_reports_the_list_change_and_keeps_undo():
    from decision.tools import Tools
    t = Tools(engine())
    sid = t.create({"search_input": trip()})["id"]
    t.apply(sid, "act", {"type": "select", "place_id": "C1"}, lambda *a: None)
    wish = trip()
    wish["soft_weights"].append(love("cozy_decor"))
    out = t.rebase(sid, {"search_input": wish})
    assert out["diff"]["text"].startswith(("Giữ", "Các nơi", "Danh sách"))
    assert len(t.engine.store.get(sid).history) == 1
    assert t.apply(sid, "act", {"type": "undo"}, lambda *a: None)["view"]["selected"] == []


def test_why_not_for_a_listed_place_below_the_loaded_window_says_where_it_is():
    recs = [srec(f"C{i:02d}", features={"scenic_view": "present", "steep_or_stairs": "absent"}, lng=108.44 + i / 1000)
            for i in range(60)]
    e = Engine(Data(recs), CFG, Store(None), None)
    sid = e.create(trip())["id"]
    ranked = e._result(e.store.get(sid)).ranked["cafe"]
    r = e.why_not(sid, ranked[40])
    assert r["reasons"] == ["Nơi này có trong danh sách Cà phê, xếp thứ 41/60; ở trang 2"]


def test_agent_sees_the_first_places_of_a_tab_and_those_the_user_names():
    recs = [srec(f"C{i:02d}", features={"scenic_view": "present", "steep_or_stairs": "absent"}, lng=108.44 + i / 1000)
            for i in range(60)]
    agent = FakeAgent(TurnPlan(say="Mình hiểu rồi."))
    e = Engine(Data(recs), CFG, Store(None), agent)
    sid = e.create(trip())["id"]
    e.turn(sid, "bạn nghĩ sao", lambda *a: None)
    lines = [x for x in agent.calls[0]["places"].splitlines() if x.startswith("P")]
    assert len(lines) == PROMPT_PER_GROUP and not any(x.endswith("| ") for x in lines)  # first page: reasons
    e.page(sid, "cafe")
    e.turn(sid, "bạn nghĩ sao", lambda *a: None)
    lines = [x for x in agent.calls[1]["places"].splitlines() if x.startswith("P")]
    assert len(lines) == PROMPT_PER_GROUP and all(x.endswith("| ") for x in lines)  # a later page: places only
    shown = [c["name"] for g in e.load(sid)["view"]["groups"] if g["id"] == "cafe" for c in g["cards"]]
    named = shown[-1]  # on screen, far past the first few of the tab
    assert not any(named in x for x in agent.calls[1]["places"].splitlines())
    e.turn(sid, f"nghĩ sao về {named}", lambda *a: None)
    assert any(named in x for x in agent.calls[2]["places"].splitlines())  # a shown place the user names is always sent


def test_a_lodging_picked_at_lua_chon_goes_into_the_output_and_ranks_nothing_again():
    hotel = srec("H", name="Khách sạn Đồi Thông", group="stay", category="Khách sạn", usable=(), lat=11.95, lng=108.45,
                 features={"steep_or_stairs": "absent"})
    hotel["operation"]["price_per_night"] = {"value": 467000, "status": "VERIFIED", "as_of": "2026-10-08",
                                             "source": "gmaps_list", "kind": "estimate"}
    e = Engine(Data(data().records + [hotel]), CFG, Store(None))
    sid = e.create(trip())["id"]
    e.act(sid, {"type": "select", "place_id": "C0"})
    assert e.load(sid)["view"]["lodging"] == {"booked": None, "chosen": None, "needed": True}
    with pytest.raises(ActionError):
        e.act(sid, {"type": "set_lodging", "lodging": {"kind": "corpus", "id": "C1"}})  # a café is not a lodging
    out = e.act(sid, {"type": "set_lodging", "lodging": {"kind": "corpus", "id": "H", "text": "spoofed", "lat": 0, "lng": 0}})
    assert out["diff"]["scope"]["from"] is None  # no step re-runs: where the user sleeps is Planning's
    assert out["view"]["lodging"]["chosen"] == {"kind": "corpus", "id": "H", "text": "Khách sạn Đồi Thông", "lat": 11.95,
                                                "lng": 108.45, "price_vnd": 467000}  # read from the record, not the client
    assert e.confirm(sid)["lodging"]["id"] == "H"
    e.act(sid, {"type": "set_lodging", "lodging": {"kind": "address", "text": "12 Bùi Thị Xuân", "lat": 11.94, "lng": 108.44}})
    assert e.draft(sid)["lodging"]["text"] == "12 Bùi Thị Xuân"
    with pytest.raises(ActionError):
        e.act(sid, {"type": "set_lodging", "lodging": {"kind": "address", "text": "", "lat": 11.9, "lng": 108.4}})
    e.act(sid, {"type": "clear_lodging"})
    assert e.draft(sid)["lodging"] is None


def test_a_booked_lodging_needs_no_pick_and_any_state_draft_is_still_given():
    booked = {"lodging_booked": "yes", "lodging": {"text": "Ana Mandara", "lat": 11.93, "lng": 108.42}}
    e = engine()
    sid = e.create(trip(context={**si().context.model_dump(mode="json"), **booked}))["id"]
    assert e.load(sid)["view"]["lodging"] == {"booked": {"id": None, "text": "Ana Mandara", "lat": 11.93, "lng": 108.42},
                                              "chosen": None, "needed": False}
    res = e._result(e.store.get(sid))
    res.view["feasibility"].update(status="infeasible", conflicts=[{"check": "hours", "physical": True}])
    assert e.draft(sid) is None and e.draft(sid, any_state=True) is not None
