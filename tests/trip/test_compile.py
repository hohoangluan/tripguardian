from datetime import date

import pytest

from trip.compile import UnhandledSignal, compile_search_input
from trip.state import Evidence, TripState, Update, apply
from trip.understanding import view

EV = Evidence(turn=1, quote="x")


def up(s, field, value=None, op="set", source="user"):
    return apply(s, Update(field=field, op=op, value=value, source=source,
                           confidence="high" if source == "user" else "medium", evidence=EV))


def doc_example():
    """docs/TRIP_UNDERSTANDING.md §15."""
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
    from trip.state import settle
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


def test_context_carries_budget_and_experience():
    from trip.state import Meta
    s = TripState(meta=Meta(experience="returning"))
    s = up(s, "budget_vnd", 500000)
    si = compile_search_input(s)
    assert si.context.budget_vnd == 500000 and si.context.experience == "returning"
    assert "budget_vnd" not in si.unknowns


def test_trip_exports_text_helpers():
    from trip import contains, squash
    assert squash("Đồi Chè Cầu Đất!") == "doi che cau dat" and contains("tới đồi chè cầu đất", "Cầu Đất")
