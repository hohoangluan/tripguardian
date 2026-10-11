"""Offline check of Place Decision on the serving records (docs/PLACE_DECISION.md §17).

python -m decision evaluate  ->  data/decision/eval.json

Each hidden trip of config/eval_trips.yaml becomes a Search Input (hard -> "!=", soft -> love the feature's first,
good value) and the real pipeline runs. Measured on the shortlist of the trip's role:
- violations: shortlist places whose evidence has ANY author naming a forbidden value, read from the raw
  distribution, not from check() (target 0);
- unknown_in_main: shortlist places with a hard filter that is not a `pass` by the screen's own rule (target 0,
  fail-closed); uncertain_in_main: places the screen passed with a warning because the value is UNCERTAIN outside the
  safety groups (shown, not hidden);
- near_duplicate_rate, filled (shortlist reached the trip's size), unverified, excluded, ms (pipeline time).
"""

import itertools
import json
import os
import time
from datetime import date
from functools import cache
from pathlib import Path

import yaml

from corpus.ontology import load as load_ontology
from corpus.serving import feature
from trip import SearchInput

from .pipeline import Data
from .pipeline import run as run_pipeline
from .screen import hard_result
from .session import Session, State
from .settings import ROOT, default

TRIPS = ROOT / "config" / "eval_trips.yaml"
START = date(2026, 12, 14)  # a Monday


@cache
def trips() -> tuple[int, list[dict]]:
    raw = yaml.safe_load(TRIPS.read_text(encoding="utf-8"))
    out = list(raw["trips"])
    for i, (hard, soft) in enumerate(itertools.product(raw["cross"]["filters"], raw["cross"]["prefs"])):
        out.append({"id": f"cross_{i}", "role": "experience", "hard": hard, "soft": soft})
    return raw["shortlist"], out


def search_input(trip: dict, version: int) -> SearchInput:
    ont = load_ontology()
    return SearchInput.model_validate({
        "ontology_version": version,
        "context": {"start_date": START.isoformat(), "month": None, "days": 2, "base": None, "mobility": "motorbike",
                    "companions": [], "people": 2, "arrive_at": None, "leave_at": None, "day_end": None,
                    "budget_vnd": None, "experience": None},
        "hard_filters": [{"feature": f, "op": "ne", "value": v, "unknown_policy": "exclude"}
                         for f, v in trip["hard"].items()],
        "anchors": [],
        "soft_weights": [{"feature": f, "value": ont.features[f].values[0], "context": None, "weight": 1,
                          "source": "user"} for f in trip["soft"]],
        "pace": {"level": "normal", "max_leg_min": None, "crowd_tolerance": None},
        "novelty": {"level": None, "visited": []}, "unknowns": [], "unmapped": []})


def violates(rec: dict, fid: str, forbidden: str) -> bool:
    f = feature(rec, fid)
    return bool(f) and f["distribution"].get(forbidden, 0) > 0


def evaluate(records: list[dict] | None = None, cfg=None) -> dict:
    data = Data(records) if records is not None else Data.load()
    cfg = cfg or default()
    k, all_trips = trips()
    version = load_ontology().version
    rows = []
    for trip in all_trips:
        si = search_input(trip, version)
        s = Session(id="0" * 12, search_input=si, state=State())
        t0 = time.perf_counter()
        res = run_pipeline(s, data, cfg)
        ms = round((time.perf_counter() - t0) * 1000)
        picked = [c["id"] for g in res.view["groups"] if g["id"] != "anchors" for c in g["cards"]
                  if c["role"] == trip["role"] and c["top"]]
        recs = [data.by_id[i] for i in picked]
        violations = [r["id"] for r in recs for f, v in trip["hard"].items() if violates(r, f, v)]
        results = {r["id"]: [hard_result(r, h) for h in si.hard_filters] for r in recs}
        unknown = [i for i, rs in results.items() if any(res_ != "pass" for res_, _ in rs)]
        uncertain = [i for i, rs in results.items() if any(warn for _, warn in rs)]
        pairs = list(itertools.combinations(recs, 2))
        dup = sum(1 for a, b in pairs if a.get("near_duplicate_group") is not None
                  and a.get("near_duplicate_group") == b.get("near_duplicate_group"))
        rows.append({"trip": trip["id"], "shortlist": picked, "names": [r["identity"]["name"] for r in recs],
                     "unverified": res.view["unverified"]["count"],
                     "excluded": sum(x["count"] for x in res.view["excluded"]["by_rule"]),
                     "violations": violations, "unknown_in_main": unknown, "uncertain_in_main": uncertain,
                     "near_duplicate_rate": round(dup / len(pairs), 3) if pairs else 0.0,
                     "filled": len(picked) >= k, "ms": ms})
    n = len(rows)
    summary = {"trips": n, "shortlist": k,
               "violations": sum(len(r["violations"]) for r in rows),
               "unknown_in_main": sum(len(r["unknown_in_main"]) for r in rows),
               "uncertain_in_main": sum(len(r["uncertain_in_main"]) for r in rows),
               "near_duplicate_rate": round(sum(r["near_duplicate_rate"] for r in rows) / n, 3) if n else 0.0,
               "filled_rate": round(sum(r["filled"] for r in rows) / n, 3) if n else 0.0,
               "unfilled_trips": [r["trip"] for r in rows if not r["filled"]],
               "ms_max": max((r["ms"] for r in rows), default=0)}
    return {"summary": summary, "trips": rows}


def run() -> dict:
    res = evaluate()
    d = Path(os.environ.get("DATA_DIR", "data"))
    out = (d if d.is_absolute() else ROOT / d) / "decision" / "eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"evaluate: {json.dumps(res['summary'], ensure_ascii=False)}")
    return res
