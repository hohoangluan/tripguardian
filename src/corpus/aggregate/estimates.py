"""Estimates of one place (docs/CORPUS.md §5): category group, visit time as a range, entry fee in VND.

config/category_defaults.yaml holds the per-category defaults. An estimate always says where it came from
(`source`): review evidence when enough people said it, the category default otherwise. Never a fact, never a hard
filter.
"""

import re
import statistics
from functools import cache

import yaml

from ..crawl.common.files import ROOT

PATH = ROOT / "config" / "category_defaults.yaml"

# 150k, 150.000đ, 160.000 đồng, 50 nghìn, 120.000 vnd; a bare number is no price
_VND = re.compile(r"(\d{1,3}(?:[.,]\d{3})+|\d{1,4})\s*(k\b|nghìn|ngàn|n\b|đ|đồng|vnđ|vnd|000)", re.I)
VND_MIN, VND_MAX = 5_000, 5_000_000


@cache
def defaults() -> dict:
    return yaml.safe_load(PATH.read_text(encoding="utf-8"))


def group(category: str | None) -> dict:
    c = (category or "").casefold()
    groups = defaults()["groups"]
    return next((g for g in groups if any(m in c for m in g["match"])), groups[-1])


def amounts_vnd(text: str) -> list[int]:
    out = []
    for num, unit in _VND.findall(text or ""):
        digits = int(re.sub(r"[.,]", "", num))
        unit = unit.casefold()
        value = digits * 1000 if unit in ("k", "nghìn", "ngàn", "n") else digits * 1000 if unit == "000" else digits
        if unit in ("đ", "đồng", "vnđ", "vnd") and digits < 1000:  # "50đ" in speech means 50k
            value = digits * 1000
        if VND_MIN <= value <= VND_MAX:
            out.append(value)
    return out


def entry_fee(observations: list[dict], ticket_usd: float | None = None) -> dict | None:
    """Ticket price from the entry_fee paid quotes (the highest amount of each quote: adults pay the most) or, without
    any, from the Maps ticket box (place_facts tickets, US$)."""
    by_author = {}
    for o in observations:
        if o["feature"] == "entry_fee" and o["value"] == "paid":
            found = amounts_vnd(o["span"]["quote"])
            if found:
                by_author[o.get("author") or o["id"]] = max(found)
    if by_author:
        xs = sorted(by_author.values())
        return {"min_vnd": xs[0], "typical_vnd": int(statistics.median(xs)), "max_vnd": xs[-1], "n": len(xs),
                "source": "reviews"}
    if ticket_usd:
        vnd = round(ticket_usd * defaults()["usd_vnd"], -3)
        return {"min_vnd": int(vnd), "typical_vnd": int(vnd), "max_vnd": int(vnd), "n": 1, "source": "maps_tickets"}
    return None


def visit_minutes(category: str | None, signal: dict | None) -> dict:
    """[short, typical, long] minutes. Review evidence wins when visit_duration has enough authors and agrees."""
    cfg = defaults()
    if signal and signal["n"] >= cfg["visit_duration_min_n"] and signal["status"] == "signal":
        lo, hi = cfg["visit_duration_minutes"][signal["top_value"]]
        return {"short": lo, "typical": (lo + hi) // 2, "long": hi, "source": "reviews", "n": signal["n"]}
    short, typical, long = group(category)["visit_minutes"]
    return {"short": short, "typical": typical, "long": long, "source": "category_default", "n": 0}


def estimates(category: str | None, features: dict, observations: list[dict], ticket_usd: float | None = None) -> dict:
    g = group(category)
    return {"category_group": g["id"], "usable_as_default": g["usable_as"], "effort_hint": g["effort_hint"],
            "visit_minutes": visit_minutes(category, features.get("visit_duration")),
            "entry_fee": entry_fee(observations, ticket_usd)}
