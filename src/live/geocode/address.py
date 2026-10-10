"""Address-shaped searches ("55/13/19 đường 18b, Bình Hưng Hòa, tphcm") on top of geosearch.

OSM maps the street and often the alley, rarely the house. A text that starts with a house number is therefore answered
by the deepest thing the map holds: the alley "55/13", else "55", else the street. That row stands in for the address as
a first row marked `approx` with the typed text as its name and the real row's point; the real rows follow. Nothing is
made up: the point is always one a source returned, and a full match is never marked approximate.
"""

import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor

from ..http import Unavailable
from ..settings import Settings
from .photon import geosearch as photon_search

HOUSE = re.compile(r"^\s*(?:(?:số|so|sn|no)\.?\s+)?(?:(?:hẻm|hem|ngõ|ngo|kiệt|ngách|ngach)\s+)?"
                   r"(\d+[a-z]?(?:/\d+[a-z]?)*)(?=[\s,]|$)[\s,]*(.*)$", re.IGNORECASE)
NUMBER = re.compile(r"\d+[a-z]?(?:/\d+[a-z]?)*")
ALIASES = ((re.compile(r"\b(?:tp\.?\s*hcm|hcmc|hcm)\b", re.IGNORECASE), "Hồ Chí Minh"),
           (re.compile(r"\b(?:tp\.?\s*hn|hn)\b", re.IGNORECASE), "Hà Nội"))
GENERIC = {"duong", "pho", "hem", "ngo", "kiet", "ngach", "so", "phuong", "xa", "quan", "huyen", "thanh", "tinh", "tp",
           "p", "q", "viet", "nam"}  # say what kind of place, not which
MAX_DROPPED = 2  # trailing "ward, city" segments a text without a match may lose


def _fold(text: str) -> str:
    t = unicodedata.normalize("NFD", (text or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in t if unicodedata.category(c) != "Mn").casefold()


def _tokens(text: str) -> list[str]:
    return [t for t in re.sub(r"[^a-z0-9]+", " ", _fold(text)).split() if t not in GENERIC]


def normalize(text: str) -> str:
    q = " ".join((text or "").split())
    for pattern, full in ALIASES:
        q = pattern.sub(full, q)
    return q


def _chain(row: dict) -> list[str]:
    """The house / alley number a row is named by: "Hẻm 55/13 Đường 18B" -> ["55", "13"]; a street number of its own
    ("Đường 18B") is not one, so only a number that is not the name's last word-with-letters counts."""
    for part in (row["text"], (row.get("address") or "").split(",")[0]):
        m = NUMBER.search(_fold(part))
        if m and not re.search(r"(?:duong|pho|so)\s+" + re.escape(m[0]) + r"\b", _fold(part)):
            return m[0].split("/")
    return []


def _depth(typed: list[str], row: dict) -> int:
    got = _chain(row)
    n = 0
    for a, b in zip(typed, got):
        if a.casefold() != b:
            break
        n += 1
    return n if n == len(got) else 0  # a row naming more than was typed ("55/13/2" for "55/13/19") is another alley


def _near(search, q: str, cfg: Settings, limit: int) -> list[dict]:
    try:
        return search(q, cfg, limit)
    except Unavailable:
        return []


def _first(search, q: str, cfg: Settings, limit: int) -> list[dict]:
    """The text as typed; when nothing matches, without its last "ward, city" segments. Raises Unavailable only when
    the typed text itself cannot be asked."""
    rows = search(q, cfg, limit)
    parts = q.split(",")
    for k in range(1, min(MAX_DROPPED, len(parts) - 1) + 1):
        if rows:
            break
        rows = _near(search, ",".join(parts[:-k]).strip(), cfg, limit)
    return rows


def search(text: str, cfg: Settings, limit: int = 6, search=photon_search) -> list[dict]:
    q = normalize(text)
    if len(q) < 2:
        return []
    rows = _first(search, q, cfg, limit)
    m = HOUSE.match(q)
    if not m:
        return rows
    chain, rest = m[1].split("/"), m[2].strip()
    street = _tokens(rest.split(",")[0])
    if not street:
        return rows
    where = set(_tokens(",".join(rest.split(",")[1:])))

    def eligible(r: dict) -> bool:
        have = set(_tokens(f"{r['text']} {r.get('address') or ''}"))
        return all(t in have for t in street)

    def score(r: dict) -> tuple[int, int]:
        have = set(_tokens(f"{r['text']} {r.get('address') or ''}"))
        return _depth(chain, r), len(where & have)

    best = max((score(r) for r in rows if eligible(r)), default=(0, 0))
    levels = [f"{'/'.join(chain[:k])} {rest}" for k in range(len(chain) - 1, best[0], -1) if k >= 1]
    if best[0] == 0 and not any(eligible(r) for r in rows):
        levels.append(rest)
    if levels:
        with ThreadPoolExecutor(max_workers=len(levels)) as pool:
            for more in pool.map(lambda lv: _near(search, lv, cfg, limit), levels):
                rows = rows + [r for r in more if (r["text"], r["address"]) not in {(x["text"], x["address"]) for x in rows}]
    fits = sorted((r for r in rows if eligible(r)), key=score, reverse=True)
    if not fits:
        return rows
    top = fits[0]
    rest_rows = fits + [r for r in rows if r not in fits]
    if _depth(chain, top) == len(chain):  # the house itself is on the map
        return rest_rows[:limit]
    lead = {**top, "text": " ".join(text.split()), "address": ", ".join(x for x in (top["text"], top.get("address")) if x),
            "approx": True}
    return [lead, *rest_rows[:limit - 1]]
