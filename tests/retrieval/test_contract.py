import inspect
from unittest.mock import MagicMock

import pytest
from corpus.retrieval import RetrievalEngine
from corpus.releases import Binding
from test_retrieval_boundary import _make_engine, _photo_row


def test_scopes_are_required():
    for name in ('search_names', 'semantic', 'similar'):
        assert inspect.signature(getattr(RetrievalEngine, name)).parameters['within'].default is inspect.Parameter.empty


def test_from_snapshot_without_index_keeps_structured_reads(tmp_path):
    engine = _make_engine([_photo_row('a')], [])
    snap = MagicMock(version='S', root=tmp_path / 'snapshot')
    snap.region.return_value = engine._region
    binding = Binding(region='test', snapshot_version='S')
    pinned = RetrievalEngine.from_snapshot(snap, 'test', binding=binding)
    assert pinned.binding == binding
    assert pinned.get_place('a')['name'] == 'Place a'
    assert pinned.search_names('Place', within={'a'})[0].place_id == 'a'
    assert pinned.semantic('garden', within={'a'}) == []
    assert pinned.evidence('a', 'outdoor_seating') == []
    assert pinned.coverage({'a'}).missing_spans == ('a',)


def test_empty_scope_never_embeds():
    engine = _make_engine([_photo_row('a')], [])
    engine._index.embed_text = MagicMock(side_effect=AssertionError('must not embed'))
    assert engine.semantic('garden', within=set()) == []


def test_ontology_only_never_creates_vector_hit():
    engine = _make_engine([_photo_row('a')], [])
    assert engine._merge_hits([], [], {'a': 1.0}, 5) == []


def test_similar_reference_must_be_in_scope():
    engine = _make_engine([_photo_row('a'), _photo_row('b')], [])
    assert engine.similar('a', within={'b'}) == []


def test_evidence_checks_current_value_and_observation_pair():
    from test_retrieval_boundary import _span_row
    engine = _make_engine([_photo_row('a')], [
        {**_span_row('a', 'other', 'tables', '["noise=low", "outdoor_seating=present"]'),
         'observations': ['other', 'actual']},
        _span_row('a', 'stale', 'closed', '["outdoor_seating=absent"]')])
    engine._region.record = lambda pid: {'environment': {'outdoor_seating': {
        'value': 'present', 'status': 'UNCERTAIN', 'evidence': ['actual']}}}
    hits = engine.evidence('a', 'outdoor_seating')
    assert len(hits) == 1
    assert hits[0].observation_id == 'actual'
    assert hits[0].value == 'present'
    assert hits[0].status == 'UNCERTAIN'
    assert hits[0].source == 'gmaps'
    assert hits[0].observed_at is None


def test_evidence_without_served_value_is_empty():
    from test_retrieval_boundary import _span_row
    engine = _make_engine([_photo_row('a')], [_span_row('a', 'o', 'tables', '["outdoor_seating=present"]')])
    assert engine.evidence('a', 'outdoor_seating') == []


def test_evidence_context_is_fail_closed():
    from test_retrieval_boundary import _span_row
    engine = _make_engine([_photo_row('a')], [_span_row('a', 'o', 'tables', '["outdoor_seating=present"]')])
    engine._region.record = lambda pid: {'environment': {'outdoor_seating': {'value': 'present', 'status': 'VERIFIED'}}}
    assert engine.evidence('a', 'outdoor_seating', context={'season': 'rainy'}) == []


def test_evidence_context_does_not_prove_global_value():
    from test_retrieval_boundary import _span_row
    engine = _make_engine([_photo_row('a')], [{**_span_row('a', 'o', 'tables', '["outdoor_seating=present"]'),
        'claims': [{'id': 'o', 'feature': 'outdoor_seating', 'value': 'present', 'context': {'season': 'rainy'}}]}])
    engine._region.record = lambda pid: {'environment': {'outdoor_seating': {'value': 'present', 'status': 'VERIFIED'}}}
    assert engine.evidence('a', 'outdoor_seating', context={'season': 'rainy'}) == []


@pytest.mark.parametrize('snapshot_version,region,index_version', [('wrong', 'test', None), ('S', 'other', None), ('S', 'test', 'wrong')])
def test_from_snapshot_rejects_mismatched_readers(snapshot_version, region, index_version, tmp_path):
    engine = _make_engine([_photo_row('a')], [])
    snapshot = MagicMock(version=snapshot_version, root=tmp_path / "snapshot")
    snapshot.region.return_value = engine._region
    binding = Binding(region='test', snapshot_version='S', index_version='test_v1')
    index = engine._index if index_version else None
    if index is not None:
        index.version = index_version
    with pytest.raises(ValueError, match='binding mismatch'):
        RetrievalEngine.from_snapshot(snapshot, region, binding=binding, index=index)


def test_semantic_postfilters_even_misbehaving_reader():
    from corpus.index import PhotoHit
    engine = _make_engine([_photo_row('a')], [])
    engine._index.embed_image = lambda q: None
    engine._index.search_photos = lambda *args, **kwargs: [PhotoHit('foreign', 1, 'photo', 'author', False, 'gmaps')]
    assert engine.semantic(b'image', within={'a', 'foreign'}) == []


def test_coverage_intersects_region_eligibility():
    engine = _make_engine([_photo_row('a')], [])
    report = engine.coverage({'a', 'foreign'})
    assert report.total == 1
    assert report.missing_spans == ('a',)
    assert report.missing_photos == ()


def test_from_snapshot_rejects_other_release_with_same_version(tmp_path):
    snapshot = MagicMock(version='S', root=tmp_path / 'releases' / 'r-other' / 'snapshot')
    binding = Binding(release_id='r-pinned', region='test', snapshot_version='S')
    with pytest.raises(ValueError, match='snapshot binding mismatch'):
        RetrievalEngine.from_snapshot(snapshot, 'test', binding=binding)


def test_from_snapshot_rejects_index_from_other_release(tmp_path):
    engine = _make_engine([_photo_row('a')], [])
    snapshot = MagicMock(version='S', root=tmp_path / 'releases' / 'r-pinned' / 'snapshot')
    snapshot.region.return_value = engine._region
    binding = Binding(release_id='r-pinned', region='test', snapshot_version='S', index_version='test_v1')
    engine._index.root = tmp_path / 'releases' / 'r-other' / 'index' / 'test_v1'
    with pytest.raises(ValueError, match='index binding mismatch'):
        RetrievalEngine.from_snapshot(snapshot, 'test', binding=binding, index=engine._index)


def test_from_snapshot_accepts_readers_in_same_named_release(tmp_path):
    engine = _make_engine([_photo_row('a')], [])
    root = tmp_path / 'releases' / 'r-pinned'
    snapshot = MagicMock(version='S', root=root / 'snapshot')
    snapshot.region.return_value = engine._region
    binding = Binding(release_id='r-pinned', region='test', snapshot_version='S', index_version='test_v1')
    engine._index.root = root / 'index' / 'test_v1'
    pinned = RetrievalEngine.from_snapshot(snapshot, 'test', binding=binding, index=engine._index)
    assert pinned.binding == binding
