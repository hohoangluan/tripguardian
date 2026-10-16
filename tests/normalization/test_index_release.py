import json

import numpy as np
import pytest


def test_declared_normalization_missing_fails_closed(corpus_roots):
    source, release = corpus_roots
    put(release, "intel/summary.json", {"normalization_id": "missing"})
    with pytest.raises(FileNotFoundError, match="normalization manifest"):
        compile_index(source_root=source, output_root=release, publish=False)

from corpus.index import Index, compile_index
from corpus.index.vectors import OUT


def put(root, path, value):
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value))
    return p


@pytest.fixture
def corpus_roots(tmp_path, monkeypatch):
    source, release = tmp_path / "source", tmp_path / "release"
    records = [{"id": p, "status": "VERIFIED", "identity": {"name": p, "category_group": g},
                "features": {"scenic_view": {"value": "present", "status": "VERIFIED"}}}
               for p, g in (("F", "cafe"), ("S", "stay"))]
    put(release, "serving/places.json", {"records": records})
    put(release, "intel/places/F.json", {"features": {
        "scenic_view": {"servable": True, "needs_review": False, "observation_ids": ["good"]},
        "steep_or_stairs": {"servable": False, "needs_review": True, "observation_ids": ["bad"]}}})
    monkeypatch.setattr("corpus.index.compile.config", lambda: {"embedder": {
        "image_model": "image-test", "text_model": "text-test", "image_dimension": 2, "text_dimension": 2}}, raising=False)
    monkeypatch.setattr("corpus.index.compile.vocabulary", lambda: {
        "version": 1, "min_authors": 1, "styles": [{"id": "retro"}]})
    return source, release


def vectors(source, kind, items, model=None, dimension=2, count=None):
    base = source.joinpath(*OUT[kind]) / "F"
    put(source, str(base.relative_to(source)) + ".json", {
        "model": model or ("text-test" if kind == "spans" else "image-test"), "place_id": "F", "items": items})
    np.save(base.with_suffix(".npy"), np.ones((len(items) if count is None else count, dimension), np.float16))


def test_release_reuses_only_existing_media_and_gated_spans(corpus_roots):
    source, release = corpus_roots
    media = source / "gmaps/places/F/photos/good.jpg"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"saved image")
    vectors(source, "photos", [{"file": str(media.relative_to(source)), "source": "gmaps", "photo_id": "p"},
                              {"file": "gmaps/places/F/photos/missing.jpg", "source": "gmaps", "photo_id": "q"}])
    vectors(source, "spans", [{"observation_id": "good", "observations": ["good", "bad"],
        "features": ["scenic_view=present", "steep_or_stairs=present"], "quote": "saved quote", "source": "gmaps_review"},
        {"observation_id": "bad", "observations": ["bad"], "features": ["steep_or_stairs=present"],
         "quote": "unsafe", "source": "gmaps_review"}])
    result = compile_index(source_root=source, output_root=release, publish=False, eligible_ids={"F", "S"})
    assert result["photos"] == 1 and result["spans"] == 1
    assert {i["reason"] for i in result["issues"]} >= {"missing_media", "stale_evidence"}
    assert not (release / "index/current").exists()
    ix = Index.load(result["version"], data=release)
    import lancedb
    rows = lancedb.connect(str(ix.root)).open_table("spans").to_arrow().to_pylist()
    assert json.loads(rows[0]["features"]) == ["scenic_view=present"]
    assert json.loads(rows[0]["observations"]) == ["good"]
    assert result["coverage"]["stay"]["places"] == 1
    assert result["coverage"]["stay"]["photos"] == 0
    assert result["inputs"][0]["sha256"]


@pytest.mark.parametrize("model,dimension,count,reason", [
    ("wrong-model", 2, 1, "incompatible_model"),
    ("image-test", 3, 1, "incompatible_dimension"),
    ("image-test", 2, 2, "item_alignment")])
def test_incompatible_vectors_are_reported_without_embedding(corpus_roots, model, dimension, count, reason):
    source, release = corpus_roots
    vectors(source, "photos", [{"file": "x.jpg", "source": "gmaps", "photo_id": "p"}], model, dimension, count)
    result = compile_index(source_root=source, output_root=release, publish=False)
    assert result["photos"] == 0
    assert reason in {i["reason"] for i in result["issues"]}


def test_style_with_missing_media_is_not_presented(corpus_roots):
    source, release = corpus_roots
    put(source, "gmaps/style_observations/F.json", {"observations": [{"id": "style", "feature": "retro",
        "author": "user", "source_id": "p", "span": {"field": "photos/missing.jpg", "quote": "wood"}}]})
    result = compile_index(source_root=source, output_root=release, publish=False)
    ix = Index.load(result["version"], data=release)
    assert ix.place_styles("F") == {}
    assert any(i["reason"] == "missing_style_evidence" for i in result["issues"])


def test_normalized_quote_and_source_must_match_saved_span(corpus_roots):
    source, release = corpus_roots
    claim = {"id": "good", "feature": "scenic_view", "value": "present", "source_type": "gmaps_review", "source_id": "review-good",
             "span": {"quote": "current quote"}}
    path = put(source, "normalization/N/gmaps/observations/F.json", {"place_fid": "F", "observations": [claim]})
    import hashlib
    put(source, "normalization/N/manifest.json", {"inputs": [{"canonical_id": "F",
        "normalized": "gmaps/observations/F.json", "normalized_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]})
    put(release, "intel/summary.json", {"normalization_id": "N"})
    vectors(source, "spans", [{"observation_id": "good", "observations": ["good"],
        "features": ["scenic_view=present"], "quote": "old quote", "source": "gmaps_review"},
        {"observation_id": "good", "observations": ["good"], "features": ["scenic_view=present"],
         "quote": "current quote", "source": "tiktok_caption"}])
    result = compile_index(source_root=source, output_root=release, publish=False)
    assert result["spans"] == 0
    assert sum(i["reason"] == "stale_evidence" for i in result["issues"]) == 2


def test_normalization_outside_source_root_keeps_span_validation(corpus_roots):
    import hashlib
    source, release = corpus_roots
    normalized_root = source.parent / "scratch/N"
    claim = {"id": "good", "feature": "scenic_view", "value": "present", "source_type": "gmaps_review", "source_id": "review-good",
             "span": {"quote": "current quote"}}
    path = put(normalized_root, "gmaps/observations/F.json", {"place_fid": "F", "observations": [claim]})
    put(normalized_root, "manifest.json", {"id": "N", "inputs": [{"canonical_id": "F",
        "normalized": "gmaps/observations/F.json", "normalized_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]})
    put(release, "intel/summary.json", {"normalization_id": "N"})
    vectors(source, "spans", [{"observation_id": "good", "observations": ["good"],
        "features": ["scenic_view=present"], "quote": "old quote", "source": "gmaps_review"}])
    result = compile_index(source_root=source, output_root=release, normalization_root=normalized_root, publish=False)
    assert result["spans"] == 0


def test_style_claim_labelled_wrong_is_not_presented(corpus_roots):
    source, release = corpus_roots
    image = source / "gmaps/places/F/photos/p.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"saved")
    put(source, "gmaps/style_observations/F.json", {"observations": [{"id": "style", "feature": "retro",
        "value": "present", "author": "user", "source_id": "p", "span": {"field": "photos/p.jpg", "quote": "wood"}}]})
    from corpus.review import label_key
    import corpus.index.compile as compiler
    compiler_label = {label_key("p", "retro", "present", "wood"): "wrong"}
    # The persisted review contract is injected to isolate this test from global labels.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(compiler, "label_verdicts", lambda **kwargs: compiler_label, raising=False)
        result = compile_index(source_root=source, output_root=release, publish=False)
    assert Index.load(result["version"], data=release).place_styles("F") == {}
    assert any(i["reason"] == "invalidated_style_evidence" for i in result["issues"])


def test_malformed_style_payload_is_reported(corpus_roots):
    source, release = corpus_roots
    put(source, "gmaps/style_observations/F.json", {"observations": [None]})
    result = compile_index(source_root=source, output_root=release, publish=False)
    assert result["styled"] == 0
    assert any(i["reason"] == "invalid_style_payload" for i in result["issues"])


def test_default_index_reader_resolves_release_but_explicit_data_is_independent(corpus_roots, monkeypatch):
    source, release = corpus_roots
    result = compile_index(source_root=source, output_root=release, publish=True)
    monkeypatch.setenv("DATA_DIR", str(source))
    monkeypatch.setattr("corpus.releases.resolve", lambda root: release)
    assert Index.current_version() == result["version"]
    assert Index.load().root == release / "index" / result["version"]
    assert Index.current_version(data=source) is None
    with pytest.raises(FileNotFoundError):
        Index.load(data=source)

@pytest.mark.parametrize('source_name,quote,oid,expected', [
    ('gmaps_review', 'valid', 'unserved', False),
    ('tiktok_caption', 'valid', 'unserved', None),
    ('gmaps_review', 'wrong', 'unserved', None),
    ('gmaps_review', 'valid', 'missing', None),
])
def test_span_gate_retains_only_normalized_unserved_claims(corpus_roots, source_name, quote, oid, expected):
    import hashlib
    from corpus.index.compile import _span_gate
    source, release = corpus_roots
    claim = {'id': 'unserved', 'feature': 'noise', 'value': 'low',
             'source_type': 'gmaps_review', 'source_id': 'review-valid', 'span': {'quote': 'valid'}}
    path = put(source, 'normalization/N/claims.json', {'observations': [claim]})
    put(source, 'normalization/N/manifest.json', {'inputs': [{'canonical_id': 'F',
        'normalized': 'claims.json', 'normalized_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}]})
    put(release, 'intel/summary.json', {'normalization_id': 'N'})
    gate = _span_gate(source, release, {'F': {'details': {}}})
    result = gate('F', {'observations': [oid], 'features': ['noise=low'], 'quote': quote, 'source': source_name})
    if expected is None:
        assert result is None
    else:
        assert result[1] is expected


def test_span_gate_preserves_normalized_claim_metadata(corpus_roots):
    import hashlib
    from corpus.index.compile import _span_gate
    source, release = corpus_roots
    claim = {'id': 'good', 'feature': 'scenic_view', 'value': 'present', 'source_type': 'gmaps_review',
             'source_id': 'review-1', 'span': {'quote': 'valid'}, 'context': {'season': 'dry'},
             'observed_at': '2025-01-01'}
    path = put(source, 'normalization/N/claims.json', {'observations': [claim]})
    put(source, 'normalization/N/manifest.json', {'inputs': [{'canonical_id': 'F',
        'normalized': 'claims.json', 'normalized_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}]})
    put(release, 'intel/summary.json', {'normalization_id': 'N'})
    gate = _span_gate(source, release, {'F': {'features': {'scenic_view': {'status': 'VERIFIED', 'value': 'present'}}}})
    item, served = gate('F', {'observations': ['good'], 'features': ['scenic_view=present'],
                             'quote': 'valid', 'source': 'gmaps_review'})
    assert item['claims'] == [claim]
    assert served


def test_span_gate_drops_invalid_pair_in_shared_span(corpus_roots):
    import hashlib
    from corpus.index.compile import _span_gate
    source, release = corpus_roots
    claim = {'id': 'good', 'feature': 'scenic_view', 'value': 'present', 'source_type': 'gmaps_review', 'source_id': 'review-good',
             'span': {'quote': 'valid'}}
    path = put(source, 'normalization/N/claims.json', {'observations': [claim]})
    put(source, 'normalization/N/manifest.json', {'inputs': [{'canonical_id': 'F',
        'normalized': 'claims.json', 'normalized_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}]})
    put(release, 'intel/summary.json', {'normalization_id': 'N'})
    gate = _span_gate(source, release, {'F': {'features': {'scenic_view': {'status': 'VERIFIED', 'value': 'absent'}}}})
    item, served = gate('F', {'observations': ['good', 'bad'],
        'features': ['scenic_view=present', 'noise=low'], 'quote': 'valid', 'source': 'gmaps_review'})
    assert item['features'] == ['scenic_view=present']
    assert not served


@pytest.mark.parametrize('verdict', ['wrong', 'unsure_again'])
@pytest.mark.parametrize('shared_valid_claim', [False, True])
def test_normalized_unserved_span_drops_rejected_judge_claim(corpus_roots, monkeypatch, verdict, shared_valid_claim):
    import hashlib
    from corpus.index.compile import _span_gate
    from corpus.review import label_key
    source, release = corpus_roots
    rejected = {'id': 'rejected', 'feature': 'noise', 'value': 'low', 'source_type': 'gmaps_review',
                'source_id': 'review-bad', 'span': {'quote': 'valid quote'}}
    valid = {**rejected, 'id': 'valid', 'source_id': 'review-good', 'feature': 'cozy_decor', 'value': 'present'}
    claims = [rejected, valid] if shared_valid_claim else [rejected]
    path = put(source, 'normalization/N/claims.json', {'observations': claims})
    put(source, 'normalization/N/manifest.json', {'inputs': [{'canonical_id': 'F',
        'normalized': 'claims.json', 'normalized_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}]})
    put(release, 'intel/summary.json', {'normalization_id': 'N'})
    verdicts = {label_key('review-bad', 'noise', 'low', 'valid quote'): verdict}
    monkeypatch.setattr('corpus.index.compile.label_verdicts', lambda **kwargs: verdicts)
    gate = _span_gate(source, release, {'F': {'details': {}}})
    result = gate('F', {'observations': [c['id'] for c in claims],
        'features': [c['feature'] + '=' + c['value'] for c in claims],
        'quote': 'valid quote', 'source': 'gmaps_review'})
    if shared_valid_claim:
        assert result[0]['observations'] == ['valid']
        assert result[0]['claims'] == [valid]
        assert result[1] is False
    else:
        assert result is None


def test_normalized_unserved_claim_without_source_identity_is_dropped(corpus_roots):
    import hashlib
    from corpus.index.compile import _span_gate
    source, release = corpus_roots
    claim = {'id': 'unknown-source', 'feature': 'noise', 'value': 'low',
             'source_type': 'gmaps_review', 'span': {'quote': 'valid'}}
    path = put(source, 'normalization/N/claims.json', {'observations': [claim]})
    put(source, 'normalization/N/manifest.json', {'inputs': [{'canonical_id': 'F',
        'normalized': 'claims.json', 'normalized_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}]})
    put(release, 'intel/summary.json', {'normalization_id': 'N'})
    gate = _span_gate(source, release, {'F': {'details': {}}}, verdicts={})
    assert gate('F', {'observations': ['unknown-source'], 'features': ['noise=low'],
                      'quote': 'valid', 'source': 'gmaps_review'}) is None
