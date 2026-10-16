"""Dish lookup: "which places serve bánh bèo / sữa đậu nành / bánh canh" (data/gmaps/places/*/menu.json -> record["menu"]).

A dish name is matched as a whole phrase after folding case, accents and `đ` ("Bánh Bèo" == "banh beo"), so
"bánh canh" finds "Bánh canh giò heo" but "canh" alone finds "Canh chua", never "Bánh canh" by substring of a word.
The owner's own dish list (the Maps menu tab) is evidence from the place itself; the dishes review authors say to
order (`details.order`) are a second, weaker source. A dish nobody wrote down is `unknown`, not absent.

`attach(records)` adds `menu` to each serving record that has dishes; `search(records, query)` ranks places.
"""

import json
import re
import unicodedata
from functools import cache

import yaml

from ..crawl.common.files import ROOT, data_dir, safe_name

ALIASES = ROOT / "config" / "dishes.yaml"
SOURCE_RANK = {"menu_popular": 3, "menu": 2, "review_order": 1}


def fold(text: str | None) -> str:
    """Lowercase, no accents, `đ` -> d, words joined by single spaces: the key two spellings of a dish share."""
    s = unicodedata.normalize("NFD", (text or "").casefold().replace("đ", "d"))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(re.findall(r"[a-z0-9]+", s))


def keep(text: str | None) -> str:
    """Case-folded words with the accents kept: "phở" != "phô" (fold would join them)."""
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFC", (text or "").casefold())))


def key_for(text: str | None, accented: bool) -> str:
    return keep(text) if accented else fold(text)


@cache
def groups() -> list[list[str]]:
    """config/dishes.yaml `same`: lists of phrases that are one dish."""
    if not ALIASES.exists():
        return []
    return (yaml.safe_load(ALIASES.read_text(encoding="utf-8")) or {}).get("same") or []


def phrases(query: str) -> tuple[frozenset[str], bool]:
    """(wanted keys, accented). A query typed with accents ("phở") is compared with accents kept, one without
    ("pho", "banh beo") compared folded: folding alone would make "phở" find "phô mai"."""
    k = fold(query)
    if not k:
        return frozenset(), False
    accented = keep(query) != k
    same = {query}
    for g in groups():
        if k in {fold(x) for x in g}:
            same.update(g)
    return frozenset(key_for(x, accented) for x in same), accented


def has_phrase(haystack: str, needle: str) -> bool:
    """needle as whole words inside haystack (both already keyed the same way)."""
    return f" {needle} " in f" {haystack} "


def menu_of(doc: dict) -> dict | None:
    """The served `menu` block of one menu.json, or None when the place has no dish list and no menu photo."""
    if not doc.get("has_menu_tab"):
        return None
    dishes, seen = [], set()

    def add(item: dict, section: str | None, popular: bool) -> None:
        key = fold(item.get("name"))
        if key and key not in seen:
            seen.add(key)
            dishes.append({k: v for k, v in {"name": item["name"], "name_en": item.get("name_en"), "section": section,
                                              "popular": popular, "price": item.get("price")}.items() if v})

    for it in doc.get("highlights") or []:
        add(it, None, bool(it.get("popular")))
    for sec in doc.get("sections") or []:
        for it in sec.get("items") or []:
            add(it, sec["name"], bool(it.get("popular")))
    photos = [p["file"] for p in doc.get("photos") or []]
    if not dishes and not photos:
        return None
    return {"dishes": dishes, "photos": photos, "fetched_at": doc.get("fetched_at")}


def attach(records: list[dict], root=None) -> int:
    """Set record["menu"] from each place's menu.json; returns how many records got one."""
    base = (root or data_dir()) / "gmaps" / "places"
    n = 0
    for rec in records:
        f = base / safe_name(rec["id"]) / "menu.json"
        menu = menu_of(json.loads(f.read_text(encoding="utf-8"))) if f.exists() else None
        rec["menu"] = menu
        if menu:
            rec["menu"]["photos"] = [f"gmaps/places/{safe_name(rec['id'])}/{p}" for p in menu["photos"]]
            n += 1
    return n


def matches(record: dict, wanted: frozenset[str], accented: bool = False) -> list[dict]:
    """Every way this place serves one of the wanted phrases: {source, dish, section?}."""
    found = []
    for d in (record.get("menu") or {}).get("dishes") or []:
        for text in (d["name"], d.get("name_en")):
            if text and any(has_phrase(key_for(text, accented), w) for w in wanted):
                found.append({"source": "menu_popular" if d.get("popular") else "menu", "dish": d["name"],
                              **({"section": d["section"]} if d.get("section") else {})})
                break
    for o in ((record.get("details") or {}).get("order") or []):
        if any(has_phrase(key_for(o.get("text"), accented), w) for w in wanted):
            found.append({"source": "review_order", "dish": o["text"], "n": o.get("n")})
    return found


def search(records: list[dict], query: str, limit: int = 20) -> list[dict]:
    """Places that serve the dish, best first: owner-listed popular > owner-listed > review authors' orders.
    [{id, name, score, evidence:[{source, dish, ...}]}]; [] when nothing was written down (that is not "none")."""
    wanted, accented = phrases(query)
    if not wanted:
        return []
    hits = []
    for r in records:
        ev = matches(r, wanted, accented)
        if ev:
            score = max(SOURCE_RANK[e["source"]] for e in ev) * 100 + min(len(ev), 9) * 10 + min(
                sum(e.get("n") or 0 for e in ev), 9)
            hits.append({"id": r["id"], "name": r["identity"]["name"], "score": score, "evidence": ev})
    return sorted(hits, key=lambda h: -h["score"])[:limit]
