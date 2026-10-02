"""Offline check of a reference Place Decision on the serving records (docs/PLACE_DECISION.md §17).

python -m corpus evaluate  ->  data/serving/eval.json

For each hidden Trip State (config/eval_trips.yaml): screen (physical, then each hard filter with check(): fail ->
out, unknown -> the "chưa xác minh" list), rank by preference fit × confidence − uncertainty, pick the shortlist
with MMR. Measured, per trip and overall:
- violations: shortlist places whose evidence has ANY author naming a forbidden value, read from the raw
  distribution, not from check() (target 0);
- unknown_in_main: shortlist places with a hard filter not `pass` (target 0, fail-closed);
- near_duplicate_rate: share of shortlist pairs in one near-duplicate group;
- filled: shortlist size reached; unverified: how many places wait in the "chưa xác minh" list.
"""

import itertools
import json
from functools import cache

import yaml

from ..crawl.common.files import ROOT, data_dir, now, write_json
from .groups import mmr, near_duplicate_groups
from .record import check, feature
from .run import load

TRIPS = ROOT / "config" / "eval_trips.yaml"
GOOD = {"present", "good", "suitable", "yes", "easy", "quiet", "low", "clean", "generous", "free", "none", "short"}
CONFIDENCE_N = 3  # authors for full confidence of a feature


@cache
def trips() -> tuple[int, list[dict]]:
    raw = yaml.safe_load(TRIPS.read_text(encoding="utf-8"))
    out = list(raw["trips"])
    for i, (hard, soft) in enumerate(itertools.product(raw["cross"]["filters"], raw["cross"]["prefs"])):
        out.append({"id": f"cross_{i}", "role": "experience", "hard": hard, "soft": soft})
    return raw["shortlist"], out


def confidence(f: dict) -> float:
    c = f["confidence"]
    base = c["agreement"] * min(1.0, f["n"] / CONFIDENCE_N)
    return base * (1.0 if f["status"] == "VERIFIED" else 0.7 if f["status"] == "OUTDATED" else 0.5)


def score(rec: dict, soft: dict) -> float:
    """Σ weight · has(feature) · confidence − uncertainty (wanted features without evidence), in [−1, 1]."""
    total = sum(soft.values()) or 1.0
    fit = missing = 0.0
    for fid, w in soft.items():
        f = feature(rec, fid)
        if f is None:
            missing += w
        elif f["value"] in GOOD:
            fit += w * confidence(f)
    return (fit - 0.2 * missing) / total


def violates(rec: dict, fid: str, forbidden: str) -> bool:
    f = feature(rec, fid)
    return bool(f) and f["distribution"].get(forbidden, 0) > 0


def screen(records: list[dict], trip: dict) -> tuple[list[dict], list[dict], int]:
    main, unverified, out = [], [], 0
    for rec in records:
        if trip["role"] not in rec["usable_as"]:
            continue
        results = [check(rec, fid, value) for fid, value in trip["hard"].items()]
        if "fail" in results:
            out += 1
        elif "unknown" in results:
            unverified.append(rec)
        else:
            main.append(rec)
    return main, unverified, out


def shortlist(records: list[dict], trip: dict, k: int) -> tuple[list[str], dict]:
    main, unverified, out = screen(records, trip)
    scores = {r["id"]: score(r, trip["soft"]) for r in main}
    ranked = sorted(main, key=lambda r: -scores[r["id"]])[: k * 5]  # MMR over the head only
    return mmr(ranked, scores, k), {"main": len(main), "unverified": len(unverified), "excluded": out}


def evaluate(records: list[dict] | None = None) -> dict:
    records = records if records is not None else load()
    k, all_trips = trips()
    by_id = {r["id"]: r for r in records}
    group_of = {rid: i for i, ids in enumerate(near_duplicate_groups(records)) for rid in ids}
    rows = []
    for trip in all_trips:
        picked, counts = shortlist(records, trip, k)
        recs = [by_id[i] for i in picked]
        violations = [r["id"] for r in recs for fid, v in trip["hard"].items() if violates(r, fid, v)]
        unknown = [r["id"] for r in recs if any(check(r, fid, v) != "pass" for fid, v in trip["hard"].items())]
        pairs = list(itertools.combinations(picked, 2))
        dup = sum(1 for a, b in pairs if a in group_of and group_of.get(a) == group_of.get(b))
        rows.append({"trip": trip["id"], "shortlist": picked, "names": [r["identity"]["name"] for r in recs],
                     **counts, "violations": violations, "unknown_in_main": unknown,
                     "near_duplicate_rate": round(dup / len(pairs), 3) if pairs else 0.0, "filled": len(picked) >= k})
    n = len(rows)
    summary = {"trips": n, "shortlist": k,
               "violations": sum(len(r["violations"]) for r in rows),
               "unknown_in_main": sum(len(r["unknown_in_main"]) for r in rows),
               "near_duplicate_rate": round(sum(r["near_duplicate_rate"] for r in rows) / n, 3) if n else 0.0,
               "filled_rate": round(sum(r["filled"] for r in rows) / n, 3) if n else 0.0,
               "unfilled_trips": [r["trip"] for r in rows if not r["filled"]]}
    return {"summary": summary, "trips": rows}


def run(city: str) -> dict:
    res = evaluate()
    write_json(data_dir() / "serving" / "eval.json", {"at": now(), **res})
    print(f"evaluate {city}: {json.dumps(res['summary'], ensure_ascii=False)}")
    return res
