"""corpus.snapshot: what online reads (docs/superpowers/specs/2026-10-13-corpus-snapshot-design.md). Offline compiles
it (python -m corpus snapshot, and at the end of python -m corpus serving); online only reads it."""

from .compile import compile_snapshot
from .read import FeatureColumn, Region, Snapshot, shared
from .tables import tables

__all__ = ["FeatureColumn", "Region", "Snapshot", "compile_snapshot", "shared", "tables"]
