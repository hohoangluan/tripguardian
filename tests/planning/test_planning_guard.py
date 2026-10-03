from planning.guard import PlanUpdate, TurnPlan, guard, names_in

ALIASES = {
    "P1": {"kind": "place", "id": "a", "name": "Đồi Chè Cầu Đất", "day": 0},
    "P2": {"kind": "place", "id": "b", "name": "Quán Mộc Lan Viên", "day": 0},
    "P3": {"kind": "place", "id": "c", "name": "Thác Datanla", "day": 1},
    "L1": {"kind": "lodging", "id": "h1", "name": "Homestay Mây"},
    "V1": {"kind": "variant", "id": "v1", "label": "Ít di chuyển"},
}
DAY_ORDER = {0: ["a", "b"], 1: ["c"]}


def plan(*updates, say="Mình đã cập nhật."):
    return TurnPlan(say=say, updates=tuple(PlanUpdate(op=o, ref=r, value=v, quote=q) for o, r, v, q in updates))


def test_names_in_full_or_last_two_words():
    assert names_in("bỏ cầu đất đi", "Đồi Chè Cầu Đất")
    assert not names_in("bỏ đồi chè", "Đồi Chè Cầu Đất")


def test_drop_does_not_require_the_name_in_the_quote():
    text = "ngày 1 nhiều quá"
    g = guard(plan(("drop", "P2", "", "ngày 1 nhiều quá")), text, ALIASES, DAY_ORDER, "")
    assert g.actions == [{"type": "drop_place", "place": "b", "reason": None}]


def test_move_day_resolves_the_one_based_day_the_user_said():
    text = "chuyển Datanla sang ngày 1"
    g = guard(plan(("move_day", "P3", "1", "chuyển Datanla sang ngày 1")), text, ALIASES, DAY_ORDER, "")
    assert g.actions == [{"type": "move_place", "place": "c", "day": 0}]


def test_reorder_edge_moves_the_place_to_the_front_keeping_the_rest_in_order():
    text = "muốn Lan Viên đi trước"
    g = guard(plan(("reorder_edge", "P2", "first", "muốn Lan Viên đi trước")), text, ALIASES, DAY_ORDER, "")
    assert g.actions == [{"type": "reorder", "day": 0, "order": ["b", "a"]}]


def test_reorder_edge_on_a_place_already_at_that_edge_is_a_no_op_order():
    text = "Cầu Đất đi trước nhé"
    g = guard(plan(("reorder_edge", "P1", "first", "Cầu Đất đi trước nhé")), text, ALIASES, DAY_ORDER, "")
    assert g.actions == [{"type": "reorder", "day": 0, "order": ["a", "b"]}]


def test_pick_lodging_and_variant_need_the_name_in_the_quote():
    text = "chọn Homestay Mây luôn"
    g = guard(plan(("pick_lodging", "L1", "", "chọn Homestay Mây luôn")), text, ALIASES, DAY_ORDER, "")
    assert g.actions == [{"type": "pick_lodging", "id": "h1"}]
    bad = guard(plan(("pick_lodging", "L1", "", "chọn luôn")), "chọn luôn", ALIASES, DAY_ORDER, "")
    assert bad.actions == [] and len(bad.log) == 1


def test_variant_is_named_by_its_label():
    text = "chọn Ít di chuyển nhé"
    g = guard(plan(("variant", "V1", "", "chọn Ít di chuyển nhé")), text, ALIASES, DAY_ORDER, "")
    assert g.actions == [{"type": "pick_variant", "id": "v1"}]
    bad = guard(plan(("variant", "V1", "", "chọn cái đó")), "chọn cái đó", ALIASES, DAY_ORDER, "")
    assert bad.actions == [] and len(bad.log) == 1


def test_lodging_near_free_text_needs_no_alias():
    g = guard(plan(("lodging_near", "", "chợ đêm Đà Lạt", "gần chợ đêm hơn")), "gần chợ đêm hơn", ALIASES,
              DAY_ORDER, "")
    assert g.actions == [{"type": "set_lodging", "text": "chợ đêm Đà Lạt"}]


def test_relax_needs_a_known_feature_and_the_place_named():
    g = guard(plan(("relax", "P1", "steep_or_stairs", "Cầu Đất có bậc thang cũng được")),
              "Cầu Đất có bậc thang cũng được", ALIASES, DAY_ORDER, "")
    assert g.actions == [{"type": "relax", "place_id": "a", "feature": "steep_or_stairs"}]
    bad = guard(plan(("relax", "P1", "not_a_feature", "bậc thang cũng được")), "bậc thang cũng được", ALIASES,
               DAY_ORDER, "")
    assert bad.actions == []


def test_a_quote_not_actually_in_the_message_is_dropped():
    g = guard(plan(("drop", "P1", "", "không có câu này")), "chào bạn", ALIASES, DAY_ORDER, "")
    assert g.actions == [] and len(g.log) == 1


def test_unknown_alias_is_dropped_and_unmapped_is_only_noted():
    text = "P9 bỏ đi, nhạc nhẹ chút"
    g = guard(plan(("drop", "P9", "", "P9 bỏ đi"), ("unmapped", "", "nhạc nhẹ chút", "nhạc nhẹ chút")), text,
              ALIASES, DAY_ORDER, "")
    assert g.actions == [] and len(g.log) == 2  # the drop of P9 is logged as bad, the unmapped one as a note


def test_say_with_an_unseen_number_is_replaced():
    # Planning's aliases never carry a place outside the current plan, so a say naming a place is never by itself a
    # hallucination; only a number nobody said or showed is (a minute count, a price, an invented day number).
    assert guard(plan(say="Còn 45 phút trống."), "bỏ đi", ALIASES, DAY_ORDER, "").say == ""
    assert guard(plan(say="Còn 45 phút trống."), "bỏ đi", ALIASES, DAY_ORDER, "dư 45 phút").say == "Còn 45 phút trống."
    assert guard(plan(say="Thử Thác Datanla nhé"), "bỏ đi", ALIASES, DAY_ORDER, "").say == "Thử Thác Datanla nhé"
