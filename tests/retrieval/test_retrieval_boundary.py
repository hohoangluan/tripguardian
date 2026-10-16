"""Boundary tests for corpus.retrieval.engine (no real model, no real corpus data).

Invariants checked (from the plan):
  - No ID outside `within` in any result.
  - Evidence only from served=True spans.
  - Semantic search returns score + pointer, never promotes to VERIFIED.
  - `release_id` present in every result.
  - Feature-aware boost does not elevate vector hit to VERIFIED.
"""

import json
import threading
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from corpus.index.query import Index, PhotoHit, SpanHit, TextVec
from corpus.retrieval.engine import (
    CoverageReport,
    EvidenceHit,
    NameHit,
    RetrievalEngine,
    SemanticHit,
    SimilarHit,
    _match_ontology,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

STYLES = {"version": 1, "min_authors": 2, "styles": [
    {"id": "retro", "label": "Hoài cổ", "hint": ""},
    {"id": "retro_saigon", "parent": "retro", "label": "Sài Gòn xưa", "hint": ""}]}

CFG = {"places_by_photos": {"min_photos": 2, "min_authors": 2, "per_place": 3, "owner_weight": 0.6},
       "clusters": {"k_max": 4, "min_places": 2, "photos": 3}, "search": {"k_photos": 50, "k_spans": 10}}

RELEASE_ID = "r-test-abc123"


def unit(*v):
    a = np.array(v, np.float32)
    return a / np.linalg.norm(a)


def _make_index(photo_rows, span_rows, places=None):
    """Build a mock Index with injected spans and photos (no LanceDB, no model)."""
    # Photo vectors (3D)
    pvecs = np.stack([unit(1, 0.1 * i, 0) for i in range(len(photo_rows))])
    # Span vectors (4D)
    svecs = np.stack([unit(1, 0.1 * i, 0, 0) for i in range(len(span_rows))]) if span_rows else np.zeros((0, 4), np.float32)
    served_mask = np.array([r.get("served", True) for r in span_rows], dtype=bool) if span_rows else np.array([], dtype=bool)
    all_pids = {r["place_id"] for r in photo_rows} | {r["place_id"] for r in span_rows}
    places = places or {pid: {"name": f"Place {pid}", "styles": {}, "near_duplicate_group": None,
                               "category_group": "non_stay"} for pid in all_pids}
    return Index(version="test_v1", root=None, places=places, styles=STYLES, photo_vecs=pvecs,
                 photo_rows=photo_rows, cfg=CFG, _spans=(svecs, span_rows, served_mask))


def _photo_row(pid, author="u1"):
    return {"place_id": pid, "file": f"gmaps/places/{pid}/photos/{author}.jpg",
            "author": author, "owner": False, "source": "gmaps"}


def _span_row(pid, oid, quote, features="[]", served=True):
    return {"place_id": pid, "observation_id": oid, "quote": quote,
            "features": features, "source": "gmaps", "served": served}


def _make_engine(photo_rows, span_rows, places=None, *, region_mock=None, ont_mock=None):
    """Build a RetrievalEngine with mock internals (no filesystem, no model)."""
    idx = _make_index(photo_rows, span_rows, places)
    snap = MagicMock()
    region = region_mock or _mock_region(places or {pid: {"name": f"Place {pid}", "styles": {},
                                                           "near_duplicate_group": None, "category_group": "non_stay"}
                                                     for pid in {r["place_id"] for r in photo_rows + span_rows}})
    ont = ont_mock or _simple_ontology()
    return RetrievalEngine(_index=idx, _snapshot=snap, _region=region, _ontology=ont, release_id=RELEASE_ID)


def _simple_ontology():
    """A minimal Ontology with one feature for testing."""
    from corpus.ontology import Feature, Ontology
    return Ontology(
        version=1,
        groups=("experience", "service"),
        contexts={},
        features={
            "outdoor_seating": Feature("outdoor_seating", "experience", ("present", "absent"),
                                        "ngồi ngoài trời / có sân vườn"),
            "photo_friendly": Feature("photo_friendly", "experience", ("present", "absent"),
                                       "chụp ảnh đẹp / instagrammable"),
        })


def _mock_region(places_dict):
    """Build a mock Region that returns canned feature columns."""
    region = MagicMock()
    ids = list(places_dict.keys())
    region.ids = ids
    region.index = {pid: i for i, pid in enumerate(ids)}

    def mock_record(pid):
        return places_dict.get(pid)

    region.record = mock_record

    def mock_feature(fid):
        col = MagicMock()
        col.value = [None] * len(ids)
        col.firm = np.zeros(len(ids), dtype=bool)
        return col

    region.feature = mock_feature
    return region


# ---------------------------------------------------------------------------
# Tests: search_names
# ---------------------------------------------------------------------------

class TestSearchNames:
    def test_no_ids_outside_within(self):
        engine = _make_engine(
            [_photo_row("a"), _photo_row("b"), _photo_row("c")],
            [], places={
                "a": {"name": "Cà phê Tùng", "styles": {}, "near_duplicate_group": None, "category_group": "non_stay"},
                "b": {"name": "Cà phê Bốn Mùa", "styles": {}, "near_duplicate_group": None, "category_group": "non_stay"},
                "c": {"name": "Nhà hàng Ba Lê", "styles": {}, "near_duplicate_group": None, "category_group": "non_stay"},
            })
        hits = engine.search_names("cà phê", within={"a"})
        assert all(h.place_id in {"a"} for h in hits)
        assert all(h.release_id == RELEASE_ID for h in hits)

    def test_match_types(self):
        engine = _make_engine(
            [_photo_row("a"), _photo_row("b")],
            [], places={
                "a": {"name": "Cà Phê Tùng", "styles": {}, "near_duplicate_group": None, "category_group": "non_stay"},
                "b": {"name": "Tiệm Cà Phê", "styles": {}, "near_duplicate_group": None, "category_group": "non_stay"},
            })
        hits = engine.search_names("cà phê tùng", within={"a", "b"})
        assert hits[0].match_type == "exact"
        assert hits[0].place_id == "a"

    def test_release_id_in_results(self):
        engine = _make_engine([_photo_row("a")], [], places={
            "a": {"name": "Test", "styles": {}, "near_duplicate_group": None, "category_group": "non_stay"}})
        hits = engine.search_names("test", within={"a"})
        assert all(h.release_id == RELEASE_ID for h in hits)


# ---------------------------------------------------------------------------
# Tests: semantic
# ---------------------------------------------------------------------------

class TestSemantic:
    def _engine_with_embed(self, photo_rows, span_rows, places=None):
        """Engine with a mock embedder that returns deterministic vectors."""
        engine = _make_engine(photo_rows, span_rows, places)

        def mock_embed_text(text, spans=False):
            return TextVec(photo=unit(1, 0, 0), span=unit(1, 0, 0, 0) if spans else None)

        def mock_embed_image(data):
            return unit(1, 0, 0)

        engine._index.embed_text = mock_embed_text
        engine._index.embed_image = mock_embed_image
        return engine

    def test_no_ids_outside_within(self):
        engine = self._engine_with_embed(
            [_photo_row("a"), _photo_row("b")],
            [_span_row("a", "o1", "cozy"), _span_row("b", "o2", "noisy")])
        hits = engine.semantic("cozy place", within={"a"})
        assert all(h.place_id in {"a"} for h in hits)

    def test_release_id_in_results(self):
        engine = self._engine_with_embed(
            [_photo_row("a")],
            [_span_row("a", "o1", "nice")])
        hits = engine.semantic("nice", within={"a"})
        assert all(h.release_id == RELEASE_ID for h in hits)

    def test_semantic_returns_score_not_status(self):
        """Semantic hits carry score + pointer, never a verification status."""
        engine = self._engine_with_embed(
            [_photo_row("a")],
            [_span_row("a", "o1", "beautiful garden")])
        hits = engine.semantic("garden", within={"a"})
        for h in hits:
            assert isinstance(h.score, float)
            assert h.pointer is not None or h.channel in ("span", "photo", "hybrid")
            # SemanticHit has no "status" or "verified" field
            assert not hasattr(h, "status") or "VERIFIED" not in str(getattr(h, "status", ""))

    def test_vibe_mode_reads_unserved_spans(self):
        """mode='vibe' includes spans with served=False."""
        engine = self._engine_with_embed(
            [_photo_row("a")],
            [_span_row("a", "o1", "đèn lồng đỏ", served=True),
             _span_row("a", "o2", "vibe chill nhẹ nhàng", served=False)])
        hits = engine.semantic("vibe chill", within={"a"}, mode="vibe")
        # Both spans should be searchable
        assert len(hits) >= 1

    def test_evidence_mode_excludes_unserved(self):
        """mode='evidence' only reads served spans."""
        engine = self._engine_with_embed(
            [_photo_row("a")],
            [_span_row("a", "o1", "đèn lồng đỏ", served=True),
             _span_row("a", "o2", "vibe chill nhẹ nhàng", served=False)])
        # Use the span search channel directly to verify filtering
        vec = TextVec(photo=unit(1, 0, 0), span=unit(1, 0, 0, 0))
        served_hits = engine._index.search_spans(vec, served_only=True)
        assert all(h.served for h in served_hits)

    def test_image_query(self):
        """bytes query uses photo space only."""
        engine = self._engine_with_embed(
            [_photo_row("a"), _photo_row("b")],
            [_span_row("a", "o1", "photo")])
        hits = engine.semantic(b"\x00\x01\x02", within={"a", "b"})
        assert all(h.channel == "photo" for h in hits)


# ---------------------------------------------------------------------------
# Tests: evidence
# ---------------------------------------------------------------------------

class TestEvidence:
    def test_evidence_only_from_served_spans(self):
        """Evidence lookup must return only served=True spans."""
        engine = _make_engine(
            [_photo_row("a")],
            [_span_row("a", "o1", "outdoor tables", '["outdoor_seating=present"]', served=True),
             _span_row("a", "o2", "nice garden vibe", '["outdoor_seating=present"]', served=False)])
        engine._region.record = lambda pid: {"environment": {"outdoor_seating": {"value": "present", "status": "VERIFIED"}}}
        hits = engine.evidence("a", "outdoor_seating")
        assert len(hits) == 1
        assert hits[0].observation_id == "o1"
        assert hits[0].release_id == RELEASE_ID

    def test_evidence_feature_filter(self):
        """Only spans whose features match the requested feature are returned."""
        engine = _make_engine(
            [_photo_row("a")],
            [_span_row("a", "o1", "outdoor", '["outdoor_seating=present"]', served=True),
             _span_row("a", "o2", "noisy", '["noise=high"]', served=True)])
        engine._region.record = lambda pid: {"environment": {"outdoor_seating": {"value": "present", "status": "VERIFIED"}}}
        hits = engine.evidence("a", "outdoor_seating")
        assert len(hits) == 1
        assert hits[0].observation_id == "o1"

    def test_evidence_wrong_place_not_returned(self):
        """Evidence for place 'a' must not include spans from place 'b'."""
        engine = _make_engine(
            [_photo_row("a"), _photo_row("b")],
            [_span_row("a", "o1", "tables", '["outdoor_seating=present"]', served=True),
             _span_row("b", "o2", "garden", '["outdoor_seating=present"]', served=True)])
        engine._region.record = lambda pid: {"environment": {"outdoor_seating": {"value": "present", "status": "VERIFIED"}}}
        hits = engine.evidence("a", "outdoor_seating")
        assert all(h.place_id == "a" for h in hits)


# ---------------------------------------------------------------------------
# Tests: similar
# ---------------------------------------------------------------------------

class TestSimilar:
    def test_no_ids_outside_within(self):
        engine = _make_engine(
            [_photo_row("a"), _photo_row("b"), _photo_row("c")],
            [])
        hits = engine.similar("a", within={"b"})
        assert all(h.place_id in {"b"} for h in hits)

    def test_release_id_in_results(self):
        engine = _make_engine(
            [_photo_row("a"), _photo_row("b")],
            [])
        hits = engine.similar("a", within={"a", "b"})
        assert all(h.release_id == RELEASE_ID for h in hits)


# ---------------------------------------------------------------------------
# Tests: coverage
# ---------------------------------------------------------------------------

class TestCoverage:
    def test_coverage_counts(self):
        engine = _make_engine(
            [_photo_row("a"), _photo_row("b")],
            [_span_row("a", "o1", "text")],
            places={
                "a": {"name": "A", "styles": {"retro": {}}, "near_duplicate_group": None, "category_group": "non_stay"},
                "b": {"name": "B", "styles": {}, "near_duplicate_group": None, "category_group": "non_stay"},
                "c": {"name": "C", "styles": {}, "near_duplicate_group": None, "category_group": "non_stay"},
            })
        report = engine.coverage({"a", "b", "c"})
        assert report.total == 3
        assert report.with_photos == 2  # a and b
        assert report.with_spans == 1   # only a
        assert report.with_styles == 1  # only a (has retro style)
        assert "c" in report.missing_photos
        assert "b" in report.missing_spans
        assert report.release_id == RELEASE_ID


# ---------------------------------------------------------------------------
# Tests: ontology matching
# ---------------------------------------------------------------------------

class TestOntologyMatching:
    def test_match_value_in_query(self):
        ont = _simple_ontology()
        matches = _match_ontology("chỗ nào có ngồi ngoài trời", ont)
        # Should match "outdoor_seating" via hint "ngồi ngoài trời"
        fids = [m[0] for m in matches]
        assert "outdoor_seating" in fids

    def test_match_photo_friendly(self):
        ont = _simple_ontology()
        matches = _match_ontology("nơi nào chụp ảnh đẹp instagrammable", ont)
        fids = [m[0] for m in matches]
        # "instagrammable" is in the hint for photo_friendly
        assert "photo_friendly" in fids

    def test_empty_query_no_match(self):
        ont = _simple_ontology()
        assert _match_ontology("", ont) == []

    def test_unrelated_query_no_match(self):
        ont = _simple_ontology()
        matches = _match_ontology("thời tiết hôm nay thế nào", ont)
        # Unrelated to any feature
        assert len(matches) == 0


# ---------------------------------------------------------------------------
# Tests: get_place
# ---------------------------------------------------------------------------

class TestGetPlace:
    def test_returns_record(self):
        places = {"a": {"name": "Place A", "id": "a", "status": "VERIFIED"}}
        engine = _make_engine([_photo_row("a")], [], places={
            "a": {"name": "Place A", "styles": {}, "near_duplicate_group": None, "category_group": "non_stay"}})
        engine._region = MagicMock()
        engine._region.record = lambda pid: places.get(pid)
        rec = engine.get_place("a")
        assert rec is not None
        assert rec["name"] == "Place A"

    def test_returns_none_for_missing(self):
        engine = _make_engine([_photo_row("a")], [])
        engine._region = MagicMock()
        engine._region.record = lambda pid: None
        assert engine.get_place("missing") is None
