from trip.domain.guard import PlanNext, PlanUpdate, TurnPlan, guard
from trip.domain.state import Evidence, TripState, Update, apply, with_meta

TEXT = "Tháng 12 đi 3 ngày với bố mẹ, muốn yên tĩnh"


def plan(*updates, say="Mình ghi lại rồi.", **nxt):
    n = {"kind": "ask", "qid": "", "custom_text": "", "custom_chips": (), "reason": ""} | nxt
    return TurnPlan(say=say, updates=tuple(PlanUpdate(**u) for u in updates), next=PlanNext(**n))


def u(field, value, quote, op="set", how="said"):
    return {"field": field, "op": op, "value": value, "quote": quote, "how": how}


def framed():
    ev = Evidence(turn=1, quote="x")
    s = TripState()
    for f, v, op in (("days", 3, "set"), ("companions", "solo", "add"), ("mobility", "car", "set")):
        s = apply(s, Update(field=f, op=op, value=v, source="user", confidence="high", evidence=ev))
    s = apply(s, Update(field="start_date", op="remove", source="user", confidence="high", evidence=ev))
    return with_meta(s, asked=("frame",))


def run(p, state, catalog, cfg, text=TEXT):
    return guard(p, state, text, 2, catalog, cfg, heard=text)


def test_update_with_quote_not_in_message_is_dropped(catalog, cfg):
    g = run(plan(u("days", "4", "4 ngày")), framed(), catalog, cfg)
    assert g.state.days.value == 3 and "not in the message" in g.log[0]


def test_said_and_inferred_sources(catalog, cfg):
    g = run(plan(u("month", "12", "Tháng 12"), u("pace", "slow", "yên tĩnh", how="inferred")), framed(), catalog, cfg)
    assert (g.state.month.source, g.state.month.status) == ("user", "confirmed")
    assert (g.state.pace.source, g.state.pace.confidence) == ("inferred", "medium")


def test_unknown_feature_becomes_unmapped(catalog, cfg):
    g = run(plan(u("soft", "quiet_music=present:love", "yên tĩnh", op="add")), framed(), catalog, cfg)
    assert [x.phrase for x in g.state.unmapped] == ["yên tĩnh"] and not g.state.soft


def test_tier_one_question_is_forced(catalog, cfg):
    g = run(plan(u("signal", "elderly", "bố mẹ", op="add", how="inferred"), qid="pace"), framed(), catalog, cfg)
    assert g.question.qid == "c_effort" and "forced" in g.log[-1]


def test_stop_and_budget_give_ready(catalog, cfg):
    assert run(plan(kind="stop"), framed(), catalog, cfg).question.qid == "ready"
    assert run(plan(qid="pace"), with_meta(framed(), adaptive_turns=5), catalog, cfg).question.qid == "ready"


def test_custom_question_needs_two_to_six_short_chips(catalog, cfg):
    ok = run(plan(custom_text="Vì sao bạn muốn đến đó?", custom_chips=("View", "Ít người")), framed(), catalog, cfg)
    assert ok.question.custom and [c.label for c in ok.question.chips] == ["View", "Ít người"]
    bad = run(plan(custom_text="Vì sao?", custom_chips=("View",)), framed(), catalog, cfg)
    assert not bad.question.custom


def test_unknown_qid_falls_back_to_policy(catalog, cfg):
    g = run(plan(qid="nope"), framed(), catalog, cfg)
    assert g.question.qid != "nope" and "unknown qid" in g.log[-1]


def test_say_with_new_number_or_place_name_is_replaced(catalog, cfg):
    assert run(plan(say="Có 38 nơi hợp."), framed(), catalog, cfg).say == ""
    assert run(plan(say="Thử Quán Yên Tĩnh Số 1 nhé."), framed(), catalog, cfg).say == ""
    assert run(plan(say="3 ngày tháng 12, ghi rồi."), framed(), catalog, cfg).say == "3 ngày tháng 12, ghi rồi."


def test_inference_cannot_overwrite_user_choice(catalog, cfg):
    g = run(plan(u("mobility", "motorbike", "đi 3 ngày", how="inferred")), framed(), catalog, cfg)
    assert g.state.mobility.value == "car"


def test_forced_question_drops_the_agents_own_question_from_say(catalog, cfg):
    say = "Mình ghi nhận đi cùng bố mẹ. Bạn hiểu “chill” là gì?"
    g = run(plan(u("signal", "elderly", "bố mẹ", op="add", how="inferred"), say=say, qid="clarify:chill"),
            framed(), catalog, cfg)
    assert g.question.qid == "c_effort" and g.say == "Mình ghi nhận đi cùng bố mẹ."


def test_the_models_at_suffix_is_a_weight_not_a_context(catalog, cfg):
    g = run(plan(u("soft", "crowd=low@love", "yên tĩnh", op="add")), framed(), catalog, cfg)
    assert g.state.soft["crowd=low"].value == "love" and not g.state.unmapped
    g = run(plan(u("soft", "crowd=low@avoid", "yên tĩnh", op="add")), framed(), catalog, cfg)
    assert g.state.soft["crowd=low"].value == "avoid"


def test_an_agent_question_does_not_repeat_what_the_rules_already_ask(catalog, cfg):
    ev = Evidence(turn=1, quote="x")
    s = apply(framed(), Update(field="pending", op="add", value={"phrase": "chill", "keys": ["noise=quiet", "crowd=low"]},
                               source="user", confidence="medium", evidence=ev))
    g = run(plan(custom_text="Chill với bạn là gì?", custom_chips=("Yên", "Vắng")), s, catalog, cfg)
    assert g.question.qid == "clarify:chill" and not g.question.custom and "already waiting" in g.log[-1]


COMPARED = [{"id": "0x1:0x1", "name": "Cà Phê Ồn Ào Phố Núi",
             "traits": [{"feature": "noise", "value": "loud", "n": 12}, {"feature": "crowd", "value": "high", "n": 8}]}]
LIKE = "không thích quán giống Cà Phê Ồn Ào Phố Núi"


def test_inferred_soft_from_a_compared_place_is_kept_only_for_its_traits(catalog, cfg):
    p = plan(u("soft", "noise=loud:avoid", LIKE, "add", "inferred"), u("soft", "cozy_decor=present:avoid", LIKE, "add", "inferred"))
    g = guard(p, framed(), LIKE, 2, catalog, cfg, heard=LIKE, compared=COMPARED)
    assert "noise=loud" in g.state.soft and "cozy_decor=present" not in g.state.soft
    assert any("not a trait" in line for line in g.log)


def test_say_may_name_the_compared_place_but_no_other(catalog, cfg):
    text = "không thích quán giống Quán Nhạc Sống 7"
    compared = [{"id": "0x7:0x1", "name": "Quán Nhạc Sống 7", "traits": [{"feature": "noise", "value": "loud", "n": 5}]}]
    p = plan(u("soft", "noise=loud:avoid", text, "add", "inferred"), say="Mình hiểu Quán Nhạc Sống 7 khá ồn.")
    assert guard(p, framed(), text, 2, catalog, cfg, heard=text, compared=compared).say == "Mình hiểu Quán Nhạc Sống 7 khá ồn."
    other = plan(say="Thử Vườn Phẳng Lặng Xanh nhé.")
    assert guard(other, framed(), text, 2, catalog, cfg, heard=text, compared=compared).say == ""


def test_soft_read_from_a_compared_place_records_that_place_and_the_ticket_names_it(catalog, cfg):
    from trip.domain.understanding import view
    text = "không thích quán giống Quán Yên Tĩnh Số 1"
    compared = [{"id": "0x1:0x1", "name": "Quán Yên Tĩnh Số 1", "traits": [{"feature": "noise", "value": "quiet", "n": 5}]}]
    g = guard(plan(u("soft", "noise=quiet:avoid", text, "add", "inferred")), framed(), text, 2, catalog, cfg,
              heard=text, compared=compared)
    assert g.state.soft["noise=quiet"].evidence[-1].tool == "place:0x1:0x1"
    row = next(r for r in view(g.state, catalog, cfg)["soft"] if r["key"] == "noise=quiet")
    assert row["like"] == "Quán Yên Tĩnh Số 1"
    plain = guard(plan(u("soft", "noise=quiet:love", "muốn chỗ yên tĩnh", "add")), framed(), "muốn chỗ yên tĩnh", 2,
                  catalog, cfg, heard="muốn chỗ yên tĩnh")
    assert next(r for r in view(plain.state, catalog, cfg)["soft"] if r["key"] == "noise=quiet")["like"] is None
