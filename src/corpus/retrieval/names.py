"""Structured name retrieval over caller-supplied serving identities; no I/O or model."""

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

_STOP = {"quan", "tiem", "cafe", "ca", "phe", "coffee", "nha", "hang", "the", "va", "cua"}
_CITY = re.compile(r"\b(da lat|dalat|tp|thanh pho)\b")


@dataclass(frozen=True)
class NameRecord:
    place_id: str
    name: str
    category_group: str | None = None


@dataclass(frozen=True)
class NameHit:
    place_id: str
    name: str
    category_group: str | None
    match_type: str
    release_id: str | None


@lru_cache(maxsize=8192)
def _name(text: str) -> str:
    folded = "".join("d" if c.lower() == "đ" else unicodedata.normalize("NFD", c.lower())[0]
                     for c in unicodedata.normalize("NFC", text))
    return " ".join(_CITY.sub(" ", re.sub(r"[^a-z0-9]+", " ", folded)).split())


def name_score(query: str, name: str) -> float:
    """Distinctive token overlap; generic words alone cannot resolve an anchor."""
    fq, fn = _name(query), _name(name)
    qt, nt = tuple(t for t in fq.split() if len(t) > 1), {t for t in fn.split() if len(t) > 1}
    if not qt:
        return 0.0
    if fq == fn:
        return 1.0
    hits = [t for t in qt if t in nt]
    if not any(t not in _STOP for t in hits):
        return 0.0
    score = len(hits) / max(len(qt), len(nt))
    return max(score, 0.8) if fq in fn or fn in fq else score


def search_names(query: str, records: Iterable[NameRecord], *, within: set[str],
                 release_id: str | None, limit: int = 6) -> list[NameHit]:
    """Rank real serving names only inside the eligible scope, retaining caller lineage."""
    fq = _name(query)
    if len(fq) < 2 or not within or limit <= 0:
        return []
    ranked = []
    for record in records:
        if record.place_id not in within:
            continue
        fn = _name(record.name)
        prefix = fn.startswith(fq)
        score = name_score(query, record.name) + (0.3 if prefix else 0)
        if score <= 0.2:
            continue
        match = "exact" if fq == fn else "prefix" if prefix else "contains" if fq in fn else "tokens"
        hit = NameHit(record.place_id, record.name, record.category_group, match, release_id)
        ranked.append((score, record.place_id, hit))
    return [hit for _, _, hit in sorted(ranked, key=lambda row: (-row[0], row[1]))[:limit]]
