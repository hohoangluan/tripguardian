import pytest

from trip import TripState, compile_search_input
from trip.domain.state import Evidence, Field


def test_search_input_keeps_raw_budget_and_scope_evidence_when_conversion_is_unknown():
    evidence = (Evidence(turn=1, quote="5 triệu cho cả chuyến"),)
    state = TripState(budget_vnd=Field[int](value=5_000_000, source="user", evidence=evidence),
                      budget_scope=Field(value="trip_total", source="user", evidence=evidence))
    context = compile_search_input(state).context
    assert context.budget_vnd is None
    assert context.budget_intent.amount == 5_000_000
    assert context.budget_intent.scope == "trip_total"
    assert context.budget_intent.currency == "VND"
    assert context.budget_intent.source == "user"
    assert context.budget_intent.evidence == evidence
    assert context.budget_intent.scope_evidence == evidence
    assert not context.budget_intent.scope_guessed
    from trip import group_budget
    assert group_budget(context) == 5_000_000


@pytest.mark.parametrize("scope,amount,total", [
    ("trip_total", 6_000_000, 6_000_000), ("per_day", 2_000_000, 6_000_000),
    ("per_person", 3_000_000, 6_000_000), ("per_person_day", 1_000_000, 6_000_000),
])
def test_group_budget_uses_explicit_amount_scope(scope, amount, total):
    from trip import group_budget
    assert group_budget({"days": 3, "people": 2, "budget_vnd": 1,
                         "budget_intent": {"amount": amount, "scope": scope}}) == total


def test_group_budget_does_not_invent_missing_conversion_dimensions():
    from trip import group_budget
    assert group_budget({"days": 3, "people": None, "budget_vnd": 500_000}) is None
    assert group_budget({"days": 3, "people": None, "companions": ["partner"], "budget_vnd": 500_000}) == 3_000_000
    assert group_budget({"days": None, "people": None,
                         "budget_intent": {"amount": 4_000_000, "scope": "trip_total"}}) == 4_000_000


def test_guessed_budget_scope_keeps_inferred_provenance():
    evidence = (Evidence(turn=2, quote="5 triệu"),)
    state = TripState(budget_vnd=Field[int](value=5_000_000, source="user", evidence=evidence))
    intent = compile_search_input(state).context.budget_intent
    assert intent.scope_guessed and intent.scope_source == "inferred"
    assert intent.evidence == evidence
