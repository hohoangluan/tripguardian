"""Long-trip allocation, sparse coverage and bounded suggestion work."""

import pytest
from fixtures import si, srec
from pydantic import ValidationError
from trip import MAX_TRIP_DAYS

from decision.contracts import DecisionOutput
from decision.curation import ActionError
from decision.diversify import sizes
from decision.engine import Engine
from decision.pipeline import Data
from decision.session import Store
from decision.settings import default


def engine():
    records = [srec(str(i), group="cafe" if i < 8 else "nature") for i in range(16)]
    eng = Engine(Data(records), default(), Store(None))
    sid = eng.create(si(context={"days": 14}).model_dump(mode="json"))["id"]
    return eng, sid


def test_types_are_spread_and_existing_assignments_stay_stable():
    eng, sid = engine()
    prev = {}
    for i in range(8):
        view = eng.act(sid, {"type": "select", "place_id": str(i)})["view"]
        mapping = view["chunk_assignments"]
        assert all(mapping[p] == chunk for p, chunk in prev.items())
        prev = dict(mapping)
    assert sorted(list(prev.values()).count(chunk) for chunk in (0, 1)) == [4, 4]
    assert [c["type_counts"]["cafe"] for c in view["chunks"]] == [4, 4]
    assert set(eng.confirm(sid)["chunk_assignments"]) == set(view["selected"])


def test_sparse_selection_is_optional_and_undo_restores_chunk_move():
    eng, sid = engine()
    view = eng.act(sid, {"type": "select", "place_id": "0"})["view"]
    original = view["chunk_assignments"]["0"]
    assert view["coverage"]["status"] == "sparse"
    view = eng.act(sid, {"type": "keep_free_time"})["view"]
    assert view["coverage"]["free_time_accepted"]
    assert eng.confirm(sid)
    eng.act(sid, {"type": "move_chunk", "place_id": "0", "chunk": 1 - original})
    view = eng.act(sid, {"type": "undo"})["view"]
    assert view["chunk_assignments"]["0"] == original


@pytest.mark.parametrize("chunk", [-1, 2, True, "1"])
def test_invalid_destination_is_refused(chunk):
    eng, sid = engine()
    eng.act(sid, {"type": "select", "place_id": "0"})
    with pytest.raises(ActionError):
        eng.act(sid, {"type": "move_chunk", "place_id": "0", "chunk": chunk})


def test_shortlist_work_is_bounded_to_one_week():
    cfg = default()
    assert sizes(si(), 14, 0, cfg) == sizes(si(), 7, 0, cfg)


def test_output_rejects_unknown_ids_and_out_of_range_chunks():
    eng, sid = engine()
    eng.act(sid, {"type": "select", "place_id": "0"})
    out = eng.confirm(sid)
    for mapping in ({"ghost": 0}, {"0": 2}, {"0": True}, {"0": -1}):
        with pytest.raises(ValidationError):
            DecisionOutput.model_validate({**out, "chunk_assignments": mapping})


@pytest.mark.parametrize("days,chunk", ((None, (MAX_TRIP_DAYS + 6) // 7), (None, 999), (7, 1), (8, 2)))
def test_output_bounds_chunks_even_without_known_duration(days, chunk):
    eng, sid = engine()
    eng.act(sid, {"type": "select", "place_id": "0"})
    out = eng.confirm(sid)
    out["trip_context"]["context"]["days"] = days
    with pytest.raises(ValidationError):
        DecisionOutput.model_validate({**out, "chunk_assignments": {"0": chunk}})


def test_unknown_duration_accepts_absolute_chunks_and_legacy_mapping():
    eng, sid = engine()
    eng.act(sid, {"type": "select", "place_id": "0"})
    out = eng.confirm(sid)
    out["trip_context"]["context"]["days"] = None
    for mapping in ({}, {"0": 0}, {"0": 1}, {"0": (MAX_TRIP_DAYS + 6) // 7 - 1}):
        assert DecisionOutput.model_validate({**out, "chunk_assignments": mapping}).chunk_assignments == mapping


@pytest.mark.parametrize("context", ({"days": 13}, {"days": 14, "start_date": "2026-12-20"}))
def test_context_rebase_invalidates_allocations_through_undo_history(context):
    from decision.tools import Tools

    eng, sid = engine()
    for action in (
        {"type": "select", "place_id": "0"},
        {"type": "lock", "place_id": "0"},
        {"type": "drop", "place_id": "2", "reason": "dislike"},
        {"type": "move_chunk", "place_id": "0", "chunk": 1},
        {"type": "keep_free_time"},
        {"type": "select", "place_id": "1"},
    ):
        eng.act(sid, action)
    session = eng.store.get(sid)
    original_history = [(list(s.selected), list(s.locked), [d.model_dump() for d in s.dropped])
                        for s in session.history]
    assert any(s.free_time for s in session.history)
    Tools(eng).rebase(sid, {"search_input": si(context=context).model_dump(mode="json")})
    assert [(s.selected, s.locked, [d.model_dump() for d in s.dropped])
            for s in session.history] == original_history
    assert all(not s.chunk_assignments and not s.free_time for s in session.history)
    view = eng.act(sid, {"type": "undo"})["view"]
    assert view["chunk_assignments"] == {"0": 0}
    assert not view["coverage"]["free_time_accepted"]
    assert session.state.selected == ["0"] and session.state.locked == ["0"]
    assert [d.place_id for d in session.state.dropped] == ["2"]
