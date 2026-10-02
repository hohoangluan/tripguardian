"""Monthly rain climate for dates beyond Open-Meteo's forecast horizon (config/climate.yaml, hand-entered)."""

from datetime import date
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "config" / "climate.yaml"


@cache
def _table(path: Path) -> dict[int, float]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {int(k): float(v) for k, v in (doc.get("rain_prob_by_month") or {}).items()}


def climate(dates: list[str], path: Path = PATH) -> dict:
    """{"YYYY-MM-DD": {"rain_prob", "source": "climate", "fetched_at": None}}; a month missing from the file is None."""
    table = _table(path)
    return {d: {"rain_prob": table.get(date.fromisoformat(d).month), "source": "climate", "fetched_at": None}
            for d in dates}
