from dataclasses import replace

import pytest

from plan_fixtures import all_days, day_ctx, rec

from planning.model import DayResult, Item
from planning.route import order_day
from planning.validate import validate


def result(*items):
    return DayResult(tuple(items), (), (), 0, 0, items[-1].end if items else 0)


def visit(pid, start, end):
    return Item("visit", start, end, place_id=pid, name=pid)


def kinds(violations):
    return sorted(v.kind for v in violations)


def run(cx, res, hard=(), anchors=(), budget=None, max_leg=None):
    return validate([cx], [res], list(hard), set(anchors), budget, max_leg)


def test_a_plan_the_scheduler_built_validly_passes():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)], start_node="h", end_node="h", extra_nodes=["h"])
    assert run(cx, order_day(["a", "b"], cx), anchors=["a"]) == []


def test_a_visit_outside_the_opening_hours_fails_even_if_the_scheduler_said_nothing():
    cx = day_ctx([rec("a", 1, 1, hours=all_days("08:00", "09:00"))])
    assert kinds(run(cx, result(visit("a", 600, 660)))) == ["hours"]


def test_a_place_closed_that_weekday_fails():
    cx = day_ctx([rec("a", 1, 1, hours={**all_days(), "mon": []})], weekday="mon")
    assert kinds(run(cx, result(visit("a", 600, 660)))) == ["hours"]


def test_a_sunset_place_visited_at_noon_fails_the_timed_check():
    cx = day_ctx([rec("a", 1, 1, features={"sunset_view": "present"})], sun=(360, 1050))
    assert kinds(run(cx, result(visit("a", 720, 780)))) == ["timed"]


def test_overlapping_items_fail():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)])
    v = run(cx, result(visit("a", 600, 660), visit("b", 650, 710)))
    assert kinds(v) == ["overlap"] and v[0].minutes == 10


def test_a_day_that_runs_past_its_end_or_starts_before_it_fails():
    cx = day_ctx([rec("a", 1, 1, hours=None)], start=480, end=700)      # no hours, so only the day window can fail
    assert kinds(run(cx, result(visit("a", 650, 750)))) == ["day_window"]
    assert kinds(run(cx, result(visit("a", 400, 460)))) == ["day_window"]


def test_a_travel_leg_shorter_than_the_travel_time_fails_and_one_over_the_limit_fails():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)], minutes=30)
    short = Item("travel", 600, 610, from_id="a", to_id="b", mode="motorbike")
    assert kinds(run(cx, result(short))) == ["travel"]
    exact = Item("travel", 600, 630, from_id="a", to_id="b", mode="motorbike")
    assert run(cx, result(exact)) == []
    assert kinds(run(cx, result(exact), max_leg=20)) == ["long_leg"]


def test_an_anchor_that_is_not_in_the_plan_fails():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)])
    v = run(cx, result(visit("a", 600, 660)), anchors=["a", "b"])
    assert [(x.kind, x.place_id) for x in v] == [("anchor", "b")]


def test_a_day_over_the_budget_fails_and_unknown_prices_are_not_counted():
    price = lambda n: {"min_vnd": n, "typical_vnd": n, "max_vnd": n}
    cx = day_ctx([rec("a", 1, 1, price=price(200000)), rec("b", 1, 1, price=price(150000)), rec("c", 1, 1)])
    res = result(visit("a", 600, 660), visit("b", 700, 760), visit("c", 800, 860))
    assert [(v.kind, v.minutes) for v in run(cx, res, budget=300000)] == [("budget", 50000)]
    assert run(cx, res, budget=400000) == []


def test_a_hard_filter_the_place_clearly_breaks_fails_and_a_physical_one_says_so():
    steep = rec("a", 1, 1, features={"steep_or_stairs": "present"})
    cx = day_ctx([steep])
    hard = [{"feature": "steep_or_stairs", "op": "ne", "value": "present", "unknown_policy": "exclude"}]
    v = run(cx, result(visit("a", 600, 660)), hard=hard)
    assert [(x.kind, x.physical) for x in v] == [("hard", True)]


def test_a_physical_filter_with_no_evidence_fails_closed():
    hard = [{"feature": "steep_or_stairs", "op": "ne", "value": "present", "unknown_policy": "flag"}]
    unknown = day_ctx([rec("u", 1, 1)])
    assert [(v.kind, v.physical) for v in run(unknown, result(visit("u", 600, 660)), hard=hard)] == [("hard", True)]


def test_a_physical_filter_cannot_be_bypassed_by_forged_relaxed_state():
    hard = [{"feature": "steep_or_stairs", "op": "ne", "value": "present", "unknown_policy": "exclude"}]
    steep = rec("a", 1, 1, features={"steep_or_stairs": "present"})
    relaxed = day_ctx([steep])
    relaxed.places["a"] = replace(relaxed.places["a"], relaxed=("steep_or_stairs",))
    assert [(v.kind, v.physical) for v in run(relaxed, result(visit("a", 600, 660)), hard=hard)] == [("hard", True)]


def test_a_non_physical_hard_filter_with_no_evidence_fails_closed():
    hard = [{"feature": "live_music", "op": "ne", "value": "present", "unknown_policy": "exclude"}]
    unknown = day_ctx([rec("u", 1, 1)])
    assert [(v.kind, v.physical) for v in run(unknown, result(visit("u", 600, 660)), hard=hard)] == [("hard", False)]


def test_a_relaxed_non_physical_filter_does_not_fail():
    hard = [{"feature": "live_music", "op": "ne", "value": "present", "unknown_policy": "exclude"}]
    relaxed = day_ctx([rec("a", 1, 1, features={"live_music": "present"})])
    relaxed.places["a"] = replace(relaxed.places["a"], relaxed=("live_music",))
    assert run(relaxed, result(visit("a", 1100, 1160)), hard=hard) == []


@pytest.mark.parametrize('value,status,contradicted,expected', [
    ('absent', 'VERIFIED', False, []), ('absent', 'OUTDATED', False, []),
    ('present', 'VERIFIED', False, [('hard', True)]),
    (None, None, False, [('hard', True)]),
    ('absent', 'UNCERTAIN', False, [('hard', True)]),
    ('absent', 'VERIFIED', True, [('hard', True)]),
])
def test_equality_hard_filter_requires_firm_uncontradicted_evidence(value, status, contradicted, expected):
    record = rec('a', 1, 1, features={'steep_or_stairs': value} if value is not None else None)
    if value is not None:
        evidence = record['effort']['steep_or_stairs']
        evidence['status'] = status
        if contradicted:
            evidence['distribution']['present'] = 1
    cx = day_ctx([record])
    hard = [{'feature': 'steep_or_stairs', 'op': 'eq', 'value': 'absent', 'unknown_policy': 'exclude'}]
    assert [(v.kind, v.physical) for v in run(cx, result(visit('a', 600, 660)), hard=hard)] == expected


def test_equality_physical_filter_cannot_be_bypassed_by_relaxed_state():
    cx = day_ctx([rec('a', 1, 1, features={'steep_or_stairs': 'present'})])
    cx.places['a'] = replace(cx.places['a'], relaxed=('steep_or_stairs',))
    hard = [{'feature': 'steep_or_stairs', 'op': 'eq', 'value': 'absent', 'unknown_policy': 'exclude'}]
    assert [(v.kind, v.physical) for v in run(cx, result(visit('a', 600, 660)), hard=hard)] == [('hard', True)]


def test_the_same_place_twice_fails_but_two_near_duplicates_the_user_kept_pass():
    # near duplicate = the same kind of place (PLACE_DECISION §9.1): a hint to keep one, never a reason to refuse
    cx = day_ctx([rec("a", 1, 1, dup=7), rec("b", 1, 1, dup=7)])
    assert kinds(run(cx, result(visit("a", 600, 660), visit("a", 700, 760)))) == ["duplicate"]
    assert run(cx, result(visit("a", 600, 660), visit("b", 700, 760))) == []


def test_a_non_physical_hard_filter_is_not_marked_physical():
    noisy = rec("a", 1, 1, features={"live_music": "present"})
    hard = [{"feature": "live_music", "op": "ne", "value": "present", "unknown_policy": "exclude"}]
    v = run(day_ctx([noisy]), result(visit("a", 1100, 1160)), hard=hard)
    assert [(x.kind, x.physical) for x in v] == [("hard", False)]
