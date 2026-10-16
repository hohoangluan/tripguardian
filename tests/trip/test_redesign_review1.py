"""Review round 1 of the Trip redesign (parts 1-2): defects found in sol's code, each pinned by a test.

R1 folded short words name the wrong person ("bố" = father read as "bồ" = partner).
R2 a care tap left the signal open: the gate asked tab ④ forever.
R3 a deck answer that cannot be used is dropped without telling the user.
R4 a free day / busy block reached Decision and Planning as an ordinary full day.
"""

from datetime import date
from pathlib import Path

import pytest
from trip_fixtures import ScriptedChat, say

from trip import Catalog, TripState, compile_search_input
from trip.agent import AgentError
from trip.api.engine import Engine, TurnInput
from trip.domain import readiness
from trip.domain.guard import record_fact
from trip.infrastructure.sessions import SessionStore

TODAY = date(2026, 10, 15)


def keys(st):
    return [k for k, _ in readiness.missing(st)]


# ---------- R1: diacritics carry meaning; a guard that folds them away accepts the wrong person ----------

@pytest.mark.parametrize("text, quote, value", [
    ("đi với bố", "bố", "partner"),            # father, not "bồ"
    ("đi với bố mẹ", "bố mẹ", "partner"),
    ("thích ăn bò nướng", "bò", "partner"),    # beef
    ("mang kem chống nắng", "chống", "partner"),  # sunscreen, not "chồng"
    ("vô Đà Lạt chơi", "vô", "partner"),       # "go in", not "vợ"
    ("đi võ đường", "võ", "partner"),
    ("mình là sinh viên, đi một mình", "sinh viên", "friends"),  # a student travelling alone
    ("bể bơi 2 tầng", "bể 2", "kids"),          # a pool, not "bé 2 tuổi"
])
def test_r1_a_word_that_only_looks_like_a_group_without_its_marks_is_refused(catalog, text, quote, value):
    st, note = record_fact(TripState(), "companions", "add", value, quote, "said", text, 1, catalog)
    assert not st.companions.known and note.startswith("refused")


@pytest.mark.parametrize("text, quote, value", [
    ("di voi bo 3 ngay", "bo", "partner"),  # typed without marks: ambiguous, never written as said
])
def test_r1_an_unmarked_short_word_is_not_enough_evidence_on_its_own(catalog, text, quote, value):
    st, _ = record_fact(TripState(), "companions", "add", value, quote, "said", text, 1, catalog)
    assert not (st.companions.known and st.companions.source == "user")


def test_r1_the_whole_message_cannot_vouch_for_a_quote_that_names_nobody(catalog):
    # the quote must name the group itself; "bồ" elsewhere in the message does not make "bạn" a partner
    st, _ = record_fact(TripState(), "companions", "add", "partner", "bạn", "said", "đi với bạn, bồ mình ở nhà", 1, catalog)
    assert not st.companions.known


# ---------- R2-R3: deck taps through the real engine ----------

@pytest.fixture
def engine(catalog, cfg, tmp_path):
    chat = ScriptedChat(error=AgentError("a tap must not call the model"))
    return Engine(catalog, cfg, SessionStore(Path(tmp_path)), chat, today=lambda: TODAY), chat


def tap(e, sid, answers):
    events = []
    e.turn(sid, TurnInput(kind="deck", answers=answers), lambda ev, d: events.append((ev, d)))
    return events


def deck_issues(events):
    return {(i["key"], i["code"]) for ev, d in events if ev == "deck_issues" for i in d["issues"]}


@pytest.mark.parametrize("chip, hard", [
    ("steps", {"steep_or_stairs", "long_walk"}),
    ("wheelchair", {"steep_or_stairs", "long_walk"}),
    ("vegetarian", {"vegetarian_options"}),
    ("vegan", {"vegan_options"}),
])
def test_r2_a_care_tap_closes_tab_four_with_a_real_limit(engine, chip, hard):
    e, chat = engine
    sid = e.create("first", "nothing")["id"]
    e.chat = chat = ScriptedChat(say("Rõ rồi."))
    tap(e, sid, {"care": [chip]})
    st = e.store.get(sid).state
    assert "care" not in keys(st) and chat.calls == 1  # Code writes the limit before the agent reacts.
    assert hard <= {h.feature for h in st.hard}
    compile_search_input(st)  # no open signal left: compiles


@pytest.mark.parametrize("chip", ["motion_sick", "height"])
def test_r2_a_care_tap_with_no_data_is_kept_for_the_user_to_check(engine, chip):
    e, _ = engine
    sid = e.create("first", "nothing")["id"]
    tap(e, sid, {"care": [chip]})
    st = e.store.get(sid).state
    assert "care" not in keys(st) and st.unmapped  # the wish is kept (🔎 line), not silently dropped


def test_r2_nothing_to_avoid_closes_a_guessed_hint(engine):
    e, _ = engine
    sid = e.create("first", "nothing")["id"]
    s = e.store.get(sid)
    s.state = s.state.model_copy(update={"signals": TripState.model_validate(
        {"signals": [{"kind": "elderly", "quote": "bố mẹ", "turn": 1, "from_companion": "parents"}]}).signals})
    e.store.save(s)
    tap(e, sid, {"care": ["none"]})
    assert "care" not in keys(e.store.get(sid).state)


def test_r2_nothing_to_avoid_does_not_erase_a_limit_the_user_said(engine):
    # "bà đau gối" was said; tapping "Không có gì" is a contradiction, not a release of a safety hint
    e, _ = engine
    sid = e.create("first", "nothing")["id"]
    s = e.store.get(sid)
    s.state = s.state.model_copy(update={"signals": TripState.model_validate(
        {"signals": [{"kind": "knee", "quote": "bà đau gối", "turn": 1}]}).signals})
    e.store.save(s)
    events = tap(e, sid, {"care": ["none"]})
    st = e.store.get(sid).state
    # 2026-10-16: the said knee now writes its limit at once (derive), so care is answered; "none" still never erases it
    assert ("care", "contradicts_said") in deck_issues(events)
    assert {h.feature for h in st.hard} >= {"steep_or_stairs", "long_walk"}


@pytest.mark.parametrize("answers, issue", [
    ({"trip.dates": "2026-10-01..2026-10-03"}, ("trip.dates", "past_date")),
    ({"trip.dates": "2026-11-20..2026-11-18"}, ("trip.dates", "end_before_start")),
    ({"trip.dates": "2026-11-01..2026-12-15"}, ("trip.dates", "too_long")),
])
def test_r3_an_unusable_date_is_reported_never_dropped_silently(engine, answers, issue):
    e, _ = engine
    sid = e.create("first", "nothing")["id"]
    events = tap(e, sid, answers)
    assert issue in deck_issues(events) and not e.store.get(sid).state.start_date.known


def test_r3_hours_ending_before_they_start_are_reported(engine):
    e, _ = engine
    sid = e.create("first", "nothing")["id"]
    events = tap(e, sid, {"trip.dates": "2026-11-20..2026-11-20", "trip.start": "15:00", "trip.end": "10:00"})
    assert ("trip.end", "end_before_start") in deck_issues(events)


def test_r3_fewer_people_than_the_groups_named_is_written_but_reported(engine):
    e, _ = engine
    sid = e.create("first", "nothing")["id"]
    events = tap(e, sid, {"companions.who": ["partner", "kids"], "companions.people": "2"})
    st = e.store.get(sid).state
    assert ("companions.people", "people_below_groups") in deck_issues(events)
    assert st.people.value == 2  # informed, not blocked: the user decides


def test_r3_a_value_outside_the_tab_is_reported(engine):
    e, _ = engine
    sid = e.create("first", "nothing")["id"]
    events = tap(e, sid, {"mobility": ["helicopter"]})
    assert ("mobility", "invalid") in deck_issues(events)


# ---------- R4: a free day and busy blocks reach the consumers ----------

def _si(frame):
    def said(v):
        return {"value": v, "source": "user", "confidence": "high", "status": "confirmed",
                "evidence": [{"turn": 1, "quote": "q"}]}
    return compile_search_input(TripState.model_validate(
        {"start_date": said("2026-11-20"), "days": said(3), "checkin_at": said("08:00"), "frame": frame}))


def test_r4_decision_sees_a_rest_day_as_no_time_and_busy_as_taken():
    from decision.settings import default
    from decision.trip_days import trip_days
    si = _si({"days": [{"index": 2, "intensity": "free", "source": "user", "evidence": [{"turn": 1, "quote": "q"}]}],
              "busy": [{"label": "nghỉ trưa", "kind": "rest", "where": "lodging", "start": "12:00", "end": "14:00",
                        "on": "all"}]})
    days = trip_days(si.context, default())
    assert days[2].end - days[2].start == 0
    assert days[1].busy == ((12 * 60, 14 * 60),)
