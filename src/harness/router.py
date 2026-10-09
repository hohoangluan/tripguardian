"""Stage routing is deterministic; a model cannot choose arbitrary modules or operations."""

from .contracts import Request, Stage

OPERATIONS = {
    "trip": frozenset({"turn", "advance"}),
    "decision": frozenset({"turn", "act", "advance", "back"}),
    "planning": frozenset({"act", "recommend", "back", "confirm"}),
}


COMPANION = frozenset({"checkin", "skip", "rate", "add", "adjust"})


class RouteError(ValueError):
    pass


def route(stage: Stage, request: Request) -> Stage:
    if request.stage != stage:
        raise RouteError(f"active stage is {stage}, not {request.stage}")
    if request.operation not in OPERATIONS[stage]:
        raise RouteError(f"{stage} does not accept {request.operation}")
    return stage


def route_companion(outputs: dict, operation: str) -> None:
    """Đang đi is open once the journey has a confirmed plan (outputs.planning), whatever stage it shows."""
    if "planning" not in outputs:
        raise RouteError("companion needs a confirmed plan")
    if operation not in COMPANION:
        raise RouteError(f"companion does not accept {operation}")
