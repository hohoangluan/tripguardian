"""Aggregate observations of every source into per-place signals (code only, docs/specs/CORPUS_SPEC.md §5)."""

from .place import aggregate_place, run

__all__ = ["aggregate_place", "run"]
