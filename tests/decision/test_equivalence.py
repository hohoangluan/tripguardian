"""The table-based Place Decision run gives the same view as the per-place run (tests/decision/reference.py)."""

import pytest

from fixtures import love, si, srec
from gen import records, sessions
from reference import run_reference

from decision.pipeline import Data, run
from decision.session import Session, State
from decision.settings import default

CFG = default()


def assert_same(s, recs, cfg=CFG, data=None, memo=None):
    new = run(s, data or Data(recs), cfg, memo).view
    old = run_reference(s, recs, cfg).view
    assert new == old, f"session {s.id}: views differ"


@pytest.mark.parametrize("seed", range(10))
def test_equivalence_random_sessions(seed):
    recs = records(seed)
    for s in sessions(seed, recs, 20):
        assert_same(s, recs)


@pytest.mark.parametrize("seed", range(10))
def test_equivalence_with_one_memo_across_changing_inputs(seed):
    recs = records(seed)
    data, memo = Data(recs), {}
    for s in sessions(seed, recs, 20):
        assert_same(s, recs, data=data, memo=memo)
        assert_same(s, recs, data=data, memo=memo)  # same input again: every tier from the memo


def test_equivalence_activity_override_and_roleless_keep():
    recs = records(4)
    recs.append(srec("RENT", group="rental", usable=()))
    s = Session(id="0" * 12, search_input=si(soft_weights=[love("scenic_view")]),
                state=State(selected=["RENT", recs[0]["id"]], activities={recs[1]["id"]: "eating", recs[2]["id"]: "coffee"}))
    assert_same(s, recs)


def test_equivalence_missing_kept_place():
    recs = records(5)
    s = Session(id="0" * 12, search_input=si(anchors=[{"place_id": "GONE", "priority": "must"}]),
                state=State(selected=["GONE2"]))
    assert_same(s, recs)


def test_data_keeps_the_list_api():
    recs = records(6)
    d = Data(recs)
    assert [r["id"] for r in d.records] == [r["id"] for r in recs]
    assert recs[0]["id"] in d.by_id and "nope" not in d.by_id
    assert Data(region=d.region).region is d.region


@pytest.mark.corpus
def test_equivalence_eval_trips_on_the_real_snapshot():
    snap = pytest.importorskip("corpus.snapshot")
    try:
        region = snap.shared().region()
    except FileNotFoundError:
        pytest.skip("no snapshot")
    from corpus.ontology import load
    from decision import eval_search_input, eval_trips
    from decision.curation import apply
    recs = region.records()
    data = Data(region=region)
    version, trips = eval_trips()
    for trip in trips:
        si_ = eval_search_input(trip, version).model_copy(update={"ontology_version": load().version})
        s = Session(id="0" * 12, search_input=si_, state=State())
        for step in range(4):
            new = run(s, data, CFG)
            old = run_reference(s, recs, CFG)
            assert new.view == old.view, (trip["id"], step)
            ids = new.view["shortlist"]
            if not ids:
                break
            act = [{"type": "select", "place_id": ids[0]}, {"type": "drop", "place_id": ids[-1], "reason": "far"},
                   {"type": "lock", "place_id": ids[0]}, {"type": "select", "place_id": ids[len(ids) // 2]}][step]
            s.state = apply(s.state, act, lambda p: p in new.cands or p in data.by_id, new.alternatives, None, CFG)


@pytest.mark.parametrize("seed", range(5))
def test_equivalence_along_a_session_with_one_memo(seed):
    from decision.curation import apply

    recs = records(seed)
    data, memo = Data(recs), {}
    s = sessions(seed, recs, 1)[0]
    for step in range(8):
        res = run(s, data, CFG, memo)
        assert res.view == run_reference(s, recs, CFG).view, (seed, step)
        ids = res.view["shortlist"]
        if len(ids) < 3:
            break
        act = [{"type": "select", "place_id": ids[0]}, {"type": "select", "place_id": ids[1]},
               {"type": "lock", "place_id": ids[0]}, {"type": "drop", "place_id": ids[2], "reason": "far"},
               {"type": "prefer", "feature": "scenic_view", "value": "present", "weight": 1},
               {"type": "wishlist", "place_id": ids[1]}, {"type": "select", "place_id": ids[-1]},
               {"type": "feedback", "reason": "crowded"}][step]
        s.state = apply(s.state, act, lambda p: p in res.cands or p in data.by_id, res.alternatives, None, CFG)


def test_equivalence_memo_follows_wish_changes():  # F3, Review Focus 5
    recs = records(7)
    data = Data(recs)
    meals = [r["id"] for r in recs if "meal" in r["usable_as"]][:5]
    with_wish = si(wishes={"dishes": [{"dish": "bánh căn", "quote": "bánh căn", "place_ids": meals}], "kinds": [],
                           "like": [{"place_id": recs[0]["id"], "but": [], "quote": "giống"}]},
                   liked_groups=["chill"], context={"purpose": "relax"})
    memo = {}
    for search in (with_wish, si(), with_wish):
        assert_same(Session(id="0" * 12, search_input=search, state=State()), recs, data=data, memo=memo)


def test_random_sessions_carry_wishes():  # F1
    ss = sessions(3, records(3), 30)
    assert any(s.search_input.wishes.dishes for s in ss) and any(s.search_input.liked_groups for s in ss)
    assert any(s.search_input.wishes.like for s in ss) and any(s.search_input.context.purpose for s in ss)
