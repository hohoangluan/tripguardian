"""Place name or link -> catalog place (docs/PLACE_DECISION.md §4). Port of web/src/user/search.ts."""

import re

from ..infrastructure.catalog import Candidate, Catalog
from .state import Anchor
from .text import squash

STOP = {"quan", "tiem", "cafe", "ca", "phe", "coffee", "nha", "hang", "the", "va", "cua"}
CITY = re.compile(r"\b(da lat|dalat|tp|thanh pho)\b")
URL = re.compile(r"https?://\S+")
FID = re.compile(r"0x[0-9a-f]+:0x[0-9a-f]+", re.I)
VIDEO = re.compile(r"/video/(\d+)")


def _name(s: str) -> str:
    return " ".join(CITY.sub(" ", squash(s)).split())


def _tokens(s: str) -> list[str]:
    return [t for t in _name(s).split() if len(t) > 1]


def score(q: str, name: str) -> float:
    """Token overlap on distinctive words; never a match on generic words alone."""
    qt, nt = _tokens(q), set(_tokens(name))
    if not qt:
        return 0.0
    fq, fn = _name(q), _name(name)
    if fq == fn:
        return 1.0
    hits = [t for t in qt if t in nt]
    if not [t for t in hits if t not in STOP]:
        return 0.0
    s = len(hits) / max(len(qt), len(nt))
    if fq in fn or fn in fq:
        s = max(s, 0.8)
    return s


def search(q: str, catalog: Catalog, limit: int = 6) -> list[Candidate]:
    if len(squash(q)) < 2:
        return []
    fq = _name(q)
    ranked = sorted(((score(q, p.name) + (0.3 if _name(p.name).startswith(fq) else 0.0), p.id, p)
                     for p in catalog.places), key=lambda x: (-x[0], x[1]))
    return [p for s, _, p in ranked if s > 0.2][:limit]


def link_place(url: str, catalog: Catalog) -> str | None:
    m = FID.search(url)
    if m and m[0].lower() in catalog.by_id:
        return m[0].lower()
    m = VIDEO.search(url)
    return catalog.video_place.get(m[1]) if m else None


def anchor_for(text: str, catalog: Catalog) -> Anchor:
    text = text.strip()
    if URL.match(text):
        pid = link_place(text, catalog)
        return Anchor(text=text, place_id=pid, state="matched" if pid else "missing")
    ranked = sorted(((score(text, p.name), p.id) for p in catalog.places), key=lambda x: (-x[0], x[1]))
    ranked = [r for r in ranked if r[0] > 0.34]
    if not ranked:
        return Anchor(text=text, state="missing")
    s1, id1 = ranked[0]
    if s1 >= 0.8 and (len(ranked) == 1 or s1 - ranked[1][0] >= 0.25):
        return Anchor(text=text, place_id=id1, state="matched")
    return Anchor(text=text, state="choose", candidates=tuple(i for _, i in ranked[:3]))
