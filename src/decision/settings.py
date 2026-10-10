"""Place Decision thresholds (config/decision.yaml)."""

from dataclasses import dataclass
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
    weights: dict
    stars: dict
    top_min_pref: float
    price_ref_vnd: int
    near_min: int
    per_day: dict
    per_day_max: dict
    meals_per_day: int
    meal_at: tuple
    meal_min: int
    fill_share: float
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
    keep_factor: float
    replace_below: float
    day_visit: dict
    first_token_s: float
    total_s: float
    display_groups: dict
    polarity: dict
    labels: dict


def load(path: Path = PATH) -> Settings:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    for k in ("rainy_months", "narrow_buckets", "timed_features", "meal_at"):
        raw[k] = tuple(raw[k])
    return Settings(**raw)


@cache
def default() -> Settings:
    return load()
