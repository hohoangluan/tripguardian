"""Turn the agent's / the screen's string values into typed values for apply()."""

import re
from datetime import date
from typing import Any

from pydantic import BaseModel

from .catalog import Catalog
from .resolve import anchor_for
from .state import Base, SoftKey, ontology
from .text import fold

MONEY = re.compile(r"(\d+(?:[.,]\d+)?)\s*(k|nghin|ngan|tr|trieu|cu)?")
LITERALS = ("companions", "mobility", "purpose", "pace", "novelty", "crowd_tolerance", "signal")


def clock(raw: str) -> str:
    m = re.fullmatch(r"\s*(\d{1,2})\s*(?:[:h]\s*(\d{2})?)?\s*", raw.lower())
    if not m or int(m[1]) > 23 or int(m[2] or 0) > 59:
        raise ValueError(f"not a time: {raw!r}")
    return f"{int(m[1]):02d}:{int(m[2] or 0):02d}"


def money(raw: str) -> int:
    m = MONEY.search(fold(raw))
    if not m:
        raise ValueError(f"not an amount: {raw!r}")
    n = float(m[1].replace(",", "."))
    unit = m[2]
    return int(n * 1000 if unit in ("k", "nghin", "ngan") else n * 1_000_000 if unit in ("tr", "trieu", "cu") else n)


def split_weight(raw: str) -> tuple[str, str]:
    """'crowd=low:avoid' and the model's habit 'crowd=low@avoid' -> ('crowd=low', 'avoid'); no weight = love."""
    m = re.fullmatch(r"(.+?)[:@](love|avoid|off)", raw.strip())
    return (m[1], m[2]) if m else (raw.strip(), "love")


def parse(field: str, raw: str, catalog: Catalog) -> Any:
    raw = raw.strip()
    if not raw:
        raise ValueError(f"{field}: empty value")
    if field == "start_date":
        return date.fromisoformat(raw[:10])
    if field in ("month", "days", "people", "max_leg_min"):
        m = re.search(r"\d+", raw)
        if not m:
            raise ValueError(f"{field}: no number in {raw!r}")
        return int(m[0])
    if field == "budget_vnd":
        return money(raw)
    if field in ("arrive_at", "leave_at", "day_end"):
        return clock(raw)
    if field in ("base", "entry_point", "exit_point"):
        if raw in catalog.by_id:
            return Base(place_id=raw, text=catalog.by_id[raw].name)
        a = anchor_for(raw, catalog)
        return Base(place_id=a.place_id if a.state == "matched" else None, text=raw)
    if field == "anchor":
        return anchor_for(raw, catalog)
    if field == "soft":
        key, weight = split_weight(raw)
        return str(SoftKey.parse(key)), weight
    if field == "hard":
        m = re.fullmatch(r"\s*([a-z_]+)\s*(!=|=)\s*([a-z_0-9]+)\s*", raw)
        if not m or not ontology().valid(m[1], m[3]):
            raise ValueError(f"hard filter {raw!r} is not feature!=value from the ontology")
        return {"feature": m[1], "op": "ne" if m[2] == "!=" else "eq", "value": m[3]}
    if field in LITERALS:
        return raw.lower()
    if field == "unmapped":
        return raw
    raise ValueError(f"unknown field {field!r}")


def parse_remove(field: str, raw: str) -> Any:
    """What apply() needs to remove something the agent names."""
    raw = raw.strip()
    if field == "soft":
        return str(SoftKey.parse(split_weight(raw)[0]))
    if field == "hard":
        return re.split(r"!=|=", raw)[0].strip()
    if field in ("companions", "signal"):
        return raw.lower()
    raise ValueError(f"{field}: the agent cannot remove by name")


def jsonable(v: Any) -> Any:
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (frozenset, set)):
        return sorted(v)
    if isinstance(v, BaseModel):
        return v.model_dump(mode="json")
    if isinstance(v, (tuple, list)):
        return [jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    return v
