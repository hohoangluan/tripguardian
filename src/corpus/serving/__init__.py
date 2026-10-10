"""Serving records for Place Decision (docs/P3_PLACE_DECISION.md §2.2): intel -> data/serving/places.json.

python -m corpus serving
"""

from .groups import areas, mmr, near_duplicate_groups, similarity
from .record import SERVED, build, check, feature
from .run import load, run

__all__ = ["SERVED", "areas", "build", "check", "feature", "load", "mmr", "near_duplicate_groups", "run", "similarity"]
