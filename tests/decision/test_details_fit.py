"""Place details in Place Decision: hard filters on a companion / pets / coach, soft fit, cards, compare, cost."""

import pytest
from fixtures import fit_entry, hard, si, srec
from requirements import hard_result

from decision.cards import card
from decision.compare import compare
from decision.feasibility import _cost_vnd
from decision.fit import centers, fit
from decision.model import Cand
from decision.settings import default
from decision.trip_days import trip_days
from types import SimpleNamespace

CFG = default()
P = SimpleNamespace(travel_mult=1.0, crowd_tolerance=None)
BABY_NOT_BAD = {"feature": "fit.baby", "op": "ne", "value": "bad"}


def with_fit(**fits):
    return srec("A", details={"fit": fits})


def test_fit_filter_fails_on_a_verified_bad_passes_on_a_verified_good_and_is_unknown_without_data():
    assert hard_result(with_fit(baby=fit_entry("bad")), BABY_NOT_BAD) == ("fail", None)
    assert hard_result(with_fit(baby=fit_entry("good")), BABY_NOT_BAD) == ("pass", None)
    assert hard_result(srec("A"), BABY_NOT_BAD) == ("unknown", None)
    assert hard_result(srec("A", details={"fit": {}}), BABY_NOT_BAD) == ("unknown", None)
    assert hard_result(with_fit(pet=fit_entry("bad")), BABY_NOT_BAD) == ("unknown", None)


def test_fit_filter_never_passes_on_an_unverified_value_or_a_disputed_one():
    assert hard_result(with_fit(baby=fit_entry("good", status="UNCERTAIN")), BABY_NOT_BAD) == ("unknown", None)
    disputed = {**fit_entry("good", n=3), "distribution": {"good": 2, "bad": 1}}
    assert hard_result(with_fit(baby=disputed), BABY_NOT_BAD) == ("unknown", None)
    assert hard_result(with_fit(baby=fit_entry("bad", status="UNCERTAIN")), BABY_NOT_BAD) == ("unknown", None)


def test_pets_and_coach_access_filters_run_like_any_feature():
    no_pets = {"feature": "pets", "op": "ne", "value": "not_allowed"}
    assert hard_result(srec("A", features={"pets": "not_allowed"}), no_pets)[0] == "fail"
    assert hard_result(srec("A", features={"pets": "allowed"}), no_pets)[0] == "pass"
    coach = {"feature": "coach_access", "op": "ne", "value": "no"}
    assert hard_result(srec("A", features={"coach_access": "no"}), coach)[0] == "fail"
    assert hard_result(srec("A"), coach)[0] == "unknown"


def test_search_input_accepts_the_new_filters_and_companions():
    s = si(context={"companions": ["baby", "pet", "coworkers"]},
           hard_filters=[hard("fit.baby", "bad"), hard("pets", "not_allowed"), hard("coach_access", "no")])
    assert s.context.companions == ("baby", "pet", "coworkers")
    with pytest.raises(ValueError):
        si(hard_filters=[hard("fit.nobody", "bad")])
    with pytest.raises(ValueError):
        si(hard_filters=[hard("fit.baby", "terrible")])


def run(c, s):
    fit(c, s, trip_days(s.context, CFG), centers(s, {c.id: c.rec}, CFG), set(), P, CFG)
    return c


FAR = dict(lat=12.0)  # a place at a distance: its fit is below 1, so a bonus shows


def test_soft_fit_rewards_what_the_trips_companions_need():
    kids = si(context={"companions": ["kids"]})
    plain = run(Cand(srec("P", **FAR), "experience"), kids)
    play = run(Cand(srec("Q", **FAR, features={"kids_play_area": "present"}), "experience"), kids)
    assert play.fit - plain.fit == pytest.approx(CFG.details_fit["feature_bonus"])
    assert run(Cand(srec("Q", **FAR, features={"kids_play_area": "present"}), "experience"), si()).fit == plain.fit  # nobody asked
    old = run(Cand(srec("R", **FAR, features={"rest_benches": "present", "toilet_available": "yes"}), "experience"),
              si(context={"companions": ["parents"]}))
    assert round(old.fit - plain.fit, 4) == round(2 * CFG.details_fit["feature_bonus"], 4)


def test_soft_fit_follows_a_verified_verdict_and_says_why():
    s = si(context={"companions": ["friends"]})
    base = run(Cand(srec("P", **FAR), "experience"), s)
    bad = run(Cand(srec("B", **FAR, details={"fit": {"friends": fit_entry("bad", reasons=["quán nhỏ, chật"])}}),
                   "experience"), s)
    good = run(Cand(srec("G", **FAR, details={"fit": {"friends": fit_entry("good")}}), "experience"), s)
    assert round(bad.fit - base.fit, 4) == -CFG.details_fit["bad_penalty"]
    assert round(good.fit - base.fit, 4) == CFG.details_fit["good_bonus"]
    [flag] = [f for f in bad.flags if f["code"] == "fit_bad"]
    assert "bạn bè" in flag["text"] and "quán nhỏ, chật" in flag["text"]
    unsure = run(Cand(srec("U", **FAR, details={"fit": {"friends": fit_entry("bad", status="UNCERTAIN")}}),
                      "experience"), s)
    assert unsure.fit == base.fit and not [f for f in unsure.flags if f["code"] == "fit_bad"]


def test_a_filter_on_pregnancy_and_a_big_party_count_as_companions_of_the_trip():
    s = si(hard_filters=[hard("fit.pregnant", "bad")])
    bad = run(Cand(srec("B", **FAR, details={"fit": {"pregnant": fit_entry("bad")}}), "experience"), s)
    assert round(bad.fit - run(Cand(srec("P", **FAR), "experience"), s).fit, 4) == -CFG.details_fit["bad_penalty"]
    party = si(context={"people": CFG.coach_min_people})
    good = run(Cand(srec("G", **FAR, details={"fit": {"large_group": fit_entry("good")}}), "experience"), party)
    assert good.fit > run(Cand(srec("P", **FAR), "experience"), party).fit
    small = si(context={"people": CFG.coach_min_people - 1})
    assert run(Cand(srec("G", **FAR, details={"fit": {"large_group": fit_entry("good")}}), "experience"), small).fit == \
        run(Cand(srec("P", **FAR), "experience"), small).fit


DETAILS = {"known_for": {"headline": {"text": "xích đu nhìn hồ", "n": 3, "status": "VERIFIED", "reason": None,
                                      "evidence": []}, "more": []},
           "cost": {"entry": {}, "parking": None, "extras": [], "per_party": [],
                    "total_vnd": {"base": 60000, "with_extras": 100000}, "kind": "estimate"}}


def test_card_and_compare_show_what_the_place_is_known_for_and_what_it_costs():
    a = Cand(srec("A", details=DETAILS), "experience")
    plain = Cand(srec("B"), "experience")
    got = card(a, si(), CFG)
    assert got["known_for"] == {"text": "xích đu nhìn hồ", "n": 3} and got["cost"] == {"base": 60000, "with_extras": 100000}
    assert card(plain, si(), CFG)["known_for"] is None and card(plain, si(), CFG)["cost"] is None
    cheap = {"cost": {**DETAILS["cost"], "total_vnd": {"base": 20000, "with_extras": 20000}}}  # no known_for
    b = Cand(srec("C", details=cheap), "experience")
    out = compare(a, b, [], trip_days(si().context, CFG), CFG)
    known = next(r for r in out["rows"] if r["aspect"] == "known_for")
    assert known["a"] == "xích đu nhìn hồ (3 người)" and known["b"] == "chưa biết" and known["better"] == "unknown"
    cost = next(r for r in out["sacrifice"] if r["aspect"] == "cost")
    assert (cost["a"], cost["b"], cost["better"]) == ("60k", "20k", "b")
    assert not [r for r in compare(plain, plain, [], trip_days(si().context, CFG), CFG)["sacrifice"] if r["aspect"] == "cost"]


def test_feasibility_cost_uses_the_total_when_there_is_one():
    entry = {"typical_vnd": 50000}
    assert _cost_vnd(Cand(srec("A", entry_fee=entry), "experience")) == 50000  # no details: the old formula
    assert _cost_vnd(Cand(srec("A", entry_fee=entry, details=DETAILS), "experience")) == 60000
    priced = srec("B", price={"min_vnd": 100000, "max_vnd": 200000}, details=DETAILS)
    assert _cost_vnd(Cand(priced, "meal")) == 150000 + 60000
