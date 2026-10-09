"""Thresholds for Trip Understanding (config/trip.yaml)."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


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
    first_token_s: float = 8.0  # shared agents runtime contract (src/agents/runtime.py); the Trip loop uses total_s
    total_s: float = 30.0
    clef_timeout_s: float = 1.0
    clef_reject_min: float = 0.88
    clef_data_min: float = 0.8
    clef_feature_min: float = 0.5  # a feature Clef ranks for a wish counts from this probability
    clef_verify_min: float = 0.75  # sure the quote does not say the fact: the fact is refused
    clef_reply_min: float = 0.9    # sure a reply promises results or states an unsaid fact: it is replaced
    clef_repeat_min: float = 0.9   # sure the question is already answered by the state: the Agent must ask another
    tool_steps: int = 6
    required: tuple = ("days", "companions", "mobility", "when")  # known before the user may press Next
    max_tokens: int = 1500
    arrival_buffer_min: int = 45  # from a coach / flight's arrival to the first stop, and from the last stop to departure
    entry_roads: tuple = ()  # ({from_deg, to_deg, text}, …): the road into the city by the bearing toward the origin
    airports: tuple = ()  # ({iata, name, lat, lng}, …) with direct flights to the city (config/airports.yaml)
    patterns: PatternSettings = field(default_factory=PatternSettings)
    themes: dict = field(default_factory=dict)  # theme id -> {title, say, soft: [...], groups: [...]} (Khám phá cards)

    @property
    def enough(self) -> int:
        return round(self.top_k * self.enough_factor)


def load(path: Path = ROOT / "config" / "trip.yaml") -> Settings:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    patterns = PatternSettings(**(raw.pop("patterns", None) or {}))
    roads = tuple(raw.pop("entry_roads", None) or ())
    airports = yaml.safe_load((path.parent / "airports.yaml").read_text(encoding="utf-8")) if (path.parent / "airports.yaml").exists() else {}
    raw["required"] = tuple(raw.get("required") or Settings.required)
    return Settings(**raw, entry_roads=roads, airports=tuple(airports.get("airports") or ()), patterns=patterns)
