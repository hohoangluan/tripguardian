"""What a place the user compares to is like ("không thích quán giống X", "kiểu X"): its served features whose value
differs from what most places of its category have, strongest first. Read only from the catalog."""

from collections import Counter

from ..infrastructure.catalog import Candidate, Catalog
from .resolve import search
from .text import contains, fold

CUES = ("giong", "kieu", "nhu", "tuong tu")
MAX_PLACES, MAX_TRAITS = 2, 4


def _common(catalog: Catalog, category: str | None) -> dict[str, str]:
    """Most frequent served value per feature among places of this category (a few thousand places: no cache)."""
    counts: dict[str, Counter] = {}
    for p in catalog.places:
        if p.category == category:
            for f, k in p.known.items():
                counts.setdefault(f, Counter())[k.value] += 1
    return {f: c.most_common(1)[0][0] for f, c in counts.items()}


def traits(place: Candidate, catalog: Catalog) -> list[dict]:
    common = _common(catalog, place.category)
    out = [{"feature": f, "value": k.value, "n": k.n} for f, k in place.known.items()
           if k.value != "unknown" and common.get(f) != k.value]
    return sorted(out, key=lambda t: (-t["n"], t["feature"]))[:MAX_TRAITS]


def compared_places(text: str, catalog: Catalog) -> list[dict]:
    folded = fold(text)
    if not any(f" {c} " in f" {folded} " for c in CUES):
        return []
    out = []
    for c in CUES:
        i = f" {folded} ".find(f" {c} ")
        if i < 0:
            continue
        tail = " ".join(text.split()[len(folded[:i].split()) + len(c.split()):][:8])
        for p in search(tail, catalog, limit=1):
            if contains(text, p.name) and all(o["id"] != p.id for o in out):
                out.append({"id": p.id, "name": p.name, "traits": traits(p, catalog)})
    return out[:MAX_PLACES]
