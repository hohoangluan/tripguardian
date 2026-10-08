import pytest


def request(stage, operation):
    from harness import Request
    return Request(request_id="request-1", stage=stage, operation=operation, expected_revision=0)


def test_router_rejects_wrong_stage_before_dispatch():
    from harness import RouteError, route
    with pytest.raises(RouteError):
        route("trip", request("decision", "act"))


def test_planning_does_not_accept_a_chat_turn():
    from harness import RouteError, route
    with pytest.raises(RouteError):
        route("planning", request("planning", "turn"))
    assert route("planning", request("planning", "recommend")) == "planning"


@pytest.mark.parametrize("stage,operation", [("trip", "turn"), ("trip", "advance"),
    ("decision", "act"), ("decision", "turn"), ("decision", "advance"),
    ("decision", "back"), ("planning", "act"), ("planning", "back"), ("planning", "confirm")])
def test_router_accepts_only_declared_operations(stage, operation):
    from harness import route
    assert route(stage, request(stage, operation)) == stage


@pytest.mark.parametrize("stage,operation", [("trip", "act"), ("trip", "back"),
    ("decision", "recommend"), ("decision", "confirm"), ("planning", "advance")])
def test_router_rejects_unsupported_operations(stage, operation):
    from harness import RouteError, route
    with pytest.raises(RouteError):
        route(stage, request(stage, operation))
