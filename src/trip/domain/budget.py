"""A budget as the user said it -> VND per person per day, the unit Place Decision and Planning read.

"5 triệu cho 2 người" is the whole trip; "500k một ngày" is per day. When nothing says what the amount covers, its size
decides (TOTAL_FROM) and the screen marks the scope as a guess. Who pays is the party: `people`, or one for solo and two
for a couple; with neither known the amount cannot be split and the budget stays unknown (never guessed).
"""

from .state import BudgetIntent, Context, TripState

TOTAL_FROM = 2_000_000  # an amount this large with no scope said is read as the whole trip; below, per person per day


def scope(state: TripState) -> tuple[str | None, bool]:
    """-> (what the amount covers, whether that is a guess from its size). (None, False) without a budget."""
    if not state.budget_vnd.known:
        return None, False
    if state.budget_scope.known:
        return state.budget_scope.value, False
    if "budget_scope" in state.meta.declined:
        return None, False
    return ("trip_total" if state.budget_vnd.value >= TOTAL_FROM else "per_person_day"), True


def party(state: TripState) -> int | None:
    if state.people.known:
        return state.people.value
    who = state.companions.value or frozenset()
    return {frozenset({"solo"}): 1, frozenset({"partner"}): 2}.get(frozenset(who))


def per_person_day(state: TripState) -> int | None:
    """The budget in VND per person per day, or None when it is unknown or cannot be split (days or party unknown)."""
    s, _ = scope(state)
    if s is None:
        return None
    amount, days, n = state.budget_vnd.value, state.days.value, party(state)
    split = {"per_person_day": 1, "per_person": days, "per_day": n, "trip_total": days * n if days and n else None}[s]
    return round(amount / split) if split else None


def intent(state: TripState) -> BudgetIntent | None:
    selected, guessed = scope(state)
    if selected is None:
        return None
    return BudgetIntent(amount=state.budget_vnd.value, scope=selected, scope_guessed=guessed,
                        source=state.budget_vnd.source, evidence=state.budget_vnd.evidence,
                        scope_source="inferred" if guessed else state.budget_scope.source,
                        scope_evidence=state.budget_vnd.evidence if guessed else state.budget_scope.evidence)


def group_budget(context: Context | dict) -> int | None:
    """VND for the whole party and trip; missing conversion dimensions remain unknown."""
    ctx = context.model_dump(mode="json") if isinstance(context, Context) else context
    days, people = ctx.get("days"), ctx.get("people")
    if people is None:
        people = {frozenset({"solo"}): 1, frozenset({"partner"}): 2}.get(frozenset(ctx.get("companions") or ()))
    raw = ctx.get("budget_intent")
    if raw:
        amount, selected = raw["amount"], raw["scope"]
        if raw.get("currency", "VND") != "VND":
            return None
        factor = {"trip_total": 1, "per_day": days, "per_person": people,
                  "per_person_day": days * people if days and people else None}.get(selected)
        return round(amount * factor) if factor else None
    amount = ctx.get("budget_vnd")
    return round(amount * days * people) if amount is not None and days and people else None
