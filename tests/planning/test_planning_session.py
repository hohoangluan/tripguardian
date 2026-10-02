import pytest
from plan_fixtures import CFG, decision, rec

from planning.places import build_places
from planning.session import ActCtx, ActionError, Session, State, Store, apply_act


def place_map(*recs):
    places, _ = build_places(decision([r["id"] for r in recs]), {r["id"]: r for r in recs}, CFG)
    return {p.id: p for p in places}


def ctx(**kw):
    by_place = kw.pop("by_place", place_map(rec("a", 1, 1), rec("b", 2, 2), rec("c", 3, 3)))
    defaults = dict(by_place=by_place, n_days=2, variant_ids={"v1", "v2"}, backup_ids={"k": {"for": "a", "reason": None}},
                    day_members=[["a", "b"], ["c"]], objective_names={"least_travel", "low_cost"},
                    valid_paces={"slow", "normal", "packed"})
    return ActCtx(**{**defaults, **kw})


def test_pick_variant_sets_the_chosen_variant_and_rejects_an_unknown_one():
    s = apply_act(State(), {"type": "pick_variant", "id": "v2"}, ctx())
    assert s.chosen_variant == "v2"
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "pick_variant", "id": "v9"}, ctx())


def test_move_place_records_the_assignment_and_clears_any_drop():
    s = State(dropped=[])
    s = apply_act(s, {"type": "drop_place", "place": "a"}, ctx())
    s = apply_act(s, {"type": "move_place", "place": "a", "day": 1}, ctx())
    assert s.assignment["a"] == 1 and not any(d.place_id == "a" for d in s.dropped)


def test_move_place_out_of_range_or_unknown_place_is_an_action_error():
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "move_place", "place": "a", "day": 9}, ctx())
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "move_place", "place": "ghost", "day": 0}, ctx())


def test_moving_a_locked_place_is_refused_before_repair_day_even_runs():
    with pytest.raises(ActionError):
        apply_act(State(locked=["a"]), {"type": "move_place", "place": "a", "day": 1}, ctx())


def test_reorder_must_be_a_permutation_of_the_days_current_members():
    s = apply_act(State(), {"type": "reorder", "day": 0, "order": ["b", "a"]}, ctx())
    assert s.order_override[0] == ["b", "a"]
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "reorder", "day": 0, "order": ["a"]}, ctx())


def test_add_from_backup_requires_a_pool_id():
    s = apply_act(State(), {"type": "add_from_backup", "place": "k", "day": 1}, ctx())
    assert s.assignment["k"] == 1
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "add_from_backup", "place": "not_in_pool", "day": 1}, ctx())


def test_swap_drops_the_old_place_and_adds_the_backup_at_its_day():
    s = apply_act(State(), {"type": "swap", "place": "a", "with": "k"}, ctx())
    assert s.dropped[-1].place_id == "a" and s.assignment["k"] == 0        # a was on day 0


def test_lock_and_unlock_round_trip():
    s = apply_act(State(), {"type": "lock_slot", "place": "a"}, ctx())
    assert s.locked == ["a"]
    s = apply_act(s, {"type": "unlock", "place": "a"}, ctx())
    assert s.locked == []


def test_set_pace_and_set_objective_validate_against_the_ctx():
    s = apply_act(State(), {"type": "set_pace", "level": "packed"}, ctx())
    assert s.pace_override == "packed"
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "set_pace", "level": "turbo"}, ctx())
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "set_objective", "name": "not_an_objective"}, ctx())


def test_set_day_window_parses_clock_strings_and_rejects_start_after_end():
    s = apply_act(State(), {"type": "set_day_window", "day": 0, "start": "09:00", "end": "20:00"}, ctx())
    assert s.day_window_override[0] == (540, 1200)
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "set_day_window", "day": 0, "start": "20:00", "end": "09:00"}, ctx())


def test_relax_rejects_a_physical_feature():
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "relax", "place_id": "a", "feature": "steep_or_stairs"}, ctx())
    s = apply_act(State(), {"type": "relax", "place_id": "a", "feature": "parking"}, ctx())
    assert s.relaxed[0].place_id == "a" and s.relaxed[0].feature == "parking"


def test_relax_whole_trip_needs_an_explicit_place_list_from_the_caller():
    s = apply_act(State(), {"type": "relax", "feature": "parking", "scope": "whole_trip", "place_ids": ["a", "b"]}, ctx())
    assert {r.place_id for r in s.relaxed} == {"a", "b"}


def test_pick_lodging_and_clear_lodging_mark_lodging_touched():
    s = apply_act(State(), {"type": "pick_lodging", "id": "h1"}, ctx())
    assert s.lodging_touched and s.lodging_id == "h1"
    s = apply_act(s, {"type": "clear_lodging"}, ctx())
    assert s.lodging_touched and s.lodging_id is None


def test_set_lodging_needs_a_resolved_point_from_the_caller():
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "set_lodging", "text": "Homestay X"}, ctx())
    point = {"id": "manual:1", "lat": 1.0, "lng": 1.0, "text": "Homestay X", "source": "nominatim", "fetched_at": "t"}
    s = apply_act(State(), {"type": "set_lodging", "text": "Homestay X", "_point": point}, ctx())
    assert s.lodging_touched and s.lodging_point == point


def test_set_lodging_budget_accepts_none_or_a_non_negative_int():
    s = apply_act(State(), {"type": "set_lodging_budget", "max_per_night": 500000}, ctx())
    assert s.budget_override == 500000
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "set_lodging_budget", "max_per_night": -1}, ctx())


def test_an_unknown_act_type_is_an_action_error():
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "teleport"}, ctx())


def test_store_round_trips_through_disk(tmp_path):
    store = Store(tmp_path)
    s = store.new({"confirmed": []}, "dsid")
    store.save(s)
    reloaded = Store(tmp_path).get(s.id)
    assert reloaded.decision_session_id == "dsid" and reloaded.state == State()


def test_store_unknown_or_malformed_id_is_a_key_error(tmp_path):
    with pytest.raises(KeyError):
        Store(tmp_path).get("not-twelve-hex")
    with pytest.raises(KeyError):
        Store(tmp_path).get("0" * 12)
