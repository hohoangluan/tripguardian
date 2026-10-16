"""RetrievalEngine: public typed retrieval API for online modules.

Design: docs/plans/NORMALIZED_CORPUS_RAG_ONLINE_PROPOSAL.md §4–5.
Wraps corpus.index.Index and corpus.snapshot.Snapshot behind a scoped,
release-pinned, typed interface. Read-only and thread-safe once opened.

Semantic gap mitigation (§5):
  1. Hybrid query expansion: user text → bge-m3 dense + ontology feature name matching.
  2. Cross-modal: text → span space (bge-m3) AND photo space (SigLIP2), merged ranked.
  3. Feature-aware boost: query matches ontology hint → boost places with that feature.
  4. Unserved span access: mode="vibe" reads spans with served=False too.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Literal


from ..index import Index, PhotoHit, SpanHit
from ..ontology import Ontology, fold_text, load as load_ontology
from ..snapshot import Region, Snapshot, shared
from ..releases import Binding, bind, resolve_binding
from ..serving import feature as served_feature
from .names import NameHit, NameRecord, search_names


# ---------------------------------------------------------------------------
# Public result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SemanticHit:
    """A place ranked by semantic similarity (photo, span, or hybrid)."""
    place_id: str
    score: float
    channel: str  # "photo" | "span" | "hybrid"
    pointer: str | None  # file path (photo) or quote (span)
    served: bool
    release_id: str | None


@dataclass(frozen=True)
class SimilarHit:
    """A place visually similar to a reference place."""
    place_id: str
    score: float
    release_id: str | None


@dataclass(frozen=True)
class EvidenceHit:
    """A span that backs a served feature."""
    place_id: str
    observation_id: str | None
    quote: str
    features: tuple[str, ...]
    score: float
    release_id: str | None

    source: str | None = None
    feature: str | None = None
    value: str | None = None
    status: str = "unknown"
    context: dict | None = None
    observed_at: str | None = None
    source_id: str | None = None


@dataclass(frozen=True)
class CoverageReport:
    """How many of the requested places have photo/span/style coverage."""
    total: int
    with_photos: int
    with_spans: int
    with_styles: int
    missing_photos: tuple[str, ...]
    missing_spans: tuple[str, ...]
    release_id: str | None


# ---------------------------------------------------------------------------
# Ontology-based query expansion helpers (no model needed)
# ---------------------------------------------------------------------------

def _match_ontology(query: str, ont: Ontology) -> list[tuple[str, str, float]]:
    """Match user query words against ontology feature hints and values.

    Returns (feature_id, matched_value, confidence) for features whose hint
    or value name appears in the query text.  Confidence is 1.0 for exact
    value match, 0.7 for hint substring match.
    """
    q = fold_text(query)
    if not q:
        return []
    matches: list[tuple[str, str, float]] = []
    for feat in ont.features.values():
        # Check value names (e.g. "free" in "chỗ nào vào cửa free")
        for val in feat.values:
            val_fold = fold_text(val)
            if val_fold and len(val_fold) > 2 and re.search(rf"(?<!\w){re.escape(val_fold)}(?!\w)", q):
                matches.append((feat.id, val, 1.0))
        # Check hint keywords
        hint_fold = fold_text(feat.hint)
        if hint_fold:
            # Extract short phrases from the hint (before the first semicolon or slash)
            first_phrase = re.split(r"[;/]", hint_fold)[0].strip()
            words = [w for w in first_phrase.split() if len(w) > 2]
            for w in words:
                if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", q):
                    matches.append((feat.id, feat.values[0] if feat.values else "present", 0.7))
                    break
    return matches


# ---------------------------------------------------------------------------
# RetrievalEngine
# ---------------------------------------------------------------------------

@dataclass
class RetrievalEngine:
    """Opened once per release+region. Read-only. Thread-safe.

    All searches respect the ``within`` scope: no result ID outside it.
    Evidence comes only from served spans.  Semantic search returns score +
    pointer; it never promotes a hit to VERIFIED.  Every result carries
    ``release_id`` for lineage tracking.
    """
    _index: Index | None
    _snapshot: Snapshot
    _region: Region
    _ontology: Ontology
    release_id: str | None
    binding: Binding | None = None
    _index_data: Path | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # -- factory ----------------------------------------------------------

    @classmethod
    def open(cls, release_id: str | None = None, region: str | None = None,
             *, data_root=None, binding: Binding | None = None) -> RetrievalEngine:
        from .. import data_root as data_dir

        root = Path(data_root) if data_root is not None else data_dir()
        binding = binding or bind(root, region=region, release_id=release_id)
        if release_id is not None and binding.release_id != release_id:
            raise ValueError("release identity mismatch")
        if region is not None and binding.region != region:
            raise ValueError("release region mismatch")
        data = resolve_binding(root, binding)
        snapshot = shared(data / "snapshot", version=binding.snapshot_version)
        engine = cls.from_snapshot(snapshot, binding.region, binding=binding)
        engine._index_data = data
        return engine

    @classmethod
    def from_snapshot(cls, snapshot: Snapshot, region: str, *, binding: Binding,
                      index: Index | None = None) -> RetrievalEngine:
        if snapshot.version != binding.snapshot_version or region != binding.region:
            raise ValueError("snapshot binding mismatch")
        snapshot_root = Path(snapshot.root).resolve()
        if binding.release_id is not None and (
            snapshot_root.name != "snapshot" or snapshot_root.parent.name != binding.release_id
            or snapshot_root.parent.parent.name != "releases"
        ):
            raise ValueError("snapshot binding mismatch")
        reg = snapshot.region(region)
        if index is not None and (
            index.version != binding.index_version
            or Path(index.root).resolve() != snapshot_root.parent / "index" / index.version
        ):
            raise ValueError("index binding mismatch")
        return cls(index, snapshot, reg, load_ontology(), binding.release_id,
                   binding=binding, _index_data=snapshot.root.parent)

    def _reader(self) -> Index | None:
        if self._index is None and self.binding is not None and self.binding.index_version is not None:
            with self._lock:
                if self._index is None:
                    self._index = Index.load(self.binding.index_version, data=self._index_data)
        return self._index

    def _scope(self, within: set[str]) -> set[str]:
        return set(within).intersection(self._region.ids)

    def search_names(self, q: str, within: set[str], limit: int = 6) -> list[NameHit]:
        records = []
        for pid in self._region.ids:
            record = self._region.record(pid) or {}
            identity = record.get("identity", record)
            records.append(NameRecord(pid, identity.get("name", ""), identity.get("category_group")))
        return search_names(q, records, within=self._scope(within),
                            release_id=self.release_id, limit=max(0, limit))

    # -- get_place --------------------------------------------------------

    def get_place(self, place_id: str) -> dict | None:
        """The full serving record for a place, or None."""
        return self._region.record(place_id)

    # -- semantic search --------------------------------------------------

    def semantic(self, q: str | bytes, within: set[str],
                 mode: Literal["vibe", "evidence"] = "vibe",
                 limit: int | None = None) -> list[SemanticHit]:
        """Hybrid semantic search bridging the vocabulary gap.

        Parameters
        ----------
        q : str or bytes
            Text query or raw image bytes.
        within : set of str
            Scope: only these place IDs can appear in results.
        mode : "vibe" or "evidence"
            ``"vibe"``: reads all spans (including unserved vibe descriptions).
            ``"evidence"``: only spans backing served features.
        limit : int or None
            Max results.  Defaults to config ``k_spans``.

        Returns
        -------
        list of SemanticHit
            Merged, deduplicated, and scored.

        Semantic gap mitigation:
          1. **Cross-modal**: text → both span space (bge-m3) and photo space (SigLIP2).
          2. **Ontology feature boost**: if query words match ontology hints/values,
             places carrying that feature get a score boost.
          3. **Unserved spans**: mode="vibe" includes descriptive spans not gating
             any served feature after normalization validation.
        """
        within = self._scope(within)
        if not within or limit is not None and limit <= 0 or self._reader() is None:
            return []
        cfg = self._index.cfg
        limit = cfg["search"]["k_spans"] if limit is None else limit

        if isinstance(q, bytes):
            # Image query: photo space only
            vec = self._index.embed_image(q)
            photo_hits = self._index.search_photos(vec, k=limit, within=within)
            return self._photo_hits_to_semantic([h for h in photo_hits if h.place_id in within], limit)

        # Text query: both spaces
        text_vec = self._index.embed_text(q, spans=True)

        # Channel 1: span search (bge-m3 text→text)
        served_only = mode == "evidence"
        span_hits = self._index.search_spans(text_vec, k=limit, within=within,
                                              served_only=served_only)

        # Channel 2: photo search (SigLIP2 text→photo)
        photo_hits = self._index.search_photos(text_vec, k=limit, within=within)

        # Channel 3: ontology feature matching (no model)
        ont_matches = _match_ontology(q, self._ontology)
        ont_boost = self._ontology_boost(ont_matches, within)

        # Merge channels
        return self._merge_hits([h for h in span_hits if h.place_id in within],
                                [h for h in photo_hits if h.place_id in within], ont_boost, limit)

    def _photo_hits_to_semantic(self, hits: list[PhotoHit],
                                limit: int) -> list[SemanticHit]:
        """Deduplicate photo hits to one SemanticHit per place (best photo)."""
        seen: dict[str, SemanticHit] = {}
        for h in hits:
            if h.place_id not in seen:
                seen[h.place_id] = SemanticHit(
                    place_id=h.place_id, score=h.score, channel="photo",
                    pointer=h.file, served=True, release_id=self.release_id)
        return list(seen.values())[:limit]

    def _ontology_boost(self, matches: list[tuple[str, str, float]],
                        within: set[str] | None) -> dict[str, float]:
        """Places that carry a matched ontology feature get a boost score."""
        if not matches:
            return {}
        boost: dict[str, float] = {}
        for fid, value, confidence in matches:
            col = self._region.feature(fid)
            for i, pid in enumerate(self._region.ids):
                if within is not None and pid not in within:
                    continue
                if col.value[i] == value and col.firm[i]:
                    # Additive boost per matched feature
                    boost[pid] = boost.get(pid, 0.0) + 0.15 * confidence
        return boost

    def _merge_hits(self, span_hits: list[SpanHit], photo_hits: list[PhotoHit],
                    ont_boost: dict[str, float],
                    limit: int) -> list[SemanticHit]:
        """Merge span + photo + ontology channels into deduplicated SemanticHits.

        Reciprocal Rank Fusion (RRF): each place gets 1/(k+rank) from each channel.
        Ontology boost is additive on top of the RRF score.
        """
        K = 60  # RRF constant
        scores: dict[str, float] = {}
        channel: dict[str, str] = {}
        pointer: dict[str, str | None] = {}
        served: dict[str, bool] = {}

        # Span channel
        for rank, h in enumerate(span_hits):
            rrf = 1.0 / (K + rank)
            if h.place_id not in scores or rrf > scores[h.place_id]:
                pointer[h.place_id] = h.quote
                channel[h.place_id] = "span"
                served[h.place_id] = h.served
            scores[h.place_id] = scores.get(h.place_id, 0.0) + rrf

        # Photo channel
        for rank, h in enumerate(photo_hits):
            rrf = 1.0 / (K + rank)
            if h.place_id not in scores:
                pointer[h.place_id] = h.file
                channel[h.place_id] = "photo"
                served[h.place_id] = True
            elif rrf > 1.0 / (K + 0) * 0.5:
                # Photo contributes significantly — mark as hybrid
                channel[h.place_id] = "hybrid"
            scores[h.place_id] = scores.get(h.place_id, 0.0) + rrf

        # Ontology boost (additive, does not create new entries)
        for pid, boost in ont_boost.items():
            if pid in scores:
                scores[pid] += boost

        # Sort and limit
        ranked = sorted(scores.items(), key=lambda x: -x[1])[:limit]
        return [
            SemanticHit(pid, score, channel.get(pid, "hybrid"),
                        pointer.get(pid), served.get(pid, True),
                        self.release_id)
            for pid, score in ranked
        ]

    # -- similar places ---------------------------------------------------

    def similar(self, place_id: str, within: set[str],
                k: int = 12) -> list[SimilarHit]:
        """Visually similar places (photo vector centroid)."""
        within = self._scope(within)
        if place_id not in within or k <= 0 or self._reader() is None:
            return []
        hits = self._index.similar_places(place_id, k=k, within=within)
        return [SimilarHit(h.place_id, h.score, self.release_id) for h in hits if h.place_id in within][:k]

    # -- evidence ---------------------------------------------------------

    def evidence(self, place_id: str, feature: str, limit: int = 10,
                 *, context: dict | None = None) -> list[EvidenceHit]:
        """Return saved claims matching the currently served feature and context."""
        if limit <= 0 or place_id not in self._region.ids:
            return []
        record = self._region.record(place_id) or {}
        try:
            served = served_feature(record, feature)
        except KeyError:
            return []
        if context is not None:
            key = "|".join(f"{k}={v}" for k, v in sorted(context.items()))
            served = (served or {}).get("by_context", {}).get(key)
        if not served or served.get("value") is None or served.get("status") not in {"VERIFIED", "UNCERTAIN", "OUTDATED"}:
            return []
        if self._reader() is None:
            return []
        target = feature + "=" + str(served["value"])
        results = []
        for row in self._index.span_rows():
            if row.place_id != place_id or not row.served:
                continue
            if len(row.features) != len(row.observations):
                continue
            for oid, pair in zip(row.observations, row.features):
                if pair != target or not oid:
                    continue
                ids = served.get("evidence")
                if isinstance(ids, list) and ids and oid not in ids:
                    continue
                claim = next((c for c in row.claims if c.get("id") == oid
                              and c.get("feature") == feature and str(c.get("value")) == str(served["value"])), {})
                claim_context = claim.get("context")
                if context is not None and (not isinstance(claim_context, dict)
                    or any(claim_context.get(k) != v for k, v in context.items())):
                    continue
                results.append(EvidenceHit(place_id, oid, row.quote, (pair,), 1.0, self.release_id,
                    row.source, feature, str(served["value"]), served["status"], claim_context,
                    claim.get("observed_at"), claim.get("source_id")))
                if len(results) >= limit:
                    return results
        return results

    # -- coverage ---------------------------------------------------------

    def coverage(self, place_ids: set[str]) -> CoverageReport:
        """Coverage report: how many places have photo/span/style data."""
        place_ids = self._scope(place_ids)
        total = len(place_ids)
        if self._reader() is None:
            return CoverageReport(total, 0, 0, 0, tuple(sorted(place_ids)),
                                  tuple(sorted(place_ids)), self.release_id)
        photo_pids = {r["place_id"] for r in self._index.photo_rows if r["place_id"] in place_ids}
        span_rows = self._index.span_rows()
        span_pids = {r.place_id for r in span_rows if r.place_id in place_ids}
        style_pids = {pid for pid in place_ids if self._index.places.get(pid, {}).get("styles")}
        return CoverageReport(
            total=total,
            with_photos=len(photo_pids),
            with_spans=len(span_pids),
            with_styles=len(style_pids),
            missing_photos=tuple(sorted(place_ids - photo_pids)),
            missing_spans=tuple(sorted(place_ids - span_pids)),
            release_id=self.release_id)
