from datetime import date

import pytest
from pydantic import ValidationError

from trip.state import (Draft, Evidence, Field, SoftKey, TripState, Update, apply, apply_drafts, unknown_fields)

EV = Evidence(turn=1, quote="x")


def up(field, value=None, op="set", source="user", confidence="high"):
    return Update(field=field, op=op, value=value, source=source, confidence=confidence, evidence=EV)


def test_value_without_evidence_is_rejected():
    with pytest.raises(ValidationError):
        Field[int](value=3, source="user")
    with pytest.raises(ValidationError):
        Evidence(turn=1)


def test_soft_key_must_be_in_ontology():
    k = SoftKey.parse("crowd=low@time_of_day.morning@day_type.weekend")
    assert str(k) == "crowd=low@day_type.weekend@time_of_day.morning"
    for bad in ("crowd=empty", "nope=present", "crowd=low@time_of_day.midnight", "crowd", "crowd=low@morning"):
        with pytest.raises(ValueError):
            SoftKey.parse(bad)


def test_user_confirmed_value_is_not_overwritten_by_inference():
    s = apply(TripState(), up("pace", "packed"))
    assert apply(s, up("pace", "slow", source="inferred", confidence="medium")).pace.value == "packed"
    assert apply(s, up("pace", op="remove", source="inferred", confidence="medium")).pace.value == "packed"
    assert apply(s, up("pace", "slow")).pace.value == "slow"


def test_keyword_value_can_be_replaced_by_the_agent():
    s = apply(TripState(), up("days", 3, confidence="medium"))  # prepass: user words, not confirmed
    assert apply(s, up("days", 4, source="inferred", confidence="medium")).days.value == 4


def test_ranges_clock_and_literals_are_checked():
    with pytest.raises(ValueError):
        apply(TripState(), up("days", 12))
    with pytest.raises(ValueError):
        apply(TripState(), up("arrive_at", "9h"))
    with pytest.raises(ValueError):
        apply(TripState(), up("mobility", "bus"))
    assert apply(TripState(), up("arrive_at", "09:30")).arrive_at.value == "09:30"


def test_companions_add_and_remove():
    s = apply(apply(TripState(), up("companions", "parents", op="add")), up("companions", "kids", op="add"))
    assert s.companions.value == {"parents", "kids"}
    assert apply(s, up("companions", "kids", op="remove")).companions.value == {"parents"}


def test_soft_set_and_remove_normalise_the_key():
    s = apply(TripState(), up("soft", ("crowd=low@time_of_day.morning", "love"), op="add"))
    assert list(s.soft) == ["crowd=low@time_of_day.morning"]
    assert apply(s, up("soft", "crowd=low@time_of_day.morning", op="remove")).soft == {}


def test_user_remove_marks_skipped():
    s = apply(apply(TripState(), up("budget_vnd", 300_000)), up("budget_vnd", op="remove"))
    assert not s.budget_vnd.known and s.budget_vnd.status == "skipped"


def test_effort_hard_filter_settles_physical_signals():
    s = apply(TripState(), up("signal", "knee", op="add"))
    assert [x.handled for x in s.signals] == [False]
    steep = Draft(field="hard", op="add", value={"feature": "steep_or_stairs", "op": "ne", "value": "present"})
    s = apply_drafts(s, [steep], turn=2, tool="chip:c_effort:steep")
    assert [x.handled for x in s.signals] == [True]


def test_hard_dedupe_and_policy():
    d = {"feature": "steep_or_stairs", "op": "ne", "value": "present"}
    s = apply(apply(TripState(), up("hard", d, op="add")), up("hard", d, op="add"))
    assert len(s.hard) == 1
    assert apply(s, up("hard_policy", ("steep_or_stairs", "flag"))).hard[0].unknown_policy == "flag"
    with pytest.raises(ValueError):
        apply(TripState(), up("hard", {"feature": "steep_or_stairs", "op": "ne", "value": "maybe"}, op="add"))


def test_pending_add_and_remove():
    s = apply(TripState(), up("pending", {"phrase": "chill", "keys": ["noise=quiet", "crowd=low"]}, op="add"))
    assert s.meta.pending[0].keys == ("noise=quiet", "crowd=low")
    assert apply(s, up("pending", "chill", op="remove")).meta.pending == ()


def test_unknown_fields_lists_what_is_missing():
    s = apply(TripState(), up("days", 3))
    assert "dates" in unknown_fields(s) and "days" not in unknown_fields(s)


def test_state_round_trips_through_json():
    s = apply(apply(TripState(), up("start_date", date(2026, 12, 12))), up("companions", "parents", op="add"))
    s = apply(s, up("soft", ("noise=quiet", "love"), op="add"))
    assert TripState.model_validate_json(s.model_dump_json()) == s
