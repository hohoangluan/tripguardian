"""Planning reads other packages only through their public API and writes nothing of the corpus
(docs/PLANNING.md §Ranh giới module; RULE.md §2)."""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "planning"
ALLOWED_CORPUS = {"corpus.serving", "corpus.ontology", "corpus.llm", "corpus.releases", "corpus.snapshot", "corpus.retrieval"}
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
        # decision: only evaluate.py, offline, in process, through decision's public __init__ (docs/PLANNING.md
        # §Ranh giới module lists decision as a one-way dependency; P9 ruling). Everywhere else it stays forbidden.
        assert top != "decision" or (path.name in {"evaluate.py", "tools.py"} and name == "decision"), f"{path.name} imports {name}"
        # trip: only its public text helpers (trip/__init__.py), the same import decision/guard.py makes (P7 ruling)
        assert top != "trip" or name == "trip", f"{path.name} deep-imports {name}"
        assert top != "live" or name == "live", f"{path.name} deep-imports {name}"
        assert top != "corpus" or name in ALLOWED_CORPUS, f"{path.name} imports {name}"


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_no_module_names_a_directory_only_the_corpus_writes(path):
    text = path.read_text(encoding="utf-8")
    for bad in WRITTEN_BY_CORPUS:
        assert bad not in text, f"{path.name} names {bad}"


def test_the_public_api_is_the_plan_builder_and_its_settings():
    import planning
    assert set(planning.__all__) == {"Engine", "TripIncomplete", "Settings", "build_lodging_variants", "build_plan", "build_variants",
                                     "load_settings", "render_lodging_variants", "render_text", "render_variants",
                                     "run_server", "PlanningProposal", "Tools", "create_engine", "run_proposal"}
    for name in planning.__all__:
        assert hasattr(planning, name)


def test_stated_nights_are_what_planning_counts_and_the_time_budget_is_less_than_whole_days():
    from planning.engine import _nights
    from planning.model import Day
    from planning.output import time_budget
    assert _nights({"days": 3, "nights": 3}) == 3 and _nights({"days": 3}) == 2 and _nights({"days": 1, "nights": 0}) == 0
    days = [Day(0, None, None, 14 * 60, 21 * 60, None, None), Day(1, None, None, 8 * 60, 21 * 60, None, None),
            Day(2, None, None, 8 * 60, 12 * 60, None, None)]
    budget = time_budget(days, 2)
    assert (budget["days"], budget["nights"]) == (3, 2)
    assert [p["from"] for p in budget["per_day"]] == ["14:00", "08:00", "08:00"]
    assert budget["total_minutes"] == 7 * 60 + 13 * 60 + 4 * 60 < 3 * 13 * 60
