"""Place name or link -> catalog place (docs/PLACE_DECISION.md §4). Port of web/src/user/search.ts."""

import re
from corpus.retrieval import NameRecord, name_score, search_names as corpus_search_names

from ..infrastructure.catalog import Candidate, Catalog
from .state import Anchor
from .text import squash

URL = re.compile(r"https?://\S+")
FID = re.compile(r"0x[0-9a-f]+:0x[0-9a-f]+", re.I)
VIDEO = re.compile(r"/video/(\d+)")


def score(q: str, name: str) -> float:
    """Token overlap on distinctive words; never a match on generic words alone."""
    return name_score(q, name)


def search(q: str, catalog: Catalog, limit: int = 6) -> list[Candidate]:
    if len(squash(q)) < 2:
        return []
    records = (NameRecord(p.id, p.name, p.category_group) for p in catalog.places)
    hits = corpus_search_names(q, records, within=set(catalog.by_id),
                               release_id=catalog.release_id, limit=limit)
    return [catalog.by_id[h.place_id] for h in hits if h.place_id in catalog.by_id]


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
