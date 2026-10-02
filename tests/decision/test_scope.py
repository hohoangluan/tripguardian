import pytest
from fixtures import hard, love, si

from decision.scope import input_scope, replan_scope


@pytest.mark.parametrize("action,step", [
    ({"type": "select", "place_id": "A"}, "diversify"),
    ({"type": "drop", "place_id": "A"}, "diversify"),
    ({"type": "drop", "place_id": "A", "reason": "far"}, "fit"),
    ({"type": "drop", "place_id": "A", "reason": "pricey"}, "rank"),
    ({"type": "relax", "place_id": "A", "feature": "steep_or_stairs"}, "screen"),
    ({"type": "feedback", "reason": "crowded"}, "fit"),
    ({"type": "prefer", "feature": "noise", "value": "quiet", "weight": 1}, "rank"),
    ({"type": "answer", "qid": "pattern:crowd=high", "chip": "yes"}, "rank"),
    ({"type": "answer", "qid": "gap:1", "chip": "free"}, "diversify"),
    ({"type": "undo"}, "screen"),
])
def test_action_scope(action, step):
    got = replan_scope(action)
    assert got["from"] == step and step not in got["keep"]


def test_input_scope_follows_place_decision_table():
    base = si()
    assert input_scope(base, si(hard_filters=[hard("long_walk", "present")]))["from"] == "screen"
    assert input_scope(base, si(anchors=[{"place_id": "A", "priority": "must"}]))["from"] == "resolve"
    assert input_scope(base, si(soft_weights=[love("noise", "quiet")]))["from"] == "rank"
    assert input_scope(base, si(pace={"level": "slow"}))["from"] == "diversify"
    assert input_scope(base, si())["from"] is None
