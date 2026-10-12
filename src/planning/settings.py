"""Planning thresholds (config/planning.yaml)."""

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "config" / "planning.yaml"


def to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass(frozen=True)
class Settings:
    version: int
    road_factor: float
    rough_speed_kmh: dict
    walk_km: float
    walk_kmh: float
    default_days: int
    day_start: int          # minutes after midnight
    day_end: int
    leave_at: int
    visit_key: dict
    per_day: dict
    buffer_min: dict
    long_leg_min: int
    buffer_extra_long: int
    buffer_extra_uncertain: int
    rest_min: dict
    max_consecutive_min: dict
    meals_per_day: int
    meal_min: int
    meal_windows: dict      # name -> (earliest start, latest start) in minutes
    pins: dict
    cluster_max_min: int
    cluster_merge_min: int
    fill_ratio: float
    intra_leg_min: int
    max_days: int
    max_clusters: int
    exact_n: int
    improve_passes: int
    weights: dict
    rain_high: float
    buffer_extra_rain: int
    robustness: dict
    max_variants: int
    objective_order: list
    objective_weights: dict
    near_close_min: int
    far_leg_min: int
    backup_radius_min: int
    backups_per_place: int
    radius_km: dict
    lodging_k: int
    lodging_share: float
    min_reviews: int
    split_min: int
    stay_min: int
    lodging_pool: int
    lodging_weights: dict
    loc_ref_min: int
    history_max: int
    repair_diff_weight: float
    decision_url: str
    first_token_s: float
    total_s: float
    rethink_drops: int
    crowd_busy_pct: int
    conditions: dict
    time_suitability: dict = field(default_factory=dict)
    repair_local_additions: int = 1
    repair_search_limit: int = 720
    cache_entries: int = 128
    suggestion_workers: int = 2
    chunk_days: int = 7
    long_trip_exact_n: int = 5
    composer: dict = field(default_factory=lambda: {"rho": 0.9, "alpha": 0.7, "tight_ratio": 0.8,
                                                   "per_day_max": {"slow": 4, "normal": 5, "packed": 7},
                                                   "search_limit": 120, "transport_vnd_per_min": {}})


@cache
def load(path: Path = PATH) -> Settings:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    for k in ("day_start", "day_end", "leave_at"):
        raw[k] = to_min(raw[k])
    raw["meal_windows"] = {name: (to_min(a), to_min(b)) for name, (a, b) in raw["meal_windows"].items()}
    raw["pins"] = {f: {**p, **({"from": to_min(p["from"]), "to": to_min(p["to"])} if p["anchor"] == "clock" else {})}
                   for f, p in raw["pins"].items()}
    return Settings(**raw)
