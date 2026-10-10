"""Aggregate observations of every source into per-place signals (code only, docs/P1_CORPUS.md §5)."""

from .place import aggregate_place, run

__all__ = ["aggregate_place", "run"]
