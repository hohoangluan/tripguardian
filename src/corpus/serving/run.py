"""Build every serving record from data/intel/places/ into data/serving/places.json (one file, one build)."""

import collections
import json
from datetime import date

import yaml

from ..crawl.common.files import ROOT, data_dir, now, write_json
from ..judge import place_verdicts
from ..review import label_stats
from .groups import areas, km, near_duplicate_groups
from . import dishes
from .details import finish
from .record import SERVED, build, config


def stay_outside(rec: dict, cities: dict) -> bool:
    """A lodging inside a city's area but farther from its centre than `stay_within` (config/cities.yaml): a trip to
    the city never sleeps there."""
    ident = rec["identity"]
    lat, lng = ident.get("lat"), ident.get("lng")
    if ident.get("category_group") != "stay" or lat is None or lng is None:
        return False
    for c in cities.values():
        a, w = c.get("area"), c.get("stay_within")
        if a and w and a[0] <= lat <= a[2] and a[1] <= lng <= a[3]:
            return km({"lat": lat, "lng": lng}, w) > w["km"]
    return False


def run(city: str, *, root=None, source_root=None, publish=True) -> dict:
    """city is accepted for a uniform CLI; intel is already per place."""
    root = root or data_dir()
    source_root = source_root or root
    built = date.today()
    records, disabled, excluded = [], collections.Counter(), []
    judged = place_verdicts(root=source_root)
    quality = {(r["feature"], r["value"]): {k: r[k] for k in ("precision", "lower", "correct", "wrong", "gate")}
               for r in label_stats(root=source_root)["rows"] if r["correct"] + r["wrong"]}
    cities = yaml.safe_load((ROOT / "config" / "cities.yaml").read_text(encoding="utf-8"))
    for p in sorted((root / "intel" / "places").glob("*.json")):
        intel = json.loads(p.read_text(encoding="utf-8"))
        rec = build(intel, built, judged.get(intel["place_fid"]), quality)
        reason = rec["status_reason"] if rec["status"] == "DISABLED" else "stay_outside_city" if stay_outside(rec, cities) else None
        if reason:
            disabled[reason] += 1
            excluded.append({"id": rec["id"], "reason": reason})
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
    with_menu = dishes.attach(records, source_root)
    status = collections.Counter(f["status"] for r in records for g in ("experience", "environment", "service",
                                                                         "effort", "suitability")
                                 for f in r.get(g, {}).values())
    summary = {"at": now(), "places": len(records), "disabled": dict(disabled), "excluded": excluded,
               "uncertain_places": sum(r["status"] == "UNCERTAIN" for r in records), "areas": len(set(area.values())),
               "near_duplicate_groups": len(groups), "in_groups": len(of), "feature_status": dict(status),
               "usable_as": dict(collections.Counter(u for r in records for u in r["usable_as"])),
               "menu": with_menu, "details": {"known_for": sum(bool(r["details"]["known_for"]["headline"]) for r in records),
                           "cost_total": sum(bool((r["details"]["cost"] or {}).get("total_vnd")) for r in records),
                           "best_time": sum(bool(r["details"]["timing"]["best_time"]["items"]) for r in records),
                           "fit": sum(bool(r["details"]["fit"]) for r in records)}}
    write_json(root / "serving" / "places.json", {"built_at": now(), "summary": summary, "records": records})
    print(f"serving {city}: {json.dumps(summary, ensure_ascii=False)}")
    from ..snapshot import compile_snapshot  # inside the function: snapshot imports serving
    compile_snapshot(city, root, source_root=source_root, publish=publish)
    return summary


def load(region: str | None = None) -> list[dict]:
    """The records online serves (data/snapshot/current); never NEEDS_REVIEW / DISABLED."""
    from ..snapshot import shared
    return [r for r in shared().region(region).records() if r["status"] in SERVED]
