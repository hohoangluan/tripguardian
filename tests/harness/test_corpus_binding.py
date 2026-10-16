import pytest

from harness import Harness, Request, Store
from test_dispatch import Tools


def bundle():
    return {stage: Tools(stage) for stage in ("trip", "decision", "planning")}


def send(harness, view, operation, request_id):
    return harness.request(view["id"], Request(stage=view["stage"], operation=operation,
                           expected_revision=view["revision"], request_id=request_id))


def test_journey_pins_all_handoffs_and_restore_to_its_release(tmp_path):
    from corpus.releases import Binding
    old, new = Binding(release_id="r-old", region="dalat"), Binding(release_id="r-new", region="dalat")
    bundles = {"r-old": bundle(), "r-new": bundle()}
    opened = []

    def factory(binding):
        opened.append(binding.release_id)
        return bundles[binding.release_id]

    store = Store(tmp_path)
    h = Harness(**{f"{s}_tools": t for s, t in bundles["r-old"].items()}, store=store,
                corpus_binding=old, tools_for_binding=factory)
    v = h.create()
    assert store.get(v["id"]).corpus_binding == old
    v = send(h, v, "turn", "t1")
    v = send(h, v, "advance", "d1")
    assert v["outputs"]["trip"]["corpus_binding"] == old.model_dump(mode="json")
    bundles["r-old"]["decision"].states[v["sessions"]["decision"]]["selected"] = ["keep-me"]
    h.store.save(h.store.get(v["id"]).model_copy(update={"snapshots": {**h.store.get(v["id"]).snapshots,
        "decision": bundles["r-old"]["decision"].snapshot(v["sessions"]["decision"])}}))
    # Restart with a different default. Old tools restore only from the old release.
    restored = bundle()
    bundles["r-old"] = restored
    h2 = Harness(**{f"{s}_tools": t for s, t in bundles["r-new"].items()}, store=Store(tmp_path),
                 corpus_binding=new, tools_for_binding=factory)
    loaded = h2.load(v["id"])
    assert loaded["result"]["view"]["selected"] == ["keep-me"]
    assert opened == ["r-old"]
    assert not bundles["r-new"]["decision"].states
    advanced = send(h2, loaded, "advance", "p1")
    assert advanced["outputs"]["decision"]["corpus_binding"] == old.model_dump(mode="json")
    assert len(restored["planning"].states) == 1


def test_missing_pinned_release_fails_before_snapshot_restore(tmp_path):
    from corpus.releases import Binding
    tools = bundle()
    old = Binding(release_id="r-old", region="dalat")
    h = Harness(**{f"{s}_tools": t for s, t in tools.items()}, store=Store(tmp_path), corpus_binding=old)
    v = h.create()

    def missing(binding):
        raise FileNotFoundError("pinned release missing")

    current = bundle()
    restarted = Harness(**{f"{s}_tools": t for s, t in current.items()}, store=Store(tmp_path),
                        corpus_binding=Binding(release_id="r-new", region="dalat"), tools_for_binding=missing)
    with pytest.raises(FileNotFoundError, match="pinned release missing"):
        restarted.load(v["id"])
    assert not current["trip"].states


def test_legacy_journey_never_adopts_current_release(tmp_path):
    from corpus.releases import Binding
    legacy = bundle()
    h = Harness(**{f"{s}_tools": t for s, t in legacy.items()}, store=Store(tmp_path))
    v = h.create()
    current = bundle()
    opened = []

    def factory(binding):
        opened.append(binding)
        return legacy

    restarted = Harness(**{f"{s}_tools": t for s, t in current.items()}, store=Store(tmp_path),
                        corpus_binding=Binding(release_id="r-new", region="dalat"), tools_for_binding=factory)
    restarted.load(v["id"])
    assert opened == [None]
    assert restarted.store.get(v["id"]).corpus_binding is None
