"""Evidence checks between the agent and the Trip State (docs/TRIP_UNDERSTANDING.md §4).

The agent proposes; nothing is written unless the quote is the user's own words and the value parses. A refusal is
returned as text so the agent can correct itself in the same turn.
"""

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Literal

from pydantic import ValidationError
from requirements import Requirement, RequirementIntent

from . import values
from ..infrastructure.catalog import Catalog
from .state import SCALARS, Evidence, TripState, Update, apply, ontology, settle
from .text import contains, fold, language, squash

FieldName = Literal["start_date", "month", "month_part", "days", "nights", "companions", "people", "base", "entry_point", "exit_point", "mobility",
                    "checkin_at", "checkout_at", "day_end", "purpose", "anchor", "signal", "soft", "hard", "pace", "max_leg_min", "crowd_tolerance",
                    "frame.arrive", "frame.leave", "drive_day_min", "driver", "care", "budget_unlimited", "novelty", "budget_vnd", "budget_scope", "liked_groups", "activity", "time_preference", "unmapped", "like"]
# a place name made only of these is a phrase ("Đặc sản Đà Lạt", "Khu Vui Chơi" are said as plain words too)
GENERIC = {"du", "lich", "da", "lat", "dalat", "viet", "nam", "thanh", "pho", "tour", "dac", "san", "khu", "vui", "choi"}
LIST_FIELDS = {"companions", "liked_groups", "anchor", "signal", "soft", "hard", "activity", "time_preference", "unmapped"}


# Short words keep their marks; longer phrases tolerate spelling slips.
GROUP_WORDS = {"partner": ("người yêu", "bạn gái", "bạn trai", "vợ chồng", "bồ", "ny", "ngừi iu", "người iu", "vợ", "chồng", "wife", "husband"),
               "friends": ("bạn", "bạn bè", "nhóm bạn", "hội bạn", "kiểu bạn", "đứa bạn", "nhom minh", "hoi minh"),
               "parents": ("bo me", "ba me", "cha me", "ong ba", "ba ma", "voi me", "voi ba", "voi bo", "mother", "father"),
               "kids": ("con nho", "tre nho", "tre em", "em be", "kids", "children"),
               "baby": ("em be", "be so sinh", "xe day", "con moi sinh"),
               "pet": ("thu cung", "con cho", "con meo", "cun cung"),
               "coworkers": ("dong nghiep", "cong ty", "team building"),
               "solo": ("mot minh", "1 minh", "solo", "alone", "no one", "nobody", "just me", "by myself")}
# Children said the everyday way: "2 đứa nhỏ", "hai bé", "con trai", "tụi nhỏ". A bare "6 đứa" is a group of friends.
KIDS = re.compile(r"\b(?:\d+|hai|ba|bốn|năm|mấy|các|những)\s+(?:đứa\s+)?(?:bé|cháu|nhóc|con)\b(?!\s*(?:chó|mèo|cún))"
                  r"|\bđứa\s+(?:nhỏ|con|bé)\b|\b(?:con|bé)\s+(?:trai|gái)\b|\b(?:tụi|bọn|lũ|mấy)\s+(?:nhỏ|trẻ|nhóc)\b")
# A wish in the user's words that is about someone's body or diet: it answers "Lưu ý" (care) as listed. The data has
# no verified feature for most of them, so they stay notes, never filters.
CARE_NOTE = re.compile(r"\b(di ung|kieng|an chay|chay truong|thuan chay|hen suyen|suyen|tieu duong|huyet ap|tim mach|"
                       r"say xe|say deo|say song|dau (?:goi|lung|chan)|thoai hoa|mang thai|co bau|xe lan|so (?:do )?cao|"
                       r"khong an duoc|benh(?! vien)|allerg\w*|vegan|vegetarian|halal|gluten|lactose)\b")
TYPO_RATIO = 0.8  # "bnạ bè" still names friends; "họ hàng xa" names no value at all


def names_group(quote: str, value: str) -> bool:
    """Whether the user's quote itself names the group `value`. Spelling slips are allowed: a window of words close
    enough to a group's words counts. A group the words do not name is an OTHER: the agent writes it as unmapped,
    never as the nearest value."""
    marked = unicodedata.normalize("NFC", quote).casefold()
    if value == "parents":
        if re.search(r"\b(mẹ|bố|cha)\s+con\b", marked):
            return False
        if re.search(r"\b(mẹ|bố|cha|má)\b|\b(ông|bà)\s+(ngoại|nội)\b", marked):  # exact: "ba người" is no grandmother
            return True
    if value == "kids" and (re.search(r"\bbé\s+\d+", marked) or KIDS.search(marked)):
        return True
    words = re.findall(r"\w+", marked)
    if value == "friends" and re.search(r"\b\d+\s+đứa\b(?!\s+(?:nhỏ|con|bé|cháu))", marked):  # "nhóm mình 6 đứa": peers
        return True
    if value == "friends" and contains(quote, "sinh viên") and any(
            w in ("đứa", "nhóm") or (w.isdecimal() and int(w) >= 2) for w in words):
        return True
    for phrase in GROUP_WORDS.get(value, ()):
        n = len(phrase.split())
        for i in range(len(words) - n + 1):
            window = " ".join(words[i:i + n])
            if window == phrase or (n > 1 and SequenceMatcher(None, fold(window), fold(phrase)).ratio() >= TYPO_RATIO):
                return True
    return False


GROUP_LABEL = {"partner": "người yêu", "friends": "bạn bè", "parents": "bố mẹ", "kids": "trẻ nhỏ", "solo": "một mình",
               "baby": "em bé", "pet": "thú cưng", "coworkers": "đồng nghiệp"}


def nearest_group(quote: str) -> str | None:
    """The companions value whose words the quote names (same closeness as names_group), for asking "có phải … không?".
    None when no value is named. Only a question to the user: nothing is written from it."""
    return next((v for v in GROUP_WORDS if names_group(quote, v)), None)


def record_fact(state: TripState, field: str, op: str, value: str, quote: str, how: str, text: str, turn: int,
                catalog: Catalog, compared: list[dict] | None = None, requirement: dict | None = None,
                replaces: str | None = None, history: tuple[tuple[int, str], ...] = ()) -> tuple[TripState, str]:
    """-> (state, note). note is "" when the fact was written, else why it was refused (the agent reads it and corrects).
    text: this turn's message; history: earlier user turns eligible as quote evidence; compared: places mentioned
    with their traits (trip.domain.traits). Unmapped bypasses every check below and is never refused: when no
    value fits, the agent always has somewhere to keep the user's own words, so a turn never dead-ends in refusals."""
    if field == "unmapped" and op != "remove":
        said = how == "said"
        new = fold(value)
        # the same wish told again at more length ("dị ứng lạc" -> "dị ứng lạc; cần tránh cả lẫn chéo") replaces it
        state = state.model_copy(update={"unmapped": tuple(
            u for u in state.unmapped if not (fold(u.phrase) != new and fold(u.phrase) in new))})
        before = len(state.unmapped)
        state = apply(state, Update(field="unmapped", op="add", value=value, source="user" if said else "inferred",
                                    confidence="high" if said else "medium", evidence=Evidence(turn=turn, quote=quote)))
        if replaces and len(state.unmapped) > before:  # a new wish: link it to the field it stands in for
            *rest, last = state.unmapped
            state = state.model_copy(update={"unmapped": (*rest, last.model_copy(update={"replaces": replaces}))})
        if said and CARE_NOTE.search(new) and not (state.care.known and state.care.source == "user"):
            # a health or diet note in the user's own words answers "Lưu ý": nothing else to ask there
            state = apply(state, Update(field="care", op="set", value="listed", source="user", confidence="high",
                                        evidence=Evidence(turn=turn, quote=quote)))
        return settle(state), ""
    marked_quote = unicodedata.normalize("NFC", quote).casefold()
    evidence_turn = next((n for n, words in ((turn, text), *reversed(history)) if contains(words, quote)
                          and (field != "companions" or marked_quote in unicodedata.normalize("NFC", words).casefold())), None)
    if evidence_turn is None:
        return state, (f"refused: quote {quote!r} is not in the user's message; copy the user's exact words, or do not "
                       f"record {field!r} again this turn if this message does not say it")
    if op != "remove" and field not in ("hard", "soft") and value.strip().casefold() in {"", "unknown", "none", "null", "n/a"}:
        if not (field == "care" and value.strip().casefold() == "none"):
            return state, "warning: placeholder value was not recorded"
    if field == "like":
        try:
            import json
            from .resolve import anchor_for
            from .state import LikeWish, SoftKey
            raw = json.loads(value)
            reference = anchor_for(raw["place"], catalog)
            if op != "add" or not contains(quote, raw["place"]) or reference.state != "matched":
                raise ValueError("like needs a uniquely matched reference named in the quote")
            changes = tuple(str(SoftKey.parse(k)) for k in raw.get("but", ()))
            wish = LikeWish(place_id=reference.place_id, but=changes, quote=quote)
            after = state
            for key in changes:
                after = apply(after, Update(field="soft", op="add", value=(key, "love"),
                                           source="user" if how == "said" else "inferred",
                                           confidence="high" if how == "said" else "medium",
                                           evidence=Evidence(turn=evidence_turn, quote=quote)))
            wishes = after.wishes.model_copy(update={"like": tuple(w for w in after.wishes.like
                                                                   if w.place_id != wish.place_id) + (wish,)})
            return after.model_copy(update={"wishes": wishes}), ""
        except (ValueError, TypeError, KeyError) as error:
            return state, f"refused: {error}"
    if field == "companions":
        value = ontology().who(value)  # a vocabulary id, or a synonym of one, becomes the id; else the user's own words
        if value == "parents" and op != "remove" and re.search(r"\b(mẹ|bố|cha)\s+con\b", marked_quote):
            state = apply(state, Update(field="companions_other", op="add", value=quote,
                                       source="user" if how == "said" else "inferred",
                                       confidence="high" if how == "said" else "medium",
                                       evidence=Evidence(turn=evidence_turn, quote=quote)))
            return settle(state), "warning: the speaker's role is ambiguous; the companion words were kept"
        if value not in values.ENUM_VALUES["companions"]:
            # someone the vocabulary has no id for ("hàng xóm"): kept as said, never mapped to the nearest id
            if op != "remove" and not (contains(text, value) or contains(quote, value)):
                return state, f"refused: {value!r} is not in the user's message; copy the user's own words for who goes"
            state = apply(state, Update(field="companions_other", op="remove" if op == "remove" else "add", value=value,
                                        source="user" if how == "said" else "inferred",
                                        confidence="high" if how == "said" else "medium",
                                        evidence=Evidence(turn=evidence_turn, quote=quote)))
            return settle(state), ""
    if field == "companions" and op != "remove" and not names_group(quote, value):
        # Fail-closed: a group the user's own words do not name is never a guess. The agent keeps it as
        # unmapped and asks who comes; nothing is written from this call.
        return state, (f"refused: {value!r} is not one of companions [solo|partner|friends|kids|parents|baby|pet|coworkers] named "
                       f"by the user's words. Do NOT retry companions for this wish. Instead call record_fact "
                       f"exactly once with field=\"unmapped\", op=\"add\", value=\"<the user's own group words>\", "
                       f"quote=\"<the same words copied from the message>\", how=\"said\". Never put the word "
                       f"\"unmapped\" or a group name in the value of companions. If the message supports no wish "
                       f"at all, do not record companions: ask who comes")
    named = [c for c in compared or () if contains(quote, c["name"])] if field == "soft" and how == "inferred" else []
    if named:
        key = values.split_weight(value)[0].replace(" ", "")
        if key not in {f"{t['feature']}={t['value']}" for c in named for t in c["traits"]}:
            return state, f"refused: {value!r} is not a trait of {named[0]['name']!r}"
    # a taste read from a place the user compared to remembers that place: the ticket says "(giống X)"
    ev = Evidence(turn=evidence_turn, quote=quote, tool=f"place:{named[0]['id']}" if named else None)
    said = how == "said"
    op = op if field in LIST_FIELDS else ("remove" if op == "remove" else "set")
    warning = ""
    if field == "mobility":
        value = {"grab": "car", "taxi": "car", "walking": "walk"}.get(value.lower(), value)
    if field == "hard" and op != "remove" and requirement and requirement.get("ambiguity"):
        return state, "refused: clarify ambiguity before recording a mandatory requirement"
    try:
        if op == "remove":
            parsed = None if field in SCALARS or field.startswith("frame.") or field == "drive_day_min" else values.parse_remove(field, value)
        else:
            try:
                parsed = values.parse(field, value, catalog)
            except ValueError:
                if field not in values.ENUM_VALUES or not contains(text, quote):
                    raise
                state, _ = record_fact(state, "unmapped", "add", quote, quote, how, text, turn,
                                       catalog, replaces=field, history=history)
                return state, "warning: value outside the closed list; the user's words were kept"
        if (field == "hard" and op != "remove" and parsed.get("op") == "eq"
                and (f := ontology().features.get(parsed.get("feature"))) is not None and f.group == "experience"):
            # a hard limit filters every place: "must have a view / local food" would drop every cafe or waterfall
            return state, (f"refused: {parsed['feature']} is a taste, never a hard filter on every place. Record it "
                           f"as soft (love); a dish they must try is field dish, a place they must visit is anchor")
        if field not in ("hard", "soft"):  # only a hard or soft fact has a requirement; an extra object is ignored
            requirement = None
        intent = None
        if requirement is not None:
            try:
                intent = RequirementIntent.model_validate(requirement)
                if op != "remove":
                    if field == "soft":
                        key = parsed[0].split("@")[0]
                        fid, val = key.split("=")
                        Requirement(feature=fid, op="eq", value=val, strength="preference", **intent.model_dump())
                    elif field == "hard":
                        Requirement(**parsed, **intent.model_dump())
            except (ValueError, ValidationError):
                intent = None
                warning = "warning: invalid requirement metadata was dropped; the fact was kept"
        if field == "activity" and op != "remove" and not contains(quote, catalog.by_id[parsed["place_id"]].name):
            raise ValueError("the activity quote must name the selected place")
        if field == "time_preference" and parsed.get("place_id") and not contains(quote, catalog.by_id[parsed["place_id"]].name):
            raise ValueError("the time preference quote must name the selected place")
        if field in ("pace", "crowd_tolerance") and op != "remove":
            current = getattr(state, field)
            if current.known and current.value != parsed and any(e.turn == evidence_turn for e in current.evidence):
                state = state.model_copy(update={field: type(current)(evidence=current.evidence), "meta": state.meta.model_copy(
                    update={"conflicts": tuple(dict.fromkeys((*state.meta.conflicts, field)))})})
                return settle(state), "warning: conflicting values in the same message; ask the user to choose"
            if field in state.meta.conflicts and any(e.turn == evidence_turn for e in current.evidence):
                return state, "warning: this field needs clarification"
            state = state.model_copy(update={"meta": state.meta.model_copy(
                update={"conflicts": tuple(f for f in state.meta.conflicts if f != field)})})
        state = apply(state, Update(field=field, op=op, value=parsed, source="user" if said else "inferred",
                                    confidence="high" if said else "medium", evidence=ev, requirement=intent))
        if field == "soft" and op != "remove" and parsed[1] == "love":
            # a feature's values exclude each other: loving "quiet" now drops the "loud" loved before. Only what the
            # user says replaces their own words; an inference replaces only other inferences or defaults
            from .state import SoftKey
            new = SoftKey.parse(parsed[0])
            stale = [k for k, f in state.soft.items() if k != parsed[0] and f.value == "love"
                     and (said or f.source != "user")
                     and (old := SoftKey.parse(k)).feature == new.feature and old.context == new.context]
            if stale:
                state = state.model_copy(update={"soft": {k: f for k, f in state.soft.items() if k not in stale}})
    except (ValueError, ValidationError) as e:
        hint = " (soft: feature=value:love|avoid with ids from FEATURES; if none fits, use field unmapped)" \
            if field in ("soft", "hard") else ""
        return state, f"refused: {value!r} is not a valid {field}: {str(e).splitlines()[0]}{hint}"
    if field == "mobility" and op != "remove" and parsed == "car" and re.search(
            r"\b(grab|taxi|tai xe|chauffeur|tu lai|self.driv)\b", fold(quote)):
        hired = bool(re.search(r"\b(grab|taxi|tai xe|chauffeur)\b", fold(quote)))
        state = apply(state, Update(field="driver", op="set", value="hired" if hired else "self",
                                   source="user" if said else "inferred", confidence="high" if said else "medium", evidence=ev))
    return settle(state), warning


# a question about how strict a body or food limit is ("bà đi bộ được bao xa?", "tránh cả dầu lạc không?")
CARE_ASK = re.compile(CARE_NOTE.pattern[:-3] + r"|di bo|bac thang|leo|duong doc|lan cheo|tiep xuc cheo|an trung|trung sua|sua bo)\b")


def asks_settled_care(say: str) -> bool:
    """The reply's question is about a care limit (to be used once Lưu ý is answered: then it is a re-ask)."""
    return any(x.rstrip().endswith("?") and CARE_ASK.search(fold(x)) for x in re.split(r"(?<=[.!?…])\s+", say))


def same_question(say: str, before: str) -> bool:
    """The question of `say` is the question of the reply `before`, asked again (the same words, give or take)."""
    def question(x: str) -> str:
        return next((fold(s) for s in reversed(re.split(r"(?<=[.!?…])\s+", x.strip())) if s.rstrip().endswith("?")), "")
    a, b = question(say), question(before)
    return bool(a and b) and SequenceMatcher(None, a, b).ratio() >= 0.6


def drop_questions(say: str) -> str:
    """The sentences of `say` that are not questions."""
    return " ".join(x for x in re.split(r"(?<=[.!?…])\s+", say) if not x.rstrip().endswith("?")).strip()


def state_text(state: TripState) -> str:
    """The known values of the trip (date, days, nights, ...) as text: numbers the reply may repeat."""
    return " ".join(str(values.jsonable(f.value)) for f in (state.start_date, state.month, state.days, state.nights, state.people)
                    if f.known)


def bad_say(say: str, heard: str, state: TripState, catalog: Catalog, compared: set[str],
            reply_language: str | None = None, told: str = "") -> str | None:
    """Why `say` may not be shown: a number the user never said, or a place the user never named.
    told: what the tools told the agent this turn (a refusal's limits, "out of range (1, 20)"): its numbers may be said."""
    if say.strip() and language(say) != (reply_language or language(heard)):
        return "reply is in the wrong language"
    internal = {f for f in SCALARS if "_" in f} | {"signal", "companions_other", "drive_day_min"}
    if any(re.search(r"(?<!\w)" + re.escape(f) + r"(?!\w)", say, re.I) for f in internal):
        return "contains internal field identifiers"
    said = {int(n) for n in re.findall(r"\d+", f"{heard} {state_text(state)} {told}")}  # the user's, the trip's, the tools'

    extra = [n for n in re.findall(r"\d+", say) if int(n) not in said]
    if extra:
        return f"numbers {extra} the user did not say"
    named = {a.place_id for a in state.anchors if a.place_id} | compared  # the user named these
    s, words = f" {squash(say)} ", f" {squash(heard)} "  # a name the user said may be said back ("gần chợ Đà Lạt")
    for key, pid in catalog.name_keys:
        if pid not in named and not set(key.split()) <= GENERIC and f" {key} " in s and f" {key} " not in words:
            return f"names place {pid}"
    return None


def prune_say(say: str, bad) -> str:
    """`say` without the sentences `bad` refuses (bad(sentence) -> reason or None): one invented figure costs its
    sentence, not the whole reply."""
    return " ".join(x for x in re.split(r"(?<=[.!?…])\s+", say.strip()) if x and bad(x) is None).strip()


def _clause(text: str, room: int) -> str:
    """`text` cut to at most `room` characters at a clause boundary (", ", "; ", ": "), never inside a clause;
    "" when no boundary leaves a useful part."""
    if len(text) <= room:
        return text
    head = text[:room]
    cut = max(head.rfind(", "), head.rfind("; "), head.rfind(": "))
    return head[:cut].rstrip(" ,;:") if cut >= room // 3 else ""


def trim_say(say: str) -> str:
    """Keep at most two sentences and 250 characters, reserving room for the final question. Text is cut only at a
    sentence or clause boundary, so a reply never ends mid-phrase ("uống cà phê và."). The chat shows plain text, so
    markdown emphasis (**x**, __x__) is dropped."""
    text = re.sub(r"\*\*|__", "", say).strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", text) if s.strip()]
    if not sentences:
        return ""
    question = next((s for s in reversed(sentences) if s.endswith("?")), None)
    selected = ([next((s for s in sentences if not s.endswith("?")), ""), question] if question else sentences[:2])
    selected = [s for s in selected if s]
    if len(" ".join(selected)) <= 250:
        return " ".join(selected)
    if question:
        if len(question) >= 250:
            part = _clause(question, 248)
            return (part or question[:248].rsplit(" ", 1)[0]).rstrip(" .!?…") + "?"
        lead = selected[0] if len(selected) > 1 else ""
        lead = _clause(lead.rstrip(" .!?…"), 250 - len(question) - 2)
        return (lead + ". " if lead else "") + question
    first = selected[0]
    if len(first) <= 250:
        return first
    part = _clause(first.rstrip(" .!?…"), 249)
    return (part or first[:249].rsplit(" ", 1)[0].rstrip(" .!?…")) + "."
