import pytest

from corpus.releases import Binding


def test_decision_output_requires_matching_search_input_binding():
    from decision import DecisionOutput
    from fixtures import si
    old = Binding(release_id="r-old", region="dalat")
    new = Binding(release_id="r-new", region="dalat")
    raw = {"confirmed": [], "backup_pool": [], "wishlist": [], "decision_log": [], "feasibility": {},
           "trip_context": {**si().model_dump(mode="json"), "corpus_binding": old.model_dump(mode="json")},
           "corpus_binding": new.model_dump(mode="json")}
    with pytest.raises(ValueError, match="binding"):
        DecisionOutput.model_validate(raw)
    raw["corpus_binding"] = old.model_dump(mode="json")
    assert DecisionOutput.model_validate(raw).corpus_binding == old


def test_decision_data_load_uses_supplied_snapshot_root(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from corpus.snapshot import Region
    from decision import Data
    import decision.pipeline as pipeline
    roots = []
    region = Region.from_records([])
    monkeypatch.setattr(pipeline, "shared", lambda root=None: roots.append(root) or SimpleNamespace(region=lambda key: region))
    assert Data.load(data_root=tmp_path).region is region
    assert roots == [tmp_path / "snapshot"]


def test_planning_tools_refuse_mismatched_release_before_build():
    from types import SimpleNamespace
    from planning import Tools
    from plan_fixtures import sample_trip
    from corpus import load_ontology
    old, new = Binding(release_id="r-old", region="dalat"), Binding(release_id="r-new", region="dalat")
    d, _ = sample_trip()
    d["trip_context"]["ontology_version"] = load_ontology().version
    d["corpus_binding"] = new.model_dump(mode="json")
    d["trip_context"]["corpus_binding"] = new.model_dump(mode="json")
    engine = SimpleNamespace(store=SimpleNamespace(root=None), records=[], live_cfg=None, corpus_binding=old,
                             create=lambda **kw: pytest.fail("mismatched release reached solver"))
    with pytest.raises(ValueError, match="binding"):
        Tools(engine).create({"decision_output": d})
