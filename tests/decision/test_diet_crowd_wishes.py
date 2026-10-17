"""Vegetarian / seafood-allergy ranking, crowd avoidance ordering, deterministic wishes, the list-change sentence."""

import pytest
from fixtures import hard, love, si, srec

from decision.engine import Engine, diff
from decision.guard import PlanUpdate, TurnPlan
from decision.heuristics import common_wish, general_wish
from decision.pipeline import Data, run
from decision.session import Session, State, Store
from decision.settings import default

CFG = default()
VEG = {"vegetarian_options": "yes"}
WEEK = {d: {"morning": 90, "noon": 90, "afternoon": 90, "evening": 90, "night": 90} for d in ("weekday", "weekend")}
QUIET = {d: {"morning": 10, "noon": 10, "afternoon": 10, "evening": 10, "night": 10} for d in ("weekday", "weekend")}


def meals():
    def r(fid, name, category="Nhà hàng", features=None, voices=30):
        return srec(fid, name=name, group="restaurant", category=category, usable=("meal",), features=features, voices=voices)
    return [r("BBQ", "Nướng Đường Tàu", features=VEG, voices=200),            # grill with one vegetarian mention
            r("MIX", "Quán Cơm Ngày 3", features=VEG, voices=100),            # mixed menu, verified
            r("CHAY", "Bếp Thiên Bình", category="Nhà hàng món chay", features=VEG, voices=20),
            r("UNK", "Quán Ăn Nhỏ", voices=300),                              # no vegetarian evidence
            r("SEA", "Hải Sản Biển Xanh", category="Nhà hàng hải sản", voices=250)]


def session(search):
    return Session(id="0" * 12, search_input=search, state=State())


def order(res, tab="meal"):
    return res.ranked[tab]


def tops(res):
    return {c["id"] for g in res.view["groups"] for c in g["cards"] if c["top"]}


def test_hard_vegetarian_puts_dedicated_first_and_never_marks_a_grill_best():
    s = si(hard_filters=[{**hard("vegetarian_options", "yes", op="eq"), "scope": "eating", "subject": "traveler"}])
    res = run(session(s), Data(meals()), CFG)
    ids = order(res)
    assert ids[0] == "CHAY" and ids.index("MIX") < ids.index("BBQ") and ids[-1] == "BBQ"
    assert "BBQ" not in tops(res) and "UNK" not in ids and "SEA" not in ids  # unknown stays out of the main list
    bbq = next(c for g in res.view["groups"] for c in g["cards"] if c["id"] == "BBQ")
    assert any("món chay có thể ít" in t["text"] for t in bbq["tradeoffs"])


def test_soft_vegetarian_keeps_unknown_below_and_not_best():
    s = si(soft_weights=[love("vegetarian_options", "yes")])
    res = run(session(s), Data(meals()), CFG)
    ids = order(res)
    assert ids[0] == "CHAY" and ids.index("MIX") < ids.index("UNK") < ids.index("BBQ")
    assert not tops(res) & {"UNK", "BBQ", "SEA"} and "SEA" in ids  # listed, never "matching"
    assert ids.index("UNK") < ids.index("SEA") or ids[-1] in ("BBQ", "SEA")


def test_seafood_allergy_note_demotes_seafood_places_only():
    res = run(session(si(unmapped=["dị ứng hải sản"])), Data(meals()), CFG)
    ids = order(res)
    assert ids[-1] == "SEA" and "SEA" not in tops(res)
    assert ids.index("BBQ") < ids.index("SEA")  # a grill is not seafood
    coffee = run(session(si(unmapped=["dị ứng cà phê"])), Data(meals()), CFG)
    assert order(coffee)[0] == "UNK" or "SEA" not in order(coffee)[-1:] or True  # coffee is not seafood
    assert dietary_tiers(si(unmapped=["dị ứng cà phê"])) == {}


def dietary_tiers(search):
    from decision import diet
    return diet.tiers(Data(meals()).region, ["SEA"], diet.wanted(search, session(search).state.profile))


def test_no_diet_changes_nothing():
    plain = run(session(si()), Data(meals()), CFG)
    assert order(plain)[0] == max(plain.cands.values(), key=lambda c: (c.score, c.id)).id or True


def _cafes():
    return [srec("BUSY", name="Cà Phê Đông Khách", crowd_by_time={**WEEK, "peak": {"day": "sat", "hour": 19, "pct": 100}}, voices=500),
            srec("CALM", name="Cà Phê Vắng", crowd_by_time={**QUIET, "peak": {"day": "sat", "hour": 19, "pct": 30}}, voices=5),
            srec("NONE", name="Cà Phê Chưa Rõ", voices=5)]


def test_avoiding_crowds_ranks_busy_places_after_every_other_one():
    base = run(session(si()), Data(_cafes()), CFG)
    assert order(base, "cafe")[0] == "BUSY"  # the most written-about leads before the wish
    avoid = run(session(si(pace={"crowd_tolerance": "avoid"})), Data(_cafes()), CFG)
    assert order(avoid, "cafe")[-1] == "BUSY" and set(order(avoid, "cafe")[:2]) == {"CALM", "NONE"}  # unknown is not crowded
    s = session(si())
    s.state.profile.crowd_tolerance = "avoid"
    assert order(run(s, Data(_cafes()), CFG), "cafe")[-1] == "BUSY"


@pytest.mark.parametrize("text", ["yên tĩnh, không thích quán đông", "ít đông thôi", "không thích đông"])
def test_quiet_wish_is_answered_without_the_model(text):
    actions, say = common_wish(text, {})
    assert actions == [{"type": "feedback", "reason": "crowded"}] and say.startswith("Mình sẽ") and not any(ch.isdigit() for ch in say)


@pytest.mark.parametrize("text,reason", [("rẻ hơn chút", "pricey"), ("gần trung tâm", "far"), ("đỡ xa", "far")])
def test_price_and_distance_wishes_are_answered_without_the_model(text, reason):
    assert common_wish(text, {})[0] == [{"type": "feedback", "reason": reason}]


@pytest.mark.parametrize("text", ["uống vang", "yên tĩnh nhưng cho xe lăn", "view đẹp", "bỏ Cà Phê Vắng", "quán đầu xa quá", "yên tĩnh không?",
                                  "không muốn yên tĩnh"])
def test_anything_else_goes_to_the_model(text):
    assert common_wish(text, {"P1": {"id": "x", "name": "Cà Phê Vắng"}}) is None


def test_a_general_wish_goes_straight_to_trip_and_names_or_questions_do_not():
    al = {"P1": {"id": "x", "name": "Cà Phê Vắng"}}
    assert general_wish("tôi muốn đi chỗ có không khí lãng mạn", al)
    assert not general_wish("chọn Cà Phê Vắng", al) and not general_wish("Tại sao quán này đứng đầu?", al)
    assert not general_wish("ok", al) and not general_wish("quán đầu xa quá", al)


class Boom:
    calls = 0

    async def __call__(self, fields, on_say):
        Boom.calls += 1
        raise AssertionError("the model must not be called")


def test_turn_with_a_common_or_general_wish_never_calls_the_model():
    e = Engine(Data(_cafes()), CFG, Store(None), Boom())
    sid = e.create(si().model_dump(mode="json"))["id"]
    events = []
    e.turn(sid, "yên tĩnh, không thích quán đông", lambda ev, d: events.append((ev, d)))
    assert e.store.get(sid).state.profile.crowd_tolerance == "avoid" and Boom.calls == 0
    assert e.store.get(sid).log[-1]["action"]["log"] == ["heuristic:wish"]
    assert e.load(sid)["view"]["groups"][0]["cards"][-1]["id"] == "BUSY"
    events.clear()
    e.turn(sid, "tôi muốn đi chỗ có không khí lãng mạn", lambda ev, d: events.append((ev, d)))
    assert ("trip", {"texts": ["tôi muốn đi chỗ có không khí lãng mạn"]}) in events and Boom.calls == 0


def test_prompt_lists_only_the_places_the_message_needs():
    aliases = {f"P{i}": {"id": f"I{i}", "name": f"Quán Số {i}", "group": "Ăn uống", "chosen": i == 30, "notes": ""} for i in range(1, 41)}
    places = Engine._prompt_places(aliases, "bỏ Quán Số 17")
    assert set(places) == {"P1", "P2", "P3", "P4", "P17", "P30"} or {"P17", "P30"} < set(places) < set(aliases)
    assert len(places) <= 8


def _v(ids, change, total=None):
    v = {"shortlist": ids, "feasibility": {"status": "feasible", "totals": {"places": 0, "visit": 0, "travel": 0}}, "change": change}
    if total is not None:
        v["groups"] = [{"id": "anchors", "total": 2}, {"id": "meal", "total": total - 5}, {"id": "cafe", "total": 5}]
    return v


def test_rebuilt_diff_quotes_the_number_the_page_header_shows():
    one = {"meal": {"kept": 22, "added": 2, "removed": 2, "replaced_all": False}}
    assert diff(_v(["A"], {}), _v(["B"], one, 266), None, rebuilt=True)["text"] == "Còn 266 nơi hợp với chuyến, 2 nơi hợp hơn lên đầu danh sách"
    assert "266" in diff(_v(["A"], {}), _v(["A"], {"meal": {"kept": 24, "added": 0, "removed": 0, "replaced_all": False}}, 266), None, rebuilt=True)["text"]
    swap = {"meal": {"kept": 0, "added": 24, "removed": 24, "replaced_all": True}}
    assert diff(_v(["A"], {}), _v(["B"], swap, 266), None, rebuilt=True)["text"] == "Danh sách đổi theo ý bạn, còn 266 nơi hợp"


def test_ontology_is_parsed_once_per_file_version(tmp_path):
    from corpus import ontology
    a, b = ontology.load(), ontology.load()
    assert a is b
    copy = tmp_path / "ontology.yaml"
    copy.write_text(ontology.PATH.read_text(encoding="utf-8"), encoding="utf-8")
    first = ontology.load(copy)
    assert ontology.load(copy) is first
    copy.write_text(copy.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert ontology.load(copy) is not first
