"""Trip State -> Search Input (docs/TRIP_UNDERSTANDING.md §11). Deterministic; refuses while a physical signal is open."""

from .state import (AnchorRef, Context, HardFilter, NoveltySpec, PaceSpec, SearchInput, SoftKey, SoftWeight, TripState,
                    WEIGHT_SIGN, ontology, pending_signals, unknown_fields)


class UnhandledSignal(Exception):
    """A health / body / diet hint has not been answered yet (docs/ARCHITECTURE.md §18.3)."""


def compile_search_input(state: TripState) -> SearchInput:
    pending = pending_signals(state)
    if pending:
        raise UnhandledSignal(", ".join(s.kind for s in pending))

    def v(field):
        return getattr(state, field).value

    soft = []
    for key, f in sorted(state.soft.items()):
        if f.known:
            k = SoftKey.parse(key)
            soft.append(SoftWeight(feature=k.feature, value=k.value, context=dict(k.context) or None,
                                   weight=WEIGHT_SIGN[f.value], source=f.source))
    return SearchInput(
        ontology_version=ontology().version,
        context=Context(start_date=v("start_date"), month=v("month"), days=v("days"), base=v("base"),
                        entry_point=v("entry_point"), exit_point=v("exit_point"),
                        mobility=v("mobility"), companions=tuple(sorted(v("companions") or ())), people=v("people"),
                        arrive_at=v("arrive_at"), leave_at=v("leave_at"), day_end=v("day_end"),
                        budget_vnd=v("budget_vnd"), experience=state.meta.experience),
        hard_filters=tuple(HardFilter(feature=h.feature, op=h.op, value=h.value,
                                      unknown_policy=h.unknown_policy or "exclude") for h in state.hard),
        anchors=tuple(AnchorRef(place_id=a.place_id, priority=a.priority)
                      for a in state.anchors if a.state == "matched" and a.place_id),
        soft_weights=tuple(soft),
        pace=PaceSpec(level=v("pace"), max_leg_min=v("max_leg_min"), crowd_tolerance=v("crowd_tolerance")),
        novelty=NoveltySpec(level=v("novelty"), visited=state.visited),
        unknowns=tuple(unknown_fields(state)),
        unmapped=tuple(u.phrase for u in state.unmapped))
