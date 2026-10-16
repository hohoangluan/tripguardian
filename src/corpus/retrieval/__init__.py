"""corpus.retrieval: public retrieval API for online modules (docs/plans/NORMALIZED_CORPUS_RAG_ONLINE_PROPOSAL.md §4–5).

Online only reads; offline writes the index/snapshot that this module wraps.
Every result carries release_id; every search respects the `within` scope.

Usage:
    from corpus.retrieval import RetrievalEngine
    engine = RetrievalEngine.open(release_id, region)
    hits = engine.semantic("quán có đèn lồng đỏ", within=allowed_ids)
"""

from .engine import (
    CoverageReport,
    EvidenceHit,
    NameHit,
    RetrievalEngine,
    SemanticHit,
    SimilarHit,
)

__all__ = [
    "CoverageReport",
    "EvidenceHit",
    "NameHit",
    "RetrievalEngine",
    "SemanticHit",
    "SimilarHit",
]

from .names import NameRecord, name_score, search_names

__all__ += ["NameRecord", "name_score", "search_names"]
