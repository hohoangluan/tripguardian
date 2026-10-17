"""The seven user answers needed before planning; choosing places stays open."""

from .state import TripState, pending_signals

REQUIRED = ("trip", "companions", "mobility", "care", "pace", "budget", "lodging")
DEFAULT_REQUIRED = REQUIRED
# Names of the seven groups as the Web designs them: short nouns, never spoken phrases ("Phương tiện", not "cách đi lại").
TITLE = {"trip": "Ngày đi", "companions": "Đi với", "mobility": "Phương tiện", "care": "Lưu ý", "pace": "Nhịp độ",
         "budget": "Ngân sách", "lodging": "Nơi lưu trú"}
# The same groups inside a sentence ("Mình cần thêm: …").
LABEL = {"trip": "ngày đi, giờ giấc", "companions": "người đi cùng", "mobility": "phương tiện", "care": "lưu ý sức khỏe, ăn uống",
         "pace": "nhịp độ", "budget": "ngân sách", "lodging": "nơi lưu trú"}


def missing(state: TripState, required: tuple[str, ...] = REQUIRED) -> list[tuple[str, str]]:
    def answered(field):
        return field.known and field.source == "user"

    start = answered(state.checkin_at) or answered(state.frame.arrive) or answered(state.inbound)
    end = answered(state.checkout_at) or answered(state.frame.leave) or answered(state.outbound)
    known = {
        "trip": answered(state.start_date) and answered(state.days) and start and end,
        "companions": answered(state.companions) and answered(state.people),
        "mobility": answered(state.mobility),
        "care": not pending_signals(state) and ((answered(state.care) and state.care.value == "none")
                                               or (answered(state.care) and state.care.value == "listed" and bool(state.unmapped))
                                               or any(h.evidence for h in state.hard)),
        "pace": answered(state.pace) and "pace" not in state.meta.conflicts,
        "budget": (answered(state.budget_unlimited) and state.budget_unlimited.value is True)
                  or (answered(state.budget_vnd) and answered(state.budget_scope)),
        "lodging": answered(state.lodging) or "lodging" in state.meta.declined,  # skipped = "Cứ xếp giúp": the app picks
    }
    return [(key, LABEL[key]) for key in required if not known.get(key, False)]
