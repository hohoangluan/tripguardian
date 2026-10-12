"""Companions beyond the first five: baby, pet, coworkers, and anyone else (docs/TRIP_UNDERSTANDING.md)."""

from datetime import date

import pytest
from trip_fixtures import rec  # noqa: F401 -- keeps conftest fixtures importable alongside

from trip.domain.compile import compile_search_input
from trip.domain.guard import record_fact
from trip.domain.prepass import prepass
from trip.domain.questions import apply_chip, care_q, companions_q
from trip.domain.state import Evidence, TripState, Update, apply, settle

TODAY = date(2026, 10, 2)


def up(s, field, value=None, op="set"):
    return apply(s, Update(field=field, op=op, value=value, source="user", confidence="high",
                           evidence=Evidence(turn=1, quote="x")))


def hards(state):
    return {(h.feature, h.op, h.value) for h in state.hard}


def pick(chip, question=None, state=None):
    return apply_chip(state or TripState(), question or companions_q(), (chip,), 1)


def test_the_new_companions_are_chips_with_their_own_limit():
    baby = pick("who:baby")
    assert baby.companions.value == frozenset({"baby"}) and hards(baby) == {("fit.baby", "ne", "bad")}
    pet = pick("who:pet")
    assert pet.companions.value == frozenset({"pet"}) and hards(pet) == {("pets", "ne", "not_allowed")}
    work = pick("who:coworkers")
    assert work.companions.value == frozenset({"coworkers"}) and hards(work) == set()
    assert ("fit.parents", "ne", "bad") in hards(pick("who:parents"))
    assert hards(pick("who:friends")) == set()


def test_care_chips_protect_a_pregnant_or_wheelchair_member():
    assert ("fit.pregnant", "ne", "bad") in hards(pick("pregnant", care_q()))
    assert ("fit.wheelchair", "ne", "bad") in hards(pick("wheelchair", care_q()))


def test_the_search_input_carries_them():
    s = settle(pick("who:baby", state=pick("who:pet")))
    si = compile_search_input(s)
    assert si.context.companions == ("baby", "pet")
    assert {(h.feature, h.op, h.value) for h in si.hard_filters} == {("fit.baby", "ne", "bad"), ("pets", "ne", "not_allowed")}
    assert si.context.companions_other == ()


def test_a_big_party_in_its_own_car_needs_a_place_a_coach_reaches():
    s = up(up(TripState(), "mobility", "car"), "people", 10)
    assert ("coach_access", "ne", "no") in {(h.feature, h.op, h.value) for h in compile_search_input(s).hard_filters}
    few = up(up(TripState(), "mobility", "car"), "people", 4)
    assert not [h for h in compile_search_input(few).hard_filters if h.feature == "coach_access"]
    bike = up(up(TripState(), "mobility", "motorbike"), "people", 10)
    assert not [h for h in compile_search_input(bike).hard_filters if h.feature == "coach_access"]
    only = compile_search_input(s).hard_filters
    assert next(h for h in only if h.feature == "coach_access").unknown_policy == "exclude"


def suggested(text):
    return {(p.field, p.value) for p in prepass(text, TODAY).suggestions}


def test_prepass_suggests_the_new_companions():
    assert ("companions", "pet") in suggested("đi với con chó nhà mình")
    assert ("companions", "pet") in suggested("có mang thú cưng theo")
    assert ("companions", "baby") in suggested("có em bé sơ sinh nên cần xe đẩy")
    assert ("companions", "coworkers") in suggested("đi team building với đồng nghiệp")
    assert ("companions", "friends") not in suggested("đi team building với đồng nghiệp")
    assert ("companions", "pet") not in suggested("không mang thú cưng")  # negated


def test_a_companion_the_vocabulary_has_no_id_for_is_kept_as_the_user_said_it(catalog):
    text = "đi với hàng xóm"
    st, note = record_fact(TripState(), "companions", "add", "hàng xóm", "hàng xóm", "said", text, 1, catalog)
    assert note == "" and st.companions_other == ("hàng xóm",) and not st.companions.known
    st, _ = record_fact(st, "companions", "add", "friends", "bạn", "said", "đi với hàng xóm và bạn bè", 2, catalog)
    assert st.companions.value == frozenset({"friends"}) and st.companions_other == ("hàng xóm",)
    assert compile_search_input(settle(st)).context.companions_other == ("hàng xóm",)
    again, _ = record_fact(st, "companions", "add", "hàng xóm", "hàng xóm", "said", text, 3, catalog)
    assert again.companions_other == ("hàng xóm",)  # said twice, kept once


def test_other_companion_needs_the_users_own_words(catalog):
    st, note = record_fact(TripState(), "companions", "add", "hàng xóm", "hàng xóm", "said", "đi một mình", 1, catalog)
    assert note.startswith("refused") and not st.companions_other


def test_a_vocabulary_synonym_is_mapped_to_its_id(catalog):
    st, note = record_fact(TripState(), "companions", "add", "chó", "con chó", "said", "đi với con chó", 1, catalog)
    assert note == "" and st.companions.value == frozenset({"pet"}) and st.companions_other == ()


@pytest.mark.parametrize("value", ["baby", "pet", "coworkers"])
def test_the_values_are_valid_companions(catalog, value):
    from trip.domain import values
    assert values.parse("companions", value, catalog) == value
