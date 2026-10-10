from datetime import date

import pytest

from trip.domain.compile import UnhandledSignal, compile_search_input
from trip.domain.state import Evidence, TripState, Update, apply
from trip.domain.understanding import view

EV = Evidence(turn=1, quote="x")


def up(s, field, value=None, op="set", source="user"):
    return apply(s, Update(field=field, op=op, value=value, source=source,
                           confidence="high" if source == "user" else "medium", evidence=EV))


def doc_example():
    """docs/P2_TRIP_UNDERSTANDING.md §15."""
    s = up(TripState(), "start_date", date(2026, 12, 12))
    s = up(up(up(s, "days", 3), "companions", "parents", "add"), "mobility", "car")
    s = up(s, "signal", "elderly", "add", source="inferred")
    for f in ("steep_or_stairs", "long_walk"):
        s = up(s, "hard", {"feature": f, "op": "ne", "value": "present"}, "add")
        s = up(s, "hard_policy", (f, "flag"))
    for k in ("long_stay_chill=present", "noise=quiet", "crowd=low"):
        s = up(s, "soft", (k, "love"), "add")
    s = up(s, "soft", ("scenic_view=present", "love"), "add", source="anchor")
    s = up(s, "soft", ("hiking=present", "off"), "add")
    s = up(s, "pace", "slow", source="inferred")
    s = up(up(s, "novelty", "new"), "unmapped", "nhạc nhẹ", "add")
    from trip.domain.state import settle
    return settle(s)


def test_doc_example_compiles():
    si = compile_search_input(doc_example())
    assert si.context.days == 3 and si.context.companions == ("parents",) and si.context.mobility == "car"
    assert {(h.feature, h.unknown_policy) for h in si.hard_filters} == {("steep_or_stairs", "flag"), ("long_walk", "flag")}
    assert {(w.feature, w.value, w.weight, w.source) for w in si.soft_weights} >= {
        ("noise", "quiet", 1, "user"), ("scenic_view", "present", 1, "anchor"), ("hiking", "present", 0, "user")}
    assert si.pace.level == "slow" and si.novelty.level == "new"
    assert "budget_vnd" in si.unknowns and si.unmapped == ("nhạc nhẹ",)


def test_unhandled_signal_blocks_compile():
    with pytest.raises(UnhandledSignal):
        compile_search_input(up(TripState(), "signal", "knee", "add"))


def test_unknown_policy_defaults_to_exclude():
    s = up(TripState(), "hard", {"feature": "vegetarian_options", "op": "eq", "value": "yes"}, "add")
    assert compile_search_input(s).hard_filters[0].unknown_policy == "exclude"


def test_view_marks_inferred_and_counts_coverage(catalog, cfg):
    v = view(doc_example(), catalog, cfg)
    assert v["pace"]["mark"] is True and v["trip"][0]["target"] == "start_date"
    assert v["hard"][0]["coverage"]["passed"] == 1
    assert {r["key"] for r in v["soft"]} >= {"noise=quiet"} and v["unmapped"][0]["phrase"] == "nhạc nhẹ"
    assert v["safety_pending"] is False
    assert 0 <= v["matching"] <= v["total"] == len(catalog.places)


def test_view_matching_drops_when_a_hard_limit_excludes(catalog, cfg):
    s = up(TripState(), "hard", {"feature": "steep_or_stairs", "op": "ne", "value": "present"}, "add")
    assert view(s, catalog, cfg)["matching"] < view(TripState(), catalog, cfg)["matching"] == len(catalog.places)


def test_view_matching_counts_places_with_evidence_for_a_liked_thing(catalog, cfg):
    c0 = next(c for c in catalog.places if c.known)
    f, k = next(iter(c0.known.items()))
    has = sum(1 for c in catalog.places if c.value(f) == k.value)
    liked = up(TripState(), "soft", (f"{f}={k.value}", "love"), "add")
    assert view(liked, catalog, cfg)["matching"] == has
    avoided = up(TripState(), "soft", (f"{f}={k.value}", "avoid"), "add")
    assert view(avoided, catalog, cfg)["matching"] == len(catalog.places) - has


def test_context_carries_budget_and_experience():
    from trip.domain.state import Meta
    s = TripState(meta=Meta(experience="returning"))
    s = up(s, "budget_vnd", 500000)
    si = compile_search_input(s)
    assert si.context.budget_vnd == 500000 and si.context.experience == "returning"
    assert "budget_vnd" not in si.unknowns


def test_trip_exports_text_helpers():
    from trip import contains, squash
    assert squash("Đồi Chè Cầu Đất!") == "doi che cau dat" and contains("tới đồi chè cầu đất", "Cầu Đất")


def test_budget_is_compiled_to_vnd_per_person_per_day_from_the_scope_days_and_party():
    from trip.domain.budget import per_person_day
    s = up(up(up(TripState(), "budget_vnd", 5_000_000), "days", 3), "companions", "partner", "add")
    assert per_person_day(s) == 833_333  # no scope said: an amount this large is read as the whole trip
    assert per_person_day(up(s, "budget_scope", "per_person")) == 1_666_667
    assert per_person_day(up(s, "budget_scope", "per_day")) == 2_500_000
    assert per_person_day(up(up(s, "budget_vnd", 800_000), "budget_scope", "per_person_day")) == 800_000
    assert per_person_day(up(s, "budget_vnd", 800_000)) == 800_000  # a small amount with no scope: per person per day
    friends = up(up(TripState(), "budget_vnd", 5_000_000), "companions", "friends", "add")
    friends = up(friends, "days", 2)
    assert per_person_day(friends) is None  # who pays is unknown: never guessed
    assert per_person_day(up(friends, "people", 4)) == 625_000


def test_search_input_carries_the_split_budget_month_part_and_liked_kinds():
    s = up(up(up(up(TripState(), "month", 10), "month_part", "late"), "days", 2), "budget_vnd", 4_000_000)
    s = up(up(s, "liked_groups", "chill", "add"), "liked_groups", "meal", "add")
    si = compile_search_input(s)
    assert si.context.month_part == "late" and si.liked_groups == ("chill", "meal")
    assert si.context.budget_vnd is None and "budget_vnd" in si.unknowns  # party unknown: the amount cannot be split
    si = compile_search_input(up(s, "people", 2))
    assert si.context.budget_vnd == 1_000_000 and "budget_vnd" not in si.unknowns
    assert compile_search_input(TripState()).liked_groups == ()


def test_a_new_month_drops_the_part_said_of_the_old_one():
    s = up(up(TripState(), "month", 10), "month_part", "late")
    assert up(s, "month", 10).month_part.value == "late" and not up(s, "month", 11).month_part.known
