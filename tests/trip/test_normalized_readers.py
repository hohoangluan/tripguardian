from types import SimpleNamespace
import hashlib
import json

import pytest

from corpus.snapshot import Region
from trip.api import tools
from trip.infrastructure.catalog import Catalog
from trip.infrastructure.looks import Looks
from trip.infrastructure.settings import Settings


def publish_pointer(root, name, *, manifest=True):
    release = root / "releases" / name
    release.mkdir(parents=True)
    if manifest:
        (release / "artifact").write_bytes(b"test")
        (release / "manifest.json").write_text(json.dumps({"release_id": name, "city": "dalat",
            "artifacts": [{"path": "artifact", "sha256": hashlib.sha256(b"test").hexdigest()}]}), encoding="utf-8")
    (root / "releases" / "current").write_text(name, encoding="utf-8")
    return release


@pytest.fixture
def factory(monkeypatch):
    opened, sensed = [], []
    region = Region.from_records([], [], {})

    def shared(root, **kwargs):
        opened.append(root)
        return SimpleNamespace(root=root, version=kwargs.get("version") or None,
                               region=lambda key=None: region)

    def senses(cfg, catalog, *, data_root=None, binding=None, retrieval=None):
        sensed.append(data_root)
        return {}

    def chat(*args, **kwargs):
        pytest.fail("factory must not call the model")

    monkeypatch.setattr(tools, "load_dotenv", lambda *args: None)
    monkeypatch.setattr(tools, "load", lambda: Settings())
    monkeypatch.setattr(tools, "shared", shared)
    monkeypatch.setattr(tools, "senses", senses)
    monkeypatch.setattr(tools, "langchain_chat", lambda cfg: chat)
    return opened, sensed


@pytest.mark.parametrize("released", [True, False], ids=["release", "legacy"])
def test_factory_binds_snapshot_and_senses_to_same_explicit_root(tmp_path, factory, released):
    resolved = publish_pointer(tmp_path, "r-test") if released else tmp_path

    engine = tools.create_engine(tmp_path)

    opened, sensed = factory
    assert opened == [resolved / "snapshot"]
    assert sensed == [resolved]
    assert engine.corpus_binding.release_id == ("r-test" if released else None)


def test_factory_resolves_once_even_when_pointer_changes(tmp_path, monkeypatch, factory):
    resolved = publish_pointer(tmp_path, "r-first")
    opened, sensed = factory
    shared = tools.shared

    def shared_then_switch(root, **kwargs):
        snapshot = shared(root, **kwargs)
        publish_pointer(tmp_path, "r-next")
        return snapshot

    monkeypatch.setattr(tools, "shared", shared_then_switch)

    tools.create_engine(tmp_path)

    assert opened == [resolved / "snapshot"]
    assert sensed == [resolved]


def test_factory_missing_release_manifest_fails_before_opening_readers(tmp_path, factory):
    publish_pointer(tmp_path, "r-missing", manifest=False)

    with pytest.raises(FileNotFoundError, match="missing release manifest"):
        tools.create_engine(tmp_path)

    assert factory == ([], [])


def test_senses_passes_explicit_data_root_to_looks(tmp_path, monkeypatch):
    loaded = []
    catalog = Catalog.from_snapshot(Region.from_records([], [], {}), n_min=1)
    reader = object()

    def looks(catalog_arg, *, data_root=None, retrieval=None):
        loaded.append((catalog_arg, data_root, retrieval))
        return reader

    monkeypatch.setattr(tools, "Looks", looks)

    retrieval = SimpleNamespace(binding=None)
    assert tools.senses(Settings(), catalog, data_root=tmp_path, retrieval=retrieval)["looks"] is reader
    assert loaded == [(catalog, tmp_path, retrieval)]


@pytest.mark.parametrize("explicit", [True, False], ids=["explicit-root", "default-root"])
def test_looks_loads_index_from_its_bound_root(tmp_path, monkeypatch, explicit):
    from corpus.index import Index

    loaded, embedded = [], []
    index = SimpleNamespace(embed_text=embedded.append)

    def load(*, data=None):
        loaded.append(data)
        return index

    monkeypatch.setattr(Index, "load", load)
    data_root = tmp_path if explicit else None
    kwargs = {"data_root": data_root} if explicit else {}
    looks = Looks(Catalog.from_snapshot(Region.from_records([], [], {}), n_min=1), warm=False, **kwargs)

    looks._load()

    assert loaded == [data_root]
    assert embedded == ["khởi động"]
    assert looks.ready()


def test_delayed_looks_load_uses_pinned_legacy_version(tmp_path, monkeypatch):
    from corpus.index import Index
    loaded = []
    index = SimpleNamespace(embed_text=lambda text: None)
    (tmp_path / "index").mkdir()
    pointer = tmp_path / "index/current"
    pointer.write_text("old")
    looks = Looks(Catalog.from_records([], 1), warm=False, data_root=tmp_path,
                  index_version="old", pinned=True)
    pointer.write_text("new")
    monkeypatch.setattr(Index, "load", lambda *, data=None, version=None: loaded.append((data, version)) or index)
    looks._load()
    assert loaded == [(tmp_path, "old")]


def test_pinned_missing_index_stays_unavailable_when_new_index_appears(tmp_path, monkeypatch):
    from corpus.index import Index
    looks = Looks(Catalog.from_records([], 1), warm=False, data_root=tmp_path, pinned=True)
    monkeypatch.setattr(Index, "load", lambda **kwargs: pytest.fail("missing pinned index must not follow pointer"))
    looks._load()
    assert not looks.ready()
    assert "pinned corpus binding" in looks._error


@pytest.mark.parametrize("released", [True, False], ids=["release", "legacy"])
def test_cli_binds_readers_to_resolved_root_and_sessions_to_original_root(tmp_path, monkeypatch, released):
    import sys

    from trip import __main__ as cli

    resolved = publish_pointer(tmp_path, "r-cli") if released else tmp_path
    opened, sensed, sessions, served = [], [], [], []
    region = Region.from_records([], [], {})

    def shared(root, **kwargs):
        opened.append(root)
        if released:
            publish_pointer(tmp_path, "r-next")
        return SimpleNamespace(region=lambda: region)

    def senses(cfg, catalog, *, data_root=None, binding=None, retrieval=None):
        sensed.append(data_root)
        return {}

    def chat(*args, **kwargs):
        pytest.fail("CLI startup must not call the model")

    monkeypatch.setattr(sys, "argv", ["trip", "serve", "--port", "9876"])
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "load_dotenv", lambda *args: None)
    monkeypatch.setattr(cli, "load", lambda: Settings())
    monkeypatch.setattr(cli, "shared", shared)
    monkeypatch.setattr(cli, "senses", senses)
    monkeypatch.setattr(cli, "SessionStore", sessions.append)
    monkeypatch.setattr(cli, "langchain_chat", lambda cfg: chat)
    monkeypatch.setattr(cli, "run", lambda engine, port: served.append(port))

    cli.main()

    assert opened == [resolved / "snapshot"]
    assert sensed == [resolved]
    assert sessions == [tmp_path / "trip" / "sessions"]
    assert served == [9876]


def test_looks_enforces_membership_and_scope():
    from trip.infrastructure.catalog import Candidate
    catalog = Catalog(tuple(Candidate(p, p, None, None, None, None, {}, 0) for p in ("A", "B")))
    hits = [SimpleNamespace(place_id=p, score=1.0) for p in ("outside", "B", "A")]
    calls = []
    ix = SimpleNamespace(places={p: {} for p in ("outside", "B", "A")},
        cfg={"search": {"min_text_photo": 0}, "place_pick": {"min_score": 0, "margin": 0}},
        embed_text=lambda _: SimpleNamespace(photo="vector"), embed_image=lambda _: "image",
        search_photos=lambda vec, within: calls.append(within) or hits,
        places_by_photos=lambda hs, **kwargs: hs,
        similar_places=lambda pid, k, within: hits,
        best_photo=lambda pid: pid + ".jpg", place_styles=lambda pid: ["retro"])
    looks = Looks(catalog, index=ix)
    assert looks.total == 2
    assert looks.by_cues(["retro"], within={"A", "outside"})[0] == ["A"]
    assert looks.by_cues(["retro"])[0] == ["B", "A"]
    assert looks.by_photo(b"image", within={"A"})[1] == [hits[2]]
    assert looks.by_photo(b"image", within={"A"})[2] == "A"
    assert looks.similar("A", within={"A"}) == ["A"]
    assert looks.similar("outside") == []
    assert looks.best_photo("outside") is None
    assert looks.styles_of("outside") == []
    assert calls[0] == {"A"}
    ix.clusters = lambda ids, vec: [SimpleNamespace(id="c", style="retro", places=["outside", "B", "A"],
        photos=(("outside", "outside.jpg"), ("A", "a.jpg")))]
    ix.style_label = lambda _: "Retro"
    kinds = looks.kinds(["A", "outside"])
    assert kinds[0].places == ("A",)
    assert kinds[0].photos == (("A", "a.jpg"),)
