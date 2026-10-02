import pytest

from planning.scope import LODGING_FETCH, LODGING_HOME, NONE, RELAYOUT, VARIANT, act_scope


@pytest.mark.parametrize("type_, expected", [
    ("pick_variant", NONE), ("lock_slot", NONE), ("unlock", NONE), ("undo", NONE), ("redo", NONE),
    ("move_place", RELAYOUT), ("reorder", RELAYOUT), ("drop_place", RELAYOUT),
    ("add_from_backup", RELAYOUT), ("swap", RELAYOUT), ("relax", RELAYOUT),
    ("set_pace", VARIANT), ("set_objective", VARIANT), ("set_day_window", VARIANT),
    ("pick_lodging", LODGING_HOME), ("clear_lodging", LODGING_HOME),
    ("set_lodging", LODGING_FETCH), ("set_lodging_budget", LODGING_FETCH),
])
def test_every_act_type_maps_to_its_scope(type_, expected):
    assert act_scope({"type": type_}) == expected


def test_an_unknown_act_type_is_a_key_error():
    with pytest.raises(KeyError):
        act_scope({"type": "teleport"})
