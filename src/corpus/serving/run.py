"""Build every serving record from data/intel/places/ into data/serving/places.json (one file, one build)."""

import collections
import json
from datetime import date

from ..crawl.common.files import data_dir, now, write_json
from ..review import decisions
from .groups import areas, near_duplicate_groups
from .record import SERVED, build


def run(city: str) -> dict:
    """city is accepted for a uniform CLI; intel is already per place."""
    root = data_dir()
    built = date.today()
    records, disabled = [], collections.Counter()
    judged = decisions("place_status")
    for p in sorted((root / "intel" / "places").glob("*.json")):
        intel = json.loads(p.read_text(encoding="utf-8"))
        rec = build(intel, built, judged.get(intel["place_fid"]))
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
    status = collections.Counter(f["status"] for r in records for g in ("experience", "environment", "service",
                                                                         "effort", "suitability")
                                 for f in r.get(g, {}).values())
    summary = {"at": now(), "places": len(records), "disabled": dict(disabled),
               "uncertain_places": sum(r["status"] == "UNCERTAIN" for r in records), "areas": len(set(area.values())),
               "near_duplicate_groups": len(groups), "in_groups": len(of), "feature_status": dict(status),
               "usable_as": dict(collections.Counter(u for r in records for u in r["usable_as"]))}
    write_json(root / "serving" / "places.json", {"built_at": now(), "summary": summary, "records": records})
    print(f"serving {city}: {json.dumps(summary, ensure_ascii=False)}")
    return summary


def load() -> list[dict]:
    """The records of the last build; never NEEDS_REVIEW / DISABLED."""
    doc = json.loads((data_dir() / "serving" / "places.json").read_text(encoding="utf-8"))
    return [r for r in doc["records"] if r["status"] in SERVED]
