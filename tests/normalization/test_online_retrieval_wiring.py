from types import SimpleNamespace

import pytest

from corpus.releases import Binding
from corpus.retrieval import SemanticHit


@pytest.mark.parametrize('module', ['trip', 'decision', 'planning'])
def test_factory_rejects_mismatched_retrieval_before_opening_data(module, tmp_path):
    from importlib import import_module
    factory = import_module(module).create_engine
    binding = Binding(region='dalat', release_id='r-pinned')
    reader = SimpleNamespace(binding=Binding(region='dalat', release_id='r-other'))
    with pytest.raises(ValueError, match='retrieval.*binding'):
        factory(tmp_path, binding=binding, retrieval=reader)


def test_trip_cues_use_scoped_hybrid_without_second_embedding():
    from trip.infrastructure.looks import Looks
    calls = []
    reader = SimpleNamespace(semantic=lambda q, **kw: calls.append((q, kw)) or [
        SemanticHit('a', .2, 'span', 'red lanterns', False, None),
        SemanticHit('outside', .3, 'photo', 'invented.jpg', True, None)])
    looks = Looks(SimpleNamespace(by_id={'a': None, 'b': None}), warm=False, retrieval=reader)
    ids, vector = looks.by_cues(['red', 'lanterns'], within={'a', 'outside'})
    assert ids == ['a'] and vector is None
    assert calls == [('red, lanterns', {'within': {'a'}, 'mode': 'vibe'})]
    assert looks.best_photo('a') is None


@pytest.mark.parametrize('error', [RuntimeError('CUDA unavailable'), OSError('index unavailable')])
def test_trip_cues_keep_turn_available_when_retrieval_fails(error):
    from trip.infrastructure.looks import Looks

    def semantic(*args, **kwargs):
        raise error

    looks = Looks(SimpleNamespace(by_id={'a': None}), warm=False,
                  retrieval=SimpleNamespace(semantic=semantic))
    assert looks.by_cues(['red lanterns'], within={'a'}) == ([], None)
    assert looks._error == f'{type(error).__name__}: {error}'


def test_harness_bundle_opens_one_reader_for_all_three_factories(tmp_path):
    import ast
    from pathlib import Path
    import harness.__main__ as entry
    source = ast.parse(Path(entry.__file__).read_text())
    factory = next(n for n in ast.walk(source) if isinstance(n, ast.FunctionDef) and n.name == 'tools_for_binding')
    calls = []
    binding = Binding(region='dalat', release_id='r-pinned')
    reader = SimpleNamespace(binding=binding)
    def open_reader(**kwargs):
        calls.append(kwargs)
        return reader
    def engine(data, **kwargs):
        return SimpleNamespace(**kwargs)
    scope = {'Binding': Binding, 'data': tmp_path,
             'RetrievalEngine': SimpleNamespace(open=open_reader),
             'trip_engine': engine, 'decision_engine': engine, 'planning_engine': engine,
             'TripTools': lambda e: SimpleNamespace(engine=e),
             'DecisionTools': lambda e: SimpleNamespace(engine=e),
             'PlanningTools': lambda e: SimpleNamespace(engine=e),
             'bind': lambda *a, **kw: Binding(region='dalat')}
    exec(compile(ast.Module(body=[factory], type_ignores=[]), entry.__file__, 'exec'), scope)
    tools = scope['tools_for_binding'](binding)
    assert calls == [{'data_root': tmp_path, 'binding': binding}]
    assert all(t.engine.retrieval is reader and t.engine.binding == binding for t in tools.values())
    legacy = scope['tools_for_binding'](None)
    assert all(t.engine.corpus_binding is None for t in legacy.values())
