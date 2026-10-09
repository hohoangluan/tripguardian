"""Trip State -> Search Input (docs/TRIP_UNDERSTANDING.md §9). Deterministic; refuses while a physical signal is open."""

from ..infrastructure.settings import ARRIVAL_BUFFER_MIN
from .budget import per_person_day
from .logistics import clock_after
from .state import (AnchorRef, Context, HardFilter, NoveltySpec, PaceSpec, SearchInput, SoftKey, SoftWeight, TripState,
                    WEIGHT_SIGN, ontology, pending_signals, unknown_fields)


class UnhandledSignal(Exception):
    """A health / body / diet hint has not been answered yet (docs/ARCHITECTURE.md §18.3)."""


def day_window(state: TripState, buffer_min: int = ARRIVAL_BUFFER_MIN) -> tuple[str | None, str | None]:
    """(opens, closes) of the trip's first and last day. The hours the user wants (check-in / check-out) are only a
    wish: a chosen coach or flight is physical, so the day opens no earlier than its arrival + buffer and closes no
    later than its departure - buffer."""
    opens, closes = state.checkin_at.value, state.checkout_at.value
    if t := state.inbound.value:
        floor = clock_after(t.arrive_at, buffer_min)
        opens = max(opens, floor) if opens else floor
    if t := state.outbound.value:
        ceiling = clock_after(t.depart_at, -buffer_min)
        closes = min(closes, ceiling) if closes else ceiling
    return opens, closes


def compile_search_input(state: TripState, arrival_buffer_min: int = ARRIVAL_BUFFER_MIN) -> SearchInput:
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
    opens, closes = day_window(state, arrival_buffer_min)
    budget = per_person_day(state)
    unknowns = unknown_fields(state)
    if budget is None and "budget_vnd" not in unknowns:  # an amount nobody can split yet (days or party unknown)
        unknowns.append("budget_vnd")
    return SearchInput(
        ontology_version=ontology().version,
        context=Context(start_date=v("start_date"), month=v("month"), month_part=v("month_part"), days=v("days"), nights=v("nights"),
                        base=v("base"),
                        entry_point=v("entry_point"), exit_point=v("exit_point"),
                        mobility=v("mobility"), companions=tuple(sorted(v("companions") or ())), people=v("people"),
                        checkin_at=opens, checkout_at=closes, day_end=v("day_end"),
                        budget_vnd=budget, experience=state.meta.experience, origin=v("origin"),
                        arrival_mode=v("arrival_mode"), inbound=v("inbound"), outbound=v("outbound"),
                        lodging_booked=v("lodging_booked"), lodging=v("lodging")),
        hard_filters=tuple(HardFilter(feature=h.feature, op=h.op, value=h.value,
                                      unknown_policy=h.unknown_policy or "exclude") for h in state.hard),
        anchors=tuple(AnchorRef(place_id=a.place_id, priority=a.priority)
                      for a in state.anchors if a.state == "matched" and a.place_id),
        soft_weights=tuple(soft),
        pace=PaceSpec(level=v("pace"), max_leg_min=v("max_leg_min"), crowd_tolerance=v("crowd_tolerance")),
        novelty=NoveltySpec(level=v("novelty"), visited=state.visited),
        unknowns=tuple(unknowns),
        unmapped=tuple(u.phrase for u in state.unmapped),
        liked_groups=v("liked_groups") or ())
