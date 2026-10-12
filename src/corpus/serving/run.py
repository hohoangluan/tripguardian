"""Build every serving record from data/intel/places/ into data/serving/places.json (one file, one build)."""

import collections
import json
from datetime import date

from ..crawl.common.files import data_dir, now, write_json
from ..judge import place_verdicts
from ..review import label_stats
from .groups import areas, near_duplicate_groups
from .details import finish
from .record import SERVED, build, config


def run(city: str) -> dict:
    """city is accepted for a uniform CLI; intel is already per place."""
    root = data_dir()
    built = date.today()
    records, disabled = [], collections.Counter()
    judged = place_verdicts()
    quality = {(r["feature"], r["value"]): {k: r[k] for k in ("precision", "lower", "correct", "wrong", "gate")}
               for r in label_stats()["rows"] if r["correct"] + r["wrong"]}
    for p in sorted((root / "intel" / "places").glob("*.json")):
        intel = json.loads(p.read_text(encoding="utf-8"))
        rec = build(intel, built, judged.get(intel["place_fid"]), quality)
        if rec["status"] == "DISABLED":
            disabled[rec["status_reason"]] += 1
            continue
        records.append(rec)
    area = areas(records)
    for rec in records:
        rec["identity"]["area"] = area.get(rec["id"])
    groups = near_duplicate_groups(records)
    of = {rid: i for i, ids in enumerate(groups) for rid in ids}
    for rec in records:
        rec["near_duplicate_group"] = of.get(rec["id"])
    finish(records, config()["details"])
    status = collections.Counter(f["status"] for r in records for g in ("experience", "environment", "service",
                                                                         "effort", "suitability")
                                 for f in r.get(g, {}).values())
    summary = {"at": now(), "places": len(records), "disabled": dict(disabled),
               "uncertain_places": sum(r["status"] == "UNCERTAIN" for r in records), "areas": len(set(area.values())),
               "near_duplicate_groups": len(groups), "in_groups": len(of), "feature_status": dict(status),
               "usable_as": dict(collections.Counter(u for r in records for u in r["usable_as"])),
               "details": {"known_for": sum(bool(r["details"]["known_for"]["headline"]) for r in records),
                           "cost_total": sum(bool((r["details"]["cost"] or {}).get("total_vnd")) for r in records),
                           "best_time": sum(bool(r["details"]["timing"]["best_time"]["items"]) for r in records),
                           "fit": sum(bool(r["details"]["fit"]) for r in records)}}
    write_json(root / "serving" / "places.json", {"built_at": now(), "summary": summary, "records": records})
    print(f"serving {city}: {json.dumps(summary, ensure_ascii=False)}")
    return summary


def load() -> list[dict]:
    """The records of the last build; never NEEDS_REVIEW / DISABLED."""
    doc = json.loads((data_dir() / "serving" / "places.json").read_text(encoding="utf-8"))
    return [r for r in doc["records"] if r["status"] in SERVED]
