"""Answers the user's own words already give, written before anything is asked (docs/TRIP_UNDERSTANDING.md §4).

A topic the user has answered in words is never asked again: "đi một mình" is one person, "với người yêu" two,
"ở gần chợ Đà Lạt" a lodging point, "bà đau gối" the same limit the care card's chip writes. Each derived value
keeps the user's quote and the tool "derived:<from>", so the read-back shows it and one tap undoes it. A value the
words do not fix (who else comes, where exactly to stay) is left for the question.
"""

import re

from ..infrastructure.catalog import Catalog
from .logistics import CITY
from .state import Base, Evidence, TripState, Update, apply, apply_drafts, pending_signals
from .text import fold, squash

CENTRE = re.compile(r"\b(trung tam|center|centre|central|downtown)\b")
# a wish kept in the user's words that is about where they sleep ("ở khách sạn 5 sao gần trung tâm")
STAY = re.compile(r"\b(khach san|homestay|hostel|resort|hotel|nha nghi|villa|o gan|o khu|o trung tam|stay)\b")
# a signal the user said -> the care card chip whose drafts answer it (questions.care_q)
CARE_CHIP = {"knee": "knee", "wheelchair": "wheelchair", "pregnant": "pregnant", "vegetarian": "veg",
             "vegan": "vegan", "motion_sick": "motion", "height": "height"}
PARTY = {frozenset({"solo"}): 1, frozenset({"partner"}): 2}
DERIVED = "derived:companions"


def derive(state: TripState, catalog: Catalog, turn: int) -> TripState:
    return _care(_lodging(_people(state, turn), catalog, turn), turn)


def _people(state: TripState, turn: int) -> TripState:
    who = frozenset(state.companions.value or ()) if state.companions.known else frozenset()
    n = PARTY.get(who) if state.companions.source == "user" else None
    derived = state.people.known and all(e.tool == DERIVED for e in state.people.evidence)
    if derived and n != state.people.value:  # the party changed after the count was derived from it
        state = state.model_copy(update={"people": type(state.people)()})
    if n is None or state.people.known:
        return state
    quote = next((e.quote for e in state.companions.evidence if e.quote), None)
    return apply(state, Update(field="people", value=n, source="user", confidence="high",
                               evidence=Evidence(turn=turn, quote=quote, tool=DERIVED)))


def _point(text: str, base: Base, catalog: Catalog) -> tuple[float, float] | None:
    """Where the words put the lodging: a corpus place they name, or the city centre."""
    ids = [base.place_id] if base.place_id else []
    words = f" {squash(text)} "
    ids += [pid for key, pid in catalog.name_keys if f" {key} " in words]
    for pid in ids:
        p = catalog.by_id.get(pid)
        if p is not None and p.lat is not None and p.lng is not None:
            return p.lat, p.lng
    return CITY if CENTRE.search(fold(text)) else None


def _lodging(state: TripState, catalog: Catalog, turn: int) -> TripState:
    if state.lodging.known:
        return state
    if not state.base.known:  # the agent kept the stay as a wish: it is the base when it says where
        wish = next((u for u in state.unmapped if STAY.search(fold(u.phrase))
                     and _point(u.phrase, Base(text=u.phrase), catalog)), None)
        if wish is None:
            return state
        state = apply(state, Update(field="base", value=Base(text=wish.phrase), source="user", confidence="high",
                                    evidence=Evidence(turn=wish.turn, quote=wish.phrase, tool="derived:unmapped")))
        state = state.model_copy(update={"unmapped": tuple(u for u in state.unmapped if u is not wish)})
    if state.base.source != "user":
        return state
    base = state.base.value
    point = _point(base.text, base, catalog)
    if point is None:
        return state
    quote = next((e.quote for e in state.base.evidence if e.quote), base.text)
    return apply(state, Update(field="lodging", value=Base(text=base.text, lat=point[0], lng=point[1], kind="address"),
                               source="user", confidence="high", evidence=Evidence(turn=turn, quote=quote, tool="derived:base")))


def _care(state: TripState, turn: int) -> TripState:
    said = [s for s in pending_signals(state) if s.kind in CARE_CHIP and s.quote]
    if not said:
        return state
    from .questions import care_q  # questions builds on this module's neighbours; imported late to keep layers flat
    chips = {c.id: c.drafts for c in care_q().chips}
    for s in said:
        state = apply_drafts(state, chips[CARE_CHIP[s.kind]], turn, tool=f"derived:signal:{s.kind}", quote=s.quote)
    if not (state.care.known and state.care.source == "user"):
        state = apply(state, Update(field="care", value="listed", source="user", confidence="high",
                                    evidence=Evidence(turn=turn, quote=said[0].quote, tool="derived:signal")))
    return state
