"""What Trip Understanding must know before the user may move on (config/trip.yaml `required`). Decided by code, not by the model."""

from .state import TripState, pending_signals

LABEL = {"days": "số ngày", "companions": "đi cùng ai", "mobility": "đi lại bằng gì", "when": "ngày hoặc tháng đi",
         "signal": "điều cần lưu ý về sức khỏe"}
DEFAULT_REQUIRED = ("days", "companions", "mobility", "when")


def missing(state: TripState, required: tuple[str, ...] = DEFAULT_REQUIRED) -> list[tuple[str, str]]:
    """-> [(key, Vietnamese label)] still needed. `when` is a start date or a month; an open health / body / diet hint
    always blocks (fail-closed)."""
    known = {"days": state.days.known, "companions": state.companions.known, "mobility": state.mobility.known,
             "when": state.start_date.known or state.month.known}
    out = [(k, LABEL[k]) for k in required if not known.get(k, True)]
    if pending_signals(state):
        out.append(("signal", LABEL["signal"]))
    return out
