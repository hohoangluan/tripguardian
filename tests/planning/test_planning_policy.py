from planning.policy import NONE, policy

ALIASES = {"P1": {"kind": "place", "id": "a", "name": "Đồi Chè Cầu Đất", "day": 0},
          "P2": {"kind": "place", "id": "b", "name": "Quán Mộc Lan Viên", "day": 0}}


def test_policy_matches_a_reason_and_a_named_place():
    actions, say = policy("Cầu Đất xa quá", ALIASES)
    assert actions == [{"type": "drop_place", "place": "a", "reason": "far"}]
    assert say


def test_policy_matches_pace_keywords():
    assert policy("đi chậm lại thôi", ALIASES)[0] == [{"type": "set_pace", "level": "slow"}]
    assert policy("đi nhiều nơi hơn nữa", ALIASES)[0] == [{"type": "set_pace", "level": "packed"}]


def test_policy_with_nothing_recognised_asks_to_use_the_chips():
    actions, say = policy("ừm", ALIASES)
    assert actions == [] and say == NONE
