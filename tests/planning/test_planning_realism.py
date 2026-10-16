"""Spec §11: every realistic case passes the realism checks. PENDING lists the checks a later task of
docs/superpowers/plans/2026-10-15-planning-realistic-core.md turns green; each task deletes its entries."""

import pytest

from realistic_cases import CASES, SERVING, run_case
from realistic_checks import CHECKS

pytestmark = pytest.mark.skipif(not SERVING.exists(), reason="needs data/serving/places.json")

PENDING: dict[str, str] = {}


@pytest.fixture(scope="module")
def runs():
    return {c["id"]: run_case(c) for c in CASES}


def test_every_case_resolves_to_real_places():
    from realistic_cases import pid
    for c in CASES:
        for name in c["places"] + [c["lodging"]]:
            assert pid(name)


@pytest.mark.parametrize("check", sorted(CHECKS))
def test_realism(check, runs, request):
    if check in PENDING:
        request.applymarker(pytest.mark.xfail(strict=True, reason=PENDING[check]))
    failures = [f"{cid}: {msg}" for cid, run in runs.items() for msg in CHECKS[check](run)]
    assert not failures, "\n".join(failures[:40])


def test_no_refused_edit_or_unpicked_plan(runs, request):
    """Run.errors: an edit the engine refused, or a plan shown without being picked, must not pass silently."""
    if "run_errors" in PENDING:
        request.applymarker(pytest.mark.xfail(strict=True, reason=PENDING["run_errors"]))
    failures = [f"{cid}: {e}" for cid, run in runs.items() for e in run.errors]
    assert not failures, "\n".join(failures)
