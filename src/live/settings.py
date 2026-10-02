"""Live Context settings (config/live.yaml). The contact in the User-Agent comes from .env, not from the repo."""

import os
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "config" / "live.yaml"


@dataclass(frozen=True)
class Settings:
    version: int
    osrm_url: str
    osrm_profile: str
    mode_factor: dict
    timeout_s: float
    nominatim_url: str
    user_agent: str
    nominatim_min_interval_s: float
    ttl_s: dict
    open_meteo_url: str
    tz_offset_h: float


@cache
def load(path: Path = PATH) -> Settings:
    load_dotenv(ROOT / ".env")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    contact = os.environ.get("LIVE_CONTACT", "unset")
    raw["user_agent"] = raw["user_agent"].format(contact=contact)
    return Settings(**raw)
