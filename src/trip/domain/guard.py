"""Evidence checks between the agent and the Trip State (docs/TRIP_UNDERSTANDING.md §4).

The agent proposes; nothing is written unless the quote is the user's own words and the value parses. A refusal is
returned as text so the agent can correct itself in the same turn.
"""

import re
from difflib import SequenceMatcher
from typing import Literal

from pydantic import ValidationError
from requirements import Requirement, RequirementIntent

from . import values
from ..infrastructure.catalog import Catalog
from .state import SCALARS, Evidence, TripState, Update, apply, ontology, settle
from .text import contains, fold, squash

FieldName = Literal["start_date", "month", "month_part", "days", "nights", "companions", "people", "base", "entry_point", "exit_point", "mobility",
                    "checkin_at", "checkout_at", "day_end", "purpose", "anchor", "signal", "soft", "hard", "pace", "max_leg_min", "crowd_tolerance",
                    "novelty", "budget_vnd", "budget_scope", "liked_groups", "activity", "time_preference", "unmapped"]
GENERIC = {"du", "lich", "da", "lat", "dalat", "viet", "nam", "thanh", "pho", "tour"}  # a place name made only of these is a phrase
LIST_FIELDS = {"companions", "liked_groups", "anchor", "signal", "soft", "hard", "activity", "time_preference", "unmapped"}


# the words that name each companion value, as the user types them (folded, no diacritics)
GROUP_WORDS = {"partner": ("nguoi yeu", "ban gai", "ban trai", "vo chong"),
               "friends": ("ban be", "nhom ban", "hoi ban", "kieu ban"),  # "kiểu bạn" = like friends
               "parents": ("bo me", "ba me", "cha me", "ong ba"),
               "kids": ("con nho", "tre nho", "tre em", "em be"),
               "baby": ("em be", "be so sinh", "xe day", "con moi sinh"),
               "pet": ("thu cung", "con cho", "con meo", "cun cung"),
               "coworkers": ("dong nghiep", "cong ty", "team building"),
               "solo": ("mot minh", "solo")}
TYPO_RATIO = 0.8  # "bnạ bè" still names friends; "họ hàng xa" names no value at all


def names_group(quote: str, value: str) -> bool:
    """Whether the user's quote itself names the group `value`. Spelling slips are allowed: a window of words close
    enough to a group's words counts. A group the words do not name is an OTHER: the agent writes it as unmapped,
    never as the nearest value."""
    words = fold(quote).split()
    for phrase in GROUP_WORDS.get(value, ()):
        n = len(phrase.split())
        for i in range(len(words) - n + 1):
            window = " ".join(words[i:i + n])
            if SequenceMatcher(None, window, phrase).ratio() >= TYPO_RATIO:
                return True
    return False


GROUP_LABEL = {"partner": "người yêu", "friends": "bạn bè", "parents": "bố mẹ", "kids": "trẻ nhỏ", "solo": "một mình",
               "baby": "em bé", "pet": "thú cưng", "coworkers": "đồng nghiệp"}


def nearest_group(quote: str) -> str | None:
    """The companions value whose words the quote names (same closeness as names_group), for asking "có phải … không?".
    None when no value is named. Only a question to the user: nothing is written from it."""
    return next((v for v in GROUP_WORDS if names_group(quote, v)), None)


def record_fact(state: TripState, field: str, op: str, value: str, quote: str, how: str, text: str, turn: int,
                catalog: Catalog, compared: list[dict] | None = None, requirement: dict | None = None) -> tuple[TripState, str]:
    """-> (state, note). note is "" when the fact was written, else why it was refused (the agent reads it and corrects).
    text: this turn's message (the quote must come from it); compared: places the message compares the trip to,
    with their traits (trip.domain.traits). Unmapped bypasses every check below and is never refused: when no
    value fits, the agent always has somewhere to keep the user's own words, so a turn never dead-ends in refusals."""
    if field == "unmapped" and op != "remove":
        said = how == "said"
        state = apply(state, Update(field="unmapped", op="add", value=value, source="user" if said else "inferred",
                                    confidence="high" if said else "medium", evidence=Evidence(turn=turn, quote=quote)))
        return settle(state), ""
    if not contains(text, quote):
        return state, (f"refused: quote {quote!r} is not in the user's message; copy the user's exact words, or do not "
                       f"record {field!r} again this turn if this message does not say it")
    if field == "companions":
        value = ontology().who(value)  # a vocabulary id, or a synonym of one, becomes the id; else the user's own words
        if value not in values.ENUM_VALUES["companions"]:
            # someone the vocabulary has no id for ("hàng xóm"): kept as said, never mapped to the nearest id
            if op != "remove" and not (contains(text, value) or contains(quote, value)):
                return state, f"refused: {value!r} is not in the user's message; copy the user's own words for who goes"
            state = apply(state, Update(field="companions_other", op="remove" if op == "remove" else "add", value=value,
                                        source="user" if how == "said" else "inferred",
                                        confidence="high" if how == "said" else "medium",
                                        evidence=Evidence(turn=turn, quote=quote)))
            return settle(state), ""
    if field == "companions" and op != "remove" and not (names_group(quote, value) or names_group(text, value)):
        # Fail-closed: a group the user's own words do not name is never a guess. The agent keeps it as
        # unmapped and asks who comes; nothing is written from this call.
        return state, (f"refused: {value!r} is not one of companions [solo|partner|friends|kids|parents|baby|pet|coworkers] named "
                       f"by the user's words. Do NOT retry companions for this wish. Instead call record_fact "
                       f"exactly once with field=\"unmapped\", op=\"add\", value=\"<the user's own group words>\", "
                       f"quote=\"<the same words copied from the message>\", how=\"said\". Never put the word "
                       f"\"unmapped\" or a group name in the value of companions. If the message supports no wish "
                       f"at all, call drop_refusal for companions")
    named = [c for c in compared or () if contains(quote, c["name"])] if field == "soft" and how == "inferred" else []
    if named:
        key = values.split_weight(value)[0].replace(" ", "")
        if key not in {f"{t['feature']}={t['value']}" for c in named for t in c["traits"]}:
            return state, f"refused: {value!r} is not a trait of {named[0]['name']!r}"
    # a taste read from a place the user compared to remembers that place: the ticket says "(giống X)"
    ev = Evidence(turn=turn, quote=quote, tool=f"place:{named[0]['id']}" if named else None)
    said = how == "said"
    op = op if field in LIST_FIELDS else ("remove" if op == "remove" else "set")
    try:
        if op == "remove":
            parsed = None if field in SCALARS else values.parse_remove(field, value)
        else:
            parsed = values.parse(field, value, catalog)
        if field not in ("hard", "soft"):  # only a hard or soft fact has a requirement; an extra object is ignored
            requirement = None
        intent = RequirementIntent.model_validate(requirement) if requirement is not None else None
        if intent and field not in ("hard", "soft"):
            raise ValueError("requirement metadata is only accepted for hard or soft")
        if intent and op != "remove":
            if field == "soft":
                key = parsed[0].split("@")[0]
                fid, val = key.split("=")
                Requirement(feature=fid, op="eq", value=val, strength="preference", **intent.model_dump())
            elif field == "hard":
                Requirement(**parsed, **intent.model_dump())
        if field == "activity" and op != "remove" and not contains(quote, catalog.by_id[parsed["place_id"]].name):
            raise ValueError("the activity quote must name the selected place")
        if field == "time_preference" and parsed.get("place_id") and not contains(quote, catalog.by_id[parsed["place_id"]].name):
            raise ValueError("the time preference quote must name the selected place")
        state = apply(state, Update(field=field, op=op, value=parsed, source="user" if said else "inferred",
                                    confidence="high" if said else "medium", evidence=ev, requirement=intent))
    except (ValueError, ValidationError) as e:
        hint = " (soft: feature=value:love|avoid with ids from FEATURES; if none fits, use field unmapped)" \
            if field in ("soft", "hard") else ""
        return state, f"refused: {value!r} is not a valid {field}: {str(e).splitlines()[0]}{hint}"
    return settle(state), ""


def drop_questions(say: str) -> str:
    """The sentences of `say` that are not questions."""
    return " ".join(x for x in re.split(r"(?<=[.!?…])\s+", say) if not x.rstrip().endswith("?")).strip()


def state_text(state: TripState) -> str:
    """The known values of the trip (date, days, nights, ...) as text: numbers the reply may repeat."""
    return " ".join(str(values.jsonable(f.value)) for f in (state.start_date, state.month, state.days, state.nights, state.people)
                    if f.known)


def bad_say(say: str, heard: str, state: TripState, catalog: Catalog, compared: set[str]) -> str | None:
    """Why `say` may not be shown: a number the user never said, or a place the user never named."""
    said = {int(n) for n in re.findall(r"\d+", heard + " " + state_text(state))}  # the user's digits and the trip's own
    extra = [n for n in re.findall(r"\d+", say) if int(n) not in said]
    if extra:
        return f"numbers {extra} the user did not say"
    named = {a.place_id for a in state.anchors if a.place_id} | compared  # the user named these
    s = f" {squash(say)} "
    for key, pid in catalog.name_keys:
        if pid not in named and not set(key.split()) <= GENERIC and f" {key} " in s:
            return f"names place {pid}"
    return None
