"""Planning reads other packages only through their public API and writes nothing of the corpus
(docs/specs/PLANNING_SPEC.md §Ranh giới module; RULE.md §2)."""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "planning"
ALLOWED_CORPUS = {"corpus.serving", "corpus.ontology"}
WRITTEN_BY_CORPUS = ("data/intel", "data/serving", "data/gmaps", "data/tiktok", "data/review")


def modules():
    return sorted(SRC.rglob("*.py"))


def imports(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


def test_there_is_something_to_check():
    assert len(modules()) >= 12


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_no_deep_import_into_live_or_corpus_and_none_into_decision_or_trip(path):
    for name in imports(path):
        top = name.split(".")[0]
        assert top not in {"decision", "trip"}, f"{path.name} imports {name}"
        assert top != "live" or name == "live", f"{path.name} deep-imports {name}"
        assert top != "corpus" or name in ALLOWED_CORPUS, f"{path.name} imports {name}"


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_no_module_names_a_directory_only_the_corpus_writes(path):
    text = path.read_text(encoding="utf-8")
    for bad in WRITTEN_BY_CORPUS:
        assert bad not in text, f"{path.name} names {bad}"


def test_the_public_api_is_the_plan_builder_and_its_settings():
    import planning
    assert set(planning.__all__) == {"Settings", "build_plan", "load_settings", "render_text"}
    for name in planning.__all__:
        assert hasattr(planning, name)
