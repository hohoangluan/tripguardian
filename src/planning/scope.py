"""act_scope (docs/specs/PLANNING_SPEC.md §Vòng người dùng sửa và góp ý, act table): which part of a session's laid
out trip one act must rerun. Mirrors src/decision/scope.py's replan_scope for the same reason: the UI's diff
promises an exact scope, so the dispatcher must pick one, not "rerun everything and hope it looks the same" -- that
is exactly the "không xáo lịch âm thầm" guardrail (docs/specs/PLANNING_SPEC.md §Guardrail).
"""

NONE = "none"                      # state only: nothing about the laid-out days changes
RELAYOUT = "relayout"              # one or two days' membership or order changed; the rest of the trip is untouched
VARIANT = "variant"                 # a trip-wide parameter changed; the chosen objective's whole day split reruns
LODGING_HOME = "lodging_home"       # the day anchor changed among lodging candidates already fetched
LODGING_FETCH = "lodging_fetch"     # the candidate list itself must be re-fetched or extended

_SCOPE = {
    "pick_variant": NONE, "lock_slot": NONE, "unlock": NONE, "undo": NONE, "redo": NONE,
    "move_place": RELAYOUT, "reorder": RELAYOUT, "drop_place": RELAYOUT, "add_from_backup": RELAYOUT,
    "swap": RELAYOUT, "relax": RELAYOUT,
    "set_pace": VARIANT, "set_objective": VARIANT, "set_day_window": VARIANT,
    "pick_lodging": LODGING_HOME, "clear_lodging": LODGING_HOME,
    "set_lodging": LODGING_FETCH, "set_lodging_budget": LODGING_FETCH,
}


def act_scope(action: dict) -> str:
    return _SCOPE[action.get("type")]


_ORDER = [NONE, RELAYOUT, VARIANT, LODGING_HOME, LODGING_FETCH]


def widest(scopes: list[str]) -> str:
    """The scope among `scopes` that implies the most rebuilding -- what a turn's diff reports when it applied more
    than one act (docs/specs/PLANNING_SPEC.md §Guardrail: "không xáo lịch âm thầm" -- the diff must say honestly
    how much a turn actually touched, not just the last action's own scope)."""
    return max(scopes, key=_ORDER.index, default=NONE)
