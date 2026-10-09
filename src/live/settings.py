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
    photon_url: str
    ttl_s: dict
    open_meteo_url: str
    lodging_query_limit: int
    tz_offset_h: float
    vexere_dalat: int = 0  # Vexere area id of the city (buses)
    vexere_regions: tuple = ()  # ({id, name, lat, lng}, …) provinces with coaches to the city
    transit_prewarm: dict | None = None  # {flight_days, bus_days, pause_s}: scripts/prewarm_transit.py


@cache
def load(path: Path = PATH) -> Settings:
    load_dotenv(ROOT / ".env")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    contact = os.environ.get("LIVE_CONTACT", "unset")
    raw["user_agent"] = raw["user_agent"].format(contact=contact)
    raw["vexere_regions"] = tuple(raw.get("vexere_regions") or ())
    return Settings(**raw)
