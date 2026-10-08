"""Hazard notices (storm, flood, landslide, fire, closed road) from config/advisories.yaml.

Entered by hand from an official notice, each with its source. There is no automatic feed yet, so an empty result means
"no notice in our data", never "safe": Planning words it that way. Nothing here invents or softens a notice.
"""

from datetime import date
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "config" / "advisories.yaml"
KINDS = ("storm", "flood", "landslide", "fire", "road_closed", "other")
SEVERITY = ("watch", "warning", "severe")


def _as_date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def _area(a) -> dict | str:
    if a in (None, "city"):
        return "city"
    return {"lat": float(a["lat"]), "lng": float(a["lng"]), "radius_km": float(a["radius_km"])}


@cache
def _table(path: Path) -> tuple[dict, ...]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = []
    for a in doc.get("advisories") or []:
        if a["kind"] not in KINDS or a["severity"] not in SEVERITY or not a.get("source"):
            raise ValueError(f"bad advisory {a.get('note')!r} in {path.name}: kind, severity and source are required")
        out.append({"kind": a["kind"], "severity": a["severity"], "start": _as_date(a["start"]),
                    "end": _as_date(a["end"]), "area": _area(a.get("area")), "note": str(a.get("note", "")),
                    "source": str(a["source"]), "issued": str(a["issued"]) if a.get("issued") else None})
    return tuple(out)


def advisories(dates: list[date], path: Path = PATH) -> dict[date, list[dict]]:
    """Only the dates a notice covers: [{kind, severity, area: "city" | {lat, lng, radius_km}, note, source, issued}]."""
    table = _table(path)
    out = {}
    for d in dates:
        hit = [{k: a[k] for k in ("kind", "severity", "area", "note", "source", "issued")}
               for a in table if a["start"] <= d <= a["end"]]
        if hit:
            out[d] = hit
    return out
