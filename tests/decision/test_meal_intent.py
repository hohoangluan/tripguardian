"""Meal intent follows the query and venue selection without an extra question."""

import pytest
from fixtures import si, srec

from decision.curation import pending
from decision.pipeline import Data, run
from decision.session import Session, State
from decision.settings import default
from decision.output import build


@pytest.mark.parametrize('group,activity,role', [('cafe', 'coffee', 'experience'), ('restaurant', 'eating', 'meal')])
def test_venue_selection_infers_activity_without_a_question(group, activity, role):
    record = srec('venue', group=group)
    state = State(selected=['venue'])
    cfg = default()
    assert pending(state, {'venue': record}, si(), {}, 1, {}, cfg) is None
    session = Session(id='123456abcdef', search_input=si(), state=state)
    result = run(session, Data([record]), cfg)
    assert result.cands['venue'].role == role
    assert build(session, result, cfg)['trip_context']['activities']['venue'] == activity
    assert session.search_input.activities == {}
    assert record['usable_as'] == ['experience', 'meal', 'backup']


@pytest.mark.parametrize('activity,role', [('eating', 'meal'), ('sightseeing', 'experience')])
def test_explicit_query_intent_overrides_venue_default(activity, role):
    record = srec('venue', group='cafe')
    query = si().model_copy(update={'activities': {'venue': activity}})
    session = Session(id='123456abcdef', search_input=query, state=State(selected=['venue']))
    result = run(session, Data([record]), default())
    assert result.cands['venue'].role == role
    assert build(session, result, default())['trip_context']['activities']['venue'] == activity
    assert pending(session.state, {'venue': record}, query, {}, 1, {}, default()) is None


def test_handoff_and_reload_keep_inferred_intent_without_waiting_for_an_answer():
    from decision.engine import Engine
    from decision.session import Store
    engine = Engine(Data([srec('venue', group='cafe')]), default(), Store(None))
    sid = engine.create(si().model_dump(mode='json'))['id']
    engine.act(sid, {'type': 'select', 'place_id': 'venue'})
    assert engine.draft(sid)['trip_context']['activities']['venue'] == 'coffee'
    engine._results.clear()
    assert engine.confirm(sid)['trip_context']['activities']['venue'] == 'coffee'
    assert engine.load(sid)['view']['pending'] is None
