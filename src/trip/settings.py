"""Thresholds for Trip Understanding (config/trip.yaml)."""

from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    n_min: int = 1
    top_k: int = 20
    enough_factor: float = 1.5
    turn_budget: int = 5
    stop_score: float = 0.15
    first_token_s: float = 8.0
    total_s: float = 30.0

    @property
    def enough(self) -> int:
        return round(self.top_k * self.enough_factor)


def load(path: Path = ROOT / "config" / "trip.yaml") -> Settings:
    return Settings(**yaml.safe_load(path.read_text(encoding="utf-8")))
