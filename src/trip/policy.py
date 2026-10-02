"""Deterministic choice of the next question (docs/TRIP_UNDERSTANDING.md §7, §9). Used for chips, edits, and as the
fallback when the agent fails."""

from .catalog import Catalog
from .questions import READY, Question, bank, clarify_q, purpose_q, rank_questions, required, show_first_q
from .settings import Settings
from .state import TripState


def next_question(state: TripState, catalog: Catalog, cfg: Settings) -> Question:
    req = required(state, catalog, cfg)
    if req:
        return req
    done = set(state.meta.asked) | state.meta.skipped
    if state.meta.unsure_streak >= 2 and "show_first" not in done:
        return show_first_q()
    if state.meta.adaptive_turns >= cfg.turn_budget:
        return READY
    if q := clarify_q(state):
        return q
    if state.meta.experience == "first" and not state.purpose.known and not state.soft and "purpose" not in done:
        return purpose_q()
    ranked = rank_questions(state, catalog, cfg)
    if ranked and ranked[0][1] >= cfg.stop_score:
        return ranked[0][0]
    return READY


def askable(state: TripState, catalog: Catalog, cfg: Settings) -> dict[str, Question]:
    """Questions the agent may pick by qid this turn (tier 1 is handled separately by the guard)."""
    qs = bank(state, catalog, cfg)
    if q := clarify_q(state):
        qs.append(q)
    qs += [show_first_q(), READY]
    if not state.purpose.known:
        qs.append(purpose_q())
    return {q.qid: q for q in qs}
