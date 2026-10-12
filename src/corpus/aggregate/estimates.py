"""Estimates of one place (docs/CORPUS.md §5): category group, visit time as a range, entry fee in VND.

config/category_defaults.yaml holds the per-category defaults. An estimate always says where it came from
(`source`): review evidence when enough people said it, the category default otherwise. Never a fact, never a hard
filter.
"""

import re
import statistics
from datetime import date, timedelta

from ..categories import defaults, group

# 150k, 150.000đ, 160.000 đồng, 50 nghìn, 120.000 vnd; a bare number is no price
_VND = re.compile(r"(\d{1,3}(?:[.,]\d{3})+|\d{1,4})\s*(k\b|nghìn|ngàn|n\b|đ|đồng|vnđ|vnd|000)", re.I)
VND_MIN, VND_MAX = 5_000, 5_000_000



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


TICKET = re.compile(r"vé|vào cổng|vào cửa|phí vào|phí tham quan|tham quan|cổng|ticket|entrance|admission|entry", re.I)
NOT_TICKET = re.compile(r"chụp|quay phim|gửi xe|giữ xe|đậu xe|thuê|massage|gội|/\s*kg|\d\s*kg", re.I)
CLAUSE = re.compile(r"[;\n]|[,.](?=\s)| - ")  # "160.000" and "50,000" stay whole
RECENT_DAYS = 730  # prices change: when enough recent quotes exist, older ones are left out
RECENT_MIN = 2


def ticket_amounts(quote: str) -> list[int]:
    """Amounts said next to a ticket word, clause by clause; a clause about photos, parking, rentals, a massage or
    food by weight is not an entry price."""
    out = []
    for clause in CLAUSE.split(quote or ""):
        if TICKET.search(clause) and not NOT_TICKET.search(clause):
            out += amounts_vnd(clause)
    return out


def entry_fee(observations: list[dict], ticket_usd: float | None = None,
              official: dict | None = None) -> dict | None:
    """Ticket price from the place's own website (official: {adult: [...], child: [...]} VND; typical = the median
    adult ticket, as sites also list combos and tours; min = the lowest ticket of anyone), else from the entry_fee paid quotes (per author the highest ticket amount: adults pay the most), the
    last RECENT_DAYS only when RECENT_MIN authors said it then, or, without any, from the Maps ticket box (US$)."""
    adult = (official or {}).get("adult") or []
    if adult:
        every = adult + ((official or {}).get("child") or [])
        return {"min_vnd": min(every), "typical_vnd": int(statistics.median_low(adult)), "max_vnd": max(adult), "n": len(adult),
                "source": "official"}
    found = {}
    for o in observations:
        if o["feature"] == "entry_fee" and o["value"] == "paid":
            xs = ticket_amounts(o["span"]["quote"])
            if xs:
                who = o.get("author") or o["id"]
                found[who] = max(found.get(who, (0, ""))[0], max(xs)), max(found.get(who, (0, ""))[1], o.get("observed_at") or "")
    if found:
        newest = max(d for _, d in found.values())
        if newest:
            cut = (date.fromisoformat(newest) - timedelta(days=RECENT_DAYS)).isoformat()
            recent = {w: v for w, v in found.items() if v[1] >= cut}
            found = recent if len(recent) >= RECENT_MIN else found
        xs = sorted(v for v, _ in found.values())
        return {"min_vnd": xs[0], "typical_vnd": int(statistics.median(xs)), "max_vnd": xs[-1], "n": len(xs),
                "source": "reviews"}
    if ticket_usd:
        vnd = round(ticket_usd * defaults()["usd_vnd"], -3)
        return {"min_vnd": int(vnd), "typical_vnd": int(vnd), "max_vnd": int(vnd), "n": 1, "source": "maps_tickets"}
    return None


def visit_minutes(category: str | None, signal: dict | None, time_spent: dict | None = None) -> dict:
    """[short, typical, long] minutes. Maps' "people typically spend" (many visitors' time on site) wins; then review
    evidence when visit_duration has enough authors and agrees; then the category default."""
    cfg = defaults()
    if time_spent:
        lo, hi = time_spent["min_minutes"], time_spent["max_minutes"]
        return {"short": lo, "typical": (lo + hi) // 2, "long": hi, "source": "maps_time_spent", "n": 0}
    if signal and signal["n"] >= cfg["visit_duration_min_n"] and signal["status"] == "signal":
        lo, hi = cfg["visit_duration_minutes"][signal["top_value"]]
        return {"short": lo, "typical": (lo + hi) // 2, "long": hi, "source": "reviews", "n": signal["n"]}
    short, typical, long = group(category)["visit_minutes"]
    return {"short": short, "typical": typical, "long": long, "source": "category_default", "n": 0}


def estimates(category: str | None, features: dict, observations: list[dict], ticket_usd: float | None = None,
              official_tickets: dict | None = None, time_spent: dict | None = None) -> dict:
    g = group(category)
    return {"category_group": g["id"], "usable_as_default": g["usable_as"], "effort_hint": g["effort_hint"],
            "visit_minutes": visit_minutes(category, features.get("visit_duration"), time_spent),
            "entry_fee": entry_fee(observations, ticket_usd, official_tickets)}
