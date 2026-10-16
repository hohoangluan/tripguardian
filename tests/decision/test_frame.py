import numpy as np
import pytest

from fixtures import feat, fit_entry, hard, love, si, srec
from gen import records, sessions

from corpus.snapshot import Region
from decision.fit import centers, fit
from decision.frame import fit_table, roles, score_table, screen_table, table
from decision.rank import score
from decision.model import Cand
from decision.screen import screen
from decision.session import Session, State
from decision.settings import default
from decision.trip_days import trip_days
from requirements import applicable, scope_allows

CFG = default()


def reference_screen(s, recs, region=None):
    si_ = s.search_input.model_copy(update={"activities": {**s.search_input.activities, **s.state.activities}})
    days = trip_days(si_.context, CFG)
    relaxed = {tuple(x) for x in s.state.relaxed}
    region = region or Region.from_records(recs)
    keep = set(s.state.selected)
    role, act = roles(region, si_.activities, keep)
    got = screen_table(region, si_, days, relaxed, role, act)
    for i, r in enumerate(recs):
        if role[i] is None:
            continue
        c = Cand(r, role[i], keep=r["id"] in keep)
        screen(c, si_, days, relaxed)
        fails = {x["reason"] for x in c.checks if x["result"] == "fail"}
        assert got.status[i] == c.status, (s.id, r["id"])
        assert {k for k, v in got.fails.items() if v[i] > 0} == fails, (s.id, r["id"])


@pytest.mark.parametrize("seed", range(10))
def test_screen_table_matches_screen(seed):
    recs = records(seed)
    region = Region.from_records(recs)
    for s in sessions(seed, recs, 20):
        reference_screen(s, recs, region)


def test_scope_allows_is_the_scope_part_of_applicable():
    r = srec("A", group="restaurant", usable=("meal",))
    for fid in ("vegetarian_options", "drink_quality", "steep_or_stairs", "scenic_view", "fit.kids"):
        for scope in (None, "eating", "drinking", "all"):
            req = {"feature": fid, "scope": scope}
            assert applicable(r, req) == scope_allows(req, "eating")


def test_screen_special_and_fit_filters():
    recs = [srec("C", group="cafe"), srec("R", group="restaurant", usable=("meal",)),
            srec("W", group="bar", features={"alcohol_required": feat("yes"), "wine_tasting_available": feat("present")}),
            srec("K", details={"fit": {"kids": fit_entry("bad")}})]
    for h in (hard("venue_category", "bar"), hard("venue_category", "bar", op="eq"), hard("activity", "alcohol_consumption"),
              hard("wine_tasting_available", "present", op="eq"), hard("fit.kids", "bad")):
        reference_screen(Session(id="0" * 12, search_input=si(hard_filters=[h]), state=State()), recs)


def test_duplicate_filters_count_each_failed_check():
    recs = [srec("S", features={"steep_or_stairs": feat("present")})]
    s = Session(id="0" * 12, search_input=si(hard_filters=[hard("steep_or_stairs", "present"),
                                                           hard("steep_or_stairs", "present", policy="flag")]),
                state=State())
    region = Region.from_records(recs)
    role, act = roles(region, {}, set())
    got = screen_table(region, s.search_input, trip_days(s.search_input.context, CFG), set(), role, act)
    assert int(got.fails["hard:steep_or_stairs"][0]) == 2


def reference_numbers(s, recs, region=None):
    si_ = s.search_input.model_copy(update={"activities": {**s.search_input.activities, **s.state.activities}})
    days = trip_days(si_.context, CFG)
    relaxed = {tuple(x) for x in s.state.relaxed}
    region = region or Region.from_records(recs)
    keep = set(s.state.selected)
    role, act = roles(region, si_.activities, keep)
    scr = screen_table(region, si_, days, relaxed, role, act)  # noqa: F841
    by_id = {r["id"]: r for r in recs}
    ctrs = centers(si_, by_id, CFG)
    anchors = [a.place_id for a in si_.anchors if a.place_id in by_id]
    anchor_areas = {a for pid in anchors if (a := by_id[pid]["identity"].get("area"))}
    cands = []
    for i, r in enumerate(recs):
        if role[i] is None:
            continue
        c = Cand(r, role[i], keep=r["id"] in keep)
        screen(c, si_, days, relaxed)
        cands.append(c)
    live = [c for c in cands if c.status != "excluded" or c.keep]
    for c in live:
        fit(c, si_, days, ctrs, anchor_areas, s.state.profile, CFG)
    score(live, si_, s.state.profile, CFG)
    live_ids = {c.id for c in live}
    live_mask = np.array([pid in live_ids for pid in region.ids])
    got_fit = fit_table(region, si_, days, ctrs, anchor_areas, s.state.profile, CFG)
    got_score, _ = score_table(region, si_, s.state.profile, CFG, got_fit, live_mask, role, act,
                               overrides=si_.activities)
    for c in live:
        i = region.index[c.id]
        assert got_fit[i] == c.fit, (s.id, c.id, "fit")
        assert got_score[i] == c.score, (s.id, c.id, "score")


@pytest.mark.parametrize("seed", range(10))
def test_fit_and_score_tables_match(seed):
    recs = records(seed)
    region = Region.from_records(recs)
    for s in sessions(seed, recs, 20):
        reference_numbers(s, recs, region)


def test_score_with_given_voices_equals_score_over_the_list():
    recs = records(2)
    s = sessions(2, recs, 1)[0]
    cands = [Cand(r, "experience") for r in recs[:10]]
    for c in cands:
        c.fit = 0.5
    score(cands, s.search_input, s.state.profile, CFG)
    whole = {c.id: c.score for c in cands}
    voices = sorted(c.rec["provenance"].get("voices") or 0 for c in cands)
    for c in cands:
        one = Cand(c.rec, "experience")
        one.fit = 0.5
        score([one], s.search_input, s.state.profile, CFG, voices=voices)
        assert one.score == whole[c.id]


def test_score_table_two_context_keys_first_with_data_wins_and_special_want():
    a = srec("A", features={"scenic_view": feat("present", by_context={"time_of_day=morning": {"absent": 2},
                                                                        "day_type=weekend": {"present": 2}})})
    b = srec("B", features={"scenic_view": feat("present", by_context={"day_type=weekend": {"absent": 3}}),
                            "wine_tasting_available": feat("present")}, group="bar")
    c = srec("C", features={"scenic_view": feat("present")})
    recs = [a, b, c]
    for ws in ([love("scenic_view", "present", context={"time_of_day": "morning", "day_type": "weekend"})],
               [love("scenic_view", "present", context={"day_type": "weekend", "time_of_day": "morning"})],
               [love("scenic_view", "present"), love("wine_tasting_available", "present", weight=-1)]):
        s = Session(id="0" * 12, search_input=si(soft_weights=ws), state=State())
        reference_numbers(s, recs)


def _table_inputs(s, recs):
    si_ = s.search_input.model_copy(update={"activities": {**s.search_input.activities, **s.state.activities}})
    days = trip_days(si_.context, CFG)
    relaxed = {tuple(x) for x in s.state.relaxed}
    ctrs = centers(si_, {r["id"]: r for r in recs}, CFG)
    return si_, days, relaxed, ctrs, set(s.state.selected)


def test_memo_reuses_tiers_and_never_changes_numbers():
    recs = records(7)
    region = Region.from_records(recs)
    for s in sessions(7, recs, 10):
        si_, days, relaxed, ctrs, keep = _table_inputs(s, recs)
        memo = {}
        a = table(region, si_, s.state.profile, days, relaxed, ctrs, [], keep, 0, CFG, memo)
        b = table(region, si_, s.state.profile, days, relaxed, ctrs, [], keep, 0, CFG, memo)
        c = table(region, si_, s.state.profile, days, relaxed, ctrs, [], keep, 0, CFG, None)
        assert a.score == b.score == c.score and a.fit == c.fit and a.status == c.status
        assert set(memo) == {"screen", "fit", "wishes", "score"}


def test_memo_recomputes_only_the_tier_whose_input_changed():
    recs = records(7)
    region = Region.from_records(recs)
    s = sessions(7, recs, 1)[0]
    si_, days, relaxed, ctrs, keep = _table_inputs(s, recs)
    memo = {}
    table(region, si_, s.state.profile, days, relaxed, ctrs, [], keep, 0, CFG, memo)
    screen_hit, fit_hit, score_hit = memo["screen"], memo["fit"], memo["score"]
    dumped = si_.model_dump(mode="json")
    more = type(si_).model_validate({**dumped, "soft_weights": [*dumped["soft_weights"], love("scenic_view", "present")]})
    b = table(region, more, s.state.profile, days, relaxed, ctrs, [], keep, 0, CFG, memo)
    assert memo["screen"] is screen_hit and memo["fit"] is fit_hit and memo["score"] is not score_hit
    assert b.score == table(region, more, s.state.profile, days, relaxed, ctrs, [], keep, 0, CFG, None).score
    other = next(r["id"] for r in recs if r["usable_as"] and r["id"] not in keep)
    kept = set(keep) | {other}  # selecting a place with a role changes `keep`, not the screen or the fit
    c = table(region, more, s.state.profile, days, relaxed, ctrs, [], kept, 0, CFG, memo)
    assert memo["screen"] is screen_hit and memo["fit"] is fit_hit
    assert c.score == table(region, more, s.state.profile, days, relaxed, ctrs, [], kept, 0, CFG, None).score
