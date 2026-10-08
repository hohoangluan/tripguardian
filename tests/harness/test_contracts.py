import pytest
from pydantic import ValidationError


def test_handoff_does_not_accept_a_client_supplied_output():
    from harness import Request
    with pytest.raises(ValidationError):
        Request(request_id="advance", stage="decision", operation="advance", expected_revision=0,
            payload={"decision_output": {"confirmed": [{"id": "invented"}]}})


def test_decision_output_validates_nested_search_input():
    from decision import DecisionOutput
    with pytest.raises(ValidationError):
        DecisionOutput.model_validate({"confirmed": [], "trip_context": {"bad": "schema"},
            "backup_pool": [], "wishlist": [], "decision_log": [], "feasibility": {}})
