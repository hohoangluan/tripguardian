import pytest

from agents import AgentError
from fixtures import si, srec
from trip import Catalog, Engine as TripEngine, SessionStore, Settings, TurnInput
from decision import Data, Engine as DecisionEngine, Store, load_settings


@pytest.mark.parametrize('text', ['3 ngày', '3 ngày đi ô tô', '2 người, xe máy'])
def test_trip_simple_frame_records_clues_without_calling_llm(text):
    calls = []
    async def agent(fields, on_say):
        calls.append(fields)
        raise AgentError('offline')
    engine = TripEngine(Catalog.from_records([], 1), Settings(), SessionStore(None), agent)
    sid = engine.create()['id']
    engine.turn(sid, TurnInput(kind='text', text=text), lambda *a: None)
    assert calls == []
    state = engine.store.get(sid).state
    if '3' in text:
        assert state.days.value == 3
    if 'ô tô' in text:
        assert state.mobility.value == 'car'
    assert any('heuristic:frame' in t['text'] for t in engine.store.get(sid).transcript if t['role'] == 'system')


@pytest.mark.parametrize('text', ['không đi ô tô', '3 ngày hoặc 4 ngày', '3 ngày với bố mẹ', '3 ngày nếu trời đẹp'])
def test_trip_unhandled_clues_and_conditions_still_reach_llm(text):
    calls = []
    async def agent(fields, on_say):
        calls.append(fields)
        raise AgentError('offline')
    engine = TripEngine(Catalog.from_records([], 1), Settings(), SessionStore(None), agent)
    sid = engine.create()['id']
    engine.turn(sid, TurnInput(kind='text', text=text), lambda *a: None)
    assert len(calls) == 1


def test_decision_exact_name_command_uses_guarded_act_without_llm():
    calls = []
    async def agent(fields, on_say):
        calls.append(fields)
        raise AgentError('offline')
    engine = DecisionEngine(Data([srec('a', name='Quán Một')]), load_settings(), Store(None), agent)
    sid = engine.create(si().model_dump(mode='json'))['id']
    engine.turn(sid, 'chọn Quán Một', lambda *a: None)
    assert calls == []
    assert engine.load(sid)['view']['selected'] == ['a']
    assert 'heuristic:exact_command' in engine.store.get(sid).log[-1]['action']['log']


@pytest.mark.parametrize('text', ['không chọn Quán Một', 'chọn Quán Một nếu gần', 'chọn giúp phần còn lại', 'bỏ Quán Một và Quán Hai'])
def test_decision_complex_or_negative_commands_reach_llm(text):
    calls = []
    async def agent(fields, on_say):
        calls.append(fields)
        raise AgentError('offline')
    engine = DecisionEngine(Data([srec('a', name='Quán Một')]), load_settings(), Store(None), agent)
    sid = engine.create(si().model_dump(mode='json'))['id']
    engine.turn(sid, text, lambda *a: None)
    assert len(calls) == 1


def test_exact_command_rejects_duplicate_names_and_extra_intent():
    from decision.heuristics import exact_command
    aliases = {'P1': {'id': 'a', 'name': 'Quán Một'}, 'P2': {'id': 'b', 'name': 'Quán Một'}}
    assert exact_command('chọn Quán Một', aliases) is None
    assert exact_command('chọn Quán Một rồi khóa lại', aliases) is None
