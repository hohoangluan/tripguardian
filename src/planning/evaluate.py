"""Offline check of Planning on the serving records (docs/specs/PLANNING_SPEC.md §Đo).

python -m planning evaluate  ->  data/planning/eval.json

Each hidden trip of config/eval_trips.yaml (the same file src/decision/evaluate.py reads) becomes a Search Input,
run through Place Decision in process -- decision.Engine's own public create/act/confirm, no HTTP, no second
server -- into a Decision Output, then through Planning: create, pick the first ok variant, confirm.
"""

from functools import cache

import yaml

from corpus.ontology import load as load_ontology
from decision import Data as DecisionData, Engine as DecisionEngine, Store as DecisionStore
from decision import load_settings as decision_default
from trip import SearchInput

from .settings import ROOT

TRIPS = ROOT / "config" / "eval_trips.yaml"


@cache
def trips() -> list[dict]:
    """The named hidden trips of config/eval_trips.yaml -- not the `cross` combinations that file also builds
    (those exist for Decision's own feature-pass coverage; the 10 named trips already vary enough in hard/soft/role
    for Planning's purposes)."""
    raw = yaml.safe_load(TRIPS.read_text(encoding="utf-8"))
    return list(raw["trips"])


def search_input(trip: dict, version: int, days: int = 3) -> SearchInput:
    """Mirrors decision.evaluate's own (non-public) search_input() -- duplicated, not imported, since
    decision.evaluate is not part of decision's public API (decision/__init__.py)."""
    ont = load_ontology()
    return SearchInput.model_validate({
        "ontology_version": version,
        "context": {"start_date": "2026-12-14", "month": None, "days": days, "base": None, "mobility": "motorbike",
                    "companions": [], "people": 2, "arrive_at": "09:00", "leave_at": "15:00", "day_end": None,
                    "budget_vnd": 3_000_000, "experience": None},
        "hard_filters": [{"feature": f, "op": "ne", "value": v, "unknown_policy": "exclude"}
                         for f, v in trip["hard"].items()],
        "anchors": [],
        "soft_weights": [{"feature": f, "value": ont.features[f].values[0], "context": None, "weight": 1,
                          "source": "user"} for f in trip["soft"]],
        "pace": {"level": "normal", "max_leg_min": None, "crowd_tolerance": None},
        "novelty": {"level": None, "visited": []}, "unknowns": [], "unmapped": []})


def decision_outputs(records: list[dict], cfg=None) -> list[tuple[str, dict]]:
    """(trip id, Decision Output) for every hidden trip Place Decision can actually confirm -- a trip whose
    pipeline shortlist cannot fill its role, or whose feasibility is "partial"/"infeasible", is skipped (not an
    error: it means Place Decision itself found nothing fit, which Planning has nothing to schedule)."""
    cfg = cfg or decision_default()
    data = DecisionData(records)
    version = load_ontology().version
    out = []
    for trip in trips():
        eng = DecisionEngine(data, cfg, DecisionStore(None))  # a fresh Engine per trip: no session state to leak
        si = search_input(trip, version)
        created = eng.create(si.model_dump(mode="json"))
        sid = created["id"]
        picked = [c["id"] for g in created["view"]["groups"] if g["id"] != "anchors" for c in g["cards"]
                 if c["role"] == trip["role"]]
        for pid in picked:
            eng.act(sid, {"type": "select", "place_id": pid})
        try:
            confirmed = eng.confirm(sid)
        except Exception:  # decision.NotConfirmable is not part of decision's public API; catch broadly on purpose
            continue
        out.append((trip["id"], confirmed))
    return out
