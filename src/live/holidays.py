"""Vietnamese public holidays from config/holidays.yaml.

Hand-entered on purpose: converting lunar dates would be a second calendar implementation, and the file is small.
A date the file does not list is not a holiday; the file is the whole truth.
"""

from datetime import date
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "config" / "holidays.yaml"


def _as_date(key) -> date:
    return key if isinstance(key, date) else date.fromisoformat(str(key))


@cache
def _table(path: Path) -> dict[date, str]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {_as_date(k): str(v) for k, v in (doc.get("holidays") or {}).items()}


def holidays(dates: list[date], path: Path = PATH) -> dict[date, str]:
    """Only the listed dates, mapped to the holiday's name."""
    table = _table(path)
    return {d: table[d] for d in dates if d in table}
