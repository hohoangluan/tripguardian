"""Decision explanations fetch pinned serving evidence without treating similarity as a fact."""

from types import SimpleNamespace

import pytest

from corpus.releases import Binding
from corpus.retrieval import EvidenceHit
from decision import Data, Engine, Store, Tools, load_settings
from fixtures import feat, si, srec


def make_engine(status="VERIFIED"):
    record = srec("cafe", features={"scenic_view": feat("present", status=status)})
    engine = Engine(Data([record]), load_settings(), Store(None))
    binding = Binding(region="dalat", release_id="r-pinned")
    engine.corpus_binding = binding
    calls = []
    hit = EvidenceHit("cafe", "o1", "View nhìn ra hồ", ("scenic_view=present",), 1.0, "r-pinned")
    engine.retrieval = SimpleNamespace(binding=binding, evidence=lambda *a, **kw: calls.append((a, kw)) or [hit])
    sid = Tools(engine).create({"search_input": si(corpus_binding=binding).model_dump(mode="json")})["id"]
    return engine, sid, calls


def test_explanation_evidence_keeps_serving_status_and_binding():
    engine, sid, calls = make_engine()
    out = Tools(engine).read(sid, "evidence", {"place": "cafe", "feature": "scenic_view"})
    assert out["value"] == "present" and out["status"] == "VERIFIED"
    assert out["reason"] == "available" and out["items"][0]["quote"] == "View nhìn ra hồ"
    assert out["corpus_binding"]["release_id"] == "r-pinned"
    assert calls
    assert engine.store.get(sid).log == []


@pytest.mark.parametrize("feature,status,reason", [
    ("scenic_view", "UNCERTAIN", "unverified_feature"), ("parking", "VERIFIED", "missing_feature")])
def test_unknown_explanation_never_borrows_semantic_quote(feature, status, reason):
    engine, sid, calls = make_engine(status)
    out = Tools(engine).read(sid, "evidence", {"place": "cafe", "feature": feature})
    assert out["items"] == [] and out["reason"] == reason
    assert not calls


def test_explanation_rejects_wrong_release_and_outside_membership():
    engine, sid, _ = make_engine()
    with pytest.raises(ValueError, match="place"):
        Tools(engine).read(sid, "evidence", {"place": "outside", "feature": "scenic_view"})
    engine.retrieval.binding = Binding(region="dalat", release_id="r-other")
    with pytest.raises(ValueError, match="binding"):
        Tools(engine).read(sid, "evidence", {"place": "cafe", "feature": "scenic_view"})


def test_no_index_explains_missing_evidence_without_changing_serving_fact():
    engine, sid, _ = make_engine()
    engine.retrieval = None
    out = Tools(engine).read(sid, "evidence", {"place": "cafe", "feature": "scenic_view"})
    assert out["status"] == "VERIFIED"
    assert out["items"] == [] and out["reason"] == "index_unavailable"


def test_context_without_serving_verdict_is_unknown_even_with_global_fact():
    engine, sid, calls = make_engine()
    out = Tools(engine).read(sid, "evidence", {"place": "cafe", "feature": "scenic_view",
                                              "context": {"time_of_day": "morning"}})
    assert out["value"] is None and out["status"] == "unknown"
    assert out["items"] == [] and not calls


def test_historical_null_binding_has_no_verified_evidence_lineage():
    engine, sid, calls = make_engine()
    session = engine.store.get(sid)
    session.search_input = session.search_input.model_copy(update={"corpus_binding": None})
    engine.corpus_binding = None
    engine.retrieval.binding = Binding(region="dalat", snapshot_version="legacy-current")
    out = Tools(engine).read(sid, "evidence", {"place": "cafe", "feature": "scenic_view"})
    assert out["corpus_binding"] is None and out["items"] == []
    assert out["reason"] == "legacy_lineage_unavailable"
    assert not calls


def test_http_query_context_is_decoded_and_validated_at_evidence_boundary():
    engine, sid, _ = make_engine()
    payload = {"place": "cafe", "feature": "scenic_view", "context": '{"time_of_day":"morning"}'}
    out = Tools(engine).read(sid, "evidence", payload)
    assert out["status"] == "unknown" and out["items"] == []
    with pytest.raises(ValueError):
        Tools(engine).read(sid, "evidence", {**payload, "context": "bad json"})


def test_agent_context_is_bounded_grounded_and_legacy_safe():
    engine, sid, calls = make_engine()
    binding = engine.corpus_binding
    engine.retrieval.evidence = lambda *a, **kw: [EvidenceHit(
        'cafe', 'o1', 'View nhìn ra hồ', ('scenic_view=present',), 1., 'r-pinned',
        source='tiktok', feature='scenic_view', value='present', status='VERIFIED')]
    aliases = {'P1': {'id': 'cafe', 'name': 'Cafe'}}
    context = engine._grounded_context(aliases, 'P1', binding)
    assert context[0]['features'][0]['quote'] == 'View nhìn ra hồ'
    assert context[0]['features'][0]['status'] == 'VERIFIED'
    assert context[0]['features'][0]['observation_id'] == 'o1'
    assert context[0]['release_id'] == 'r-pinned'
    assert engine._grounded_context(aliases, '', None) == []
    engine.retrieval.evidence = lambda *a, **kw: [EvidenceHit(
        'cafe', 'o1', 'wrong value', (), 1., 'r-pinned', feature='scenic_view', value='absent', status='VERIFIED')]
    assert engine._grounded_context(aliases, '', binding)[0]['features'][0]['quote'] is None


def test_turn_passes_grounded_source_to_agent_without_changing_selection():
    from decision.guard import TurnPlan
    engine, sid, _ = make_engine()
    received = []
    engine.retrieval.evidence = lambda *a, **kw: [EvidenceHit(
        'cafe', 'o1', 'View nhìn ra hồ', ('scenic_view=present',), 1., 'r-pinned',
        source='tiktok', feature='scenic_view', value='present', status='VERIFIED')]
    async def agent(fields, on_say):
        received.append(fields)
        return TurnPlan(say='')
    engine.agent = agent
    before = engine.load(sid)['view']['selected']
    engine.turn(sid, 'giải thích khung cảnh ở đây', lambda *a: None)
    assert 'View nhìn ra hồ' in received[0]['places']
    assert 'r-pinned' in received[0]['places']
    assert engine.load(sid)['view']['selected'] == before
