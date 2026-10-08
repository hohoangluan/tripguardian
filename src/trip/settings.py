"""Thresholds for Trip Understanding (config/trip.yaml)."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class PatternSettings:
    """Long-term pattern learning (docs/TRIP_UNDERSTANDING.md §17). Off until a user id and consent are given."""
    enabled: bool = False
    min_sessions: int = 3     # sessions that must make the same choice before it counts as a pattern
    window: int = 8           # only the latest votes on a key are read
    agreement: float = 0.75   # share of those votes the winning choice needs
    stale_days: int = 365     # a pattern whose last vote is older than this is dropped
    max_places: int = 3       # place patterns offered on the prior card
    dir: str = "data/trip/profiles"


@dataclass(frozen=True)
class Settings:
    n_min: int = 1
    top_k: int = 20
    enough_factor: float = 1.5
    turn_budget: int = 5
    idle_limit: int = 2
    stop_score: float = 0.15
    first_token_s: float = 8.0
    total_s: float = 30.0
    patterns: PatternSettings = field(default_factory=PatternSettings)

    @property
    def enough(self) -> int:
        return round(self.top_k * self.enough_factor)


def load(path: Path = ROOT / "config" / "trip.yaml") -> Settings:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    patterns = PatternSettings(**(raw.pop("patterns", None) or {}))
    return Settings(**raw, patterns=patterns)
