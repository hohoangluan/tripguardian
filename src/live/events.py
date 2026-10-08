"""Crowd periods and shop-closure periods from config/events.yaml (festivals, long holidays, Noel, Tết).

Hand-entered on purpose, like holidays.py: there is no source to fetch them from that this project trusts, and a wrong
festival date does more harm than a missing one. A date the file does not list has no known event; the file is the whole
truth, and the caller must not read "none" as "quiet".
"""

from datetime import date
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "config" / "events.yaml"
CROWD = ("busy", "peak")


def _as_date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


@cache
def _table(path: Path) -> tuple[dict, ...]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = []
    for e in doc.get("events") or []:
        start, end = _as_date(e["start"]), _as_date(e["end"])
        if end < start or e.get("crowd", "busy") not in CROWD:
            raise ValueError(f"bad event {e.get('name')!r} in {path.name}")
        out.append({"name": str(e["name"]), "start": start, "end": end, "crowd": e.get("crowd", "busy"),
                    "closure_risk": bool(e.get("closure_risk", False))})
    return tuple(out)


def events(dates: list[date], path: Path = PATH) -> dict[date, list[dict]]:
    """Only the dates inside a listed event: [{name, crowd: busy | peak, closure_risk}]."""
    table = _table(path)
    out = {}
    for d in dates:
        hit = [{"name": e["name"], "crowd": e["crowd"], "closure_risk": e["closure_risk"]}
               for e in table if e["start"] <= d <= e["end"]]
        if hit:
            out[d] = hit
    return out
