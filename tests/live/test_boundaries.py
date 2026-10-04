"""The invariants that keep live context from becoming Place Intelligence (docs/PLANNING.md)."""

import ast
from pathlib import Path

import pytest

import live

SRC = Path(__file__).resolve().parents[2] / "src" / "live"
CORPUS_DIRS = ("data/intel", "data/serving", "data/gmaps", "data/tiktok", "data/review",
               "data\intel", "data\serving", "data\gmaps")
OTHER_PACKAGES = {"corpus", "decision", "trip", "planning"}
CORPUS_EXCEPTION = {"corpus"}  # live/lodging reuses corpus.crawl's public API (docs/PLANNING.md §Chỗ ở (crawl live))


def modules():
    return sorted(SRC.rglob("*.py"))


def test_there_is_something_to_check():
    assert len(modules()) >= 7


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_no_module_names_a_corpus_directory(path):
    text = path.read_text(encoding="utf-8")
    for bad in CORPUS_DIRS:
        assert bad not in text, f"{path.name} names {bad}"


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_no_module_imports_another_project_package(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    allowed = CORPUS_EXCEPTION if "lodging" in path.parts else set()
    bad = (imported & OTHER_PACKAGES) - allowed
    assert not bad, f"{path.name} imports {bad}"


def test_lodging_reaches_corpus_only_through_its_crawl_public_api():
    tree = ast.parse((SRC / "lodging" / "maps.py").read_text(encoding="utf-8"))
    modules_imported = {n.module for n in ast.walk(tree)
                        if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module}
    assert "corpus.crawl" in modules_imported
    assert not any(m.startswith("corpus.crawl.") for m in modules_imported)


def test_the_public_api_is_exactly_what_planning_may_use():
    assert set(live.__all__) == {"Settings", "Unavailable", "geocode", "holidays", "load_settings", "lodging_near",
                                 "route_shape", "sun_times", "travel_matrix", "weather"}
    for name in live.__all__:
        assert hasattr(live, name), name


def test_the_only_thing_live_writes_is_its_own_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from live import cache
    cache.put("osrm", {"a": 1}, [[0]], "osrm")
    cache.put("geocode", {"q": "x"}, None, "nominatim")
    top = {p.relative_to(tmp_path).parts[0] for p in tmp_path.rglob("*") if p.is_file()}
    assert top == {"live"}
