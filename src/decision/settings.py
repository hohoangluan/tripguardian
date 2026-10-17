"""Place Decision thresholds (config/decision.yaml)."""

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "config" / "decision.yaml"


@dataclass(frozen=True)
class Settings:
    version: int
    center: dict
    speed_kmh: dict
    road_factor: float
    radius_km: dict
    area_bonus: float
    crowd_busy_pct: int
    crowd_penalty: float
    rainy_months: tuple
    min_context_fit: float
    max_travel_min: int  # a place farther than this from the trip's first center is hidden (docs §9.3)
    weights: dict
    price_ref_vnd: int
    near_min: int
    per_day: dict
    per_day_max: dict
    meals_per_day: int
    spare_factor: float
    pool_factor: int
    default_days: int
    day_start: str
    day_end: str
    leave_at: str
    buffer_min: dict
    intra_leg_min: int
    far_km: float
    buckets: dict
    narrow_buckets: tuple
    timed_features: tuple
    timed_share: float
    night_open: str
    infeasible_ratio: float
    budget_slack: float
    far_step: float
    travel_mult_min: float
    price_step: float
    pattern_min: int
    gap_min: int
    rethink_drops: int
    history_max: int
    unverified_show: int
    page_size: int
    replace_below: float
    first_token_s: float
    total_s: float
    display_groups: dict
    tabs: dict
    polarity: dict
    labels: dict
    shortlist_days: int = 7
    coach_min_people: int = 9  # a party this big needs a coach or a 16-seater: it counts as the companion `large_group`
    details_fit: dict = field(default_factory=lambda: {"good_bonus": 0.1, "bad_penalty": 0.2, "feature_bonus": 0.05})
    wish: dict = field(default_factory=lambda: {"a": {}, "like_min": 1.0, "purpose": {}})  # config/decision.yaml wish


def load(path: Path = PATH) -> Settings:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    for k in ("rainy_months", "narrow_buckets", "timed_features"):
        raw[k] = tuple(raw[k])
    return Settings(**raw)


@cache
def default() -> Settings:
    return load()
