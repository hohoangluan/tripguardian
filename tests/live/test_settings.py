from pathlib import Path

from live import settings


def test_the_shipped_config_loads_with_every_field_filled():
    cfg = settings.load(settings.PATH)
    assert cfg.version == 1
    assert cfg.osrm_url.startswith("http")
    assert cfg.mode_factor["car"] == 1.0
    assert cfg.mode_factor["motorbike"] < 1.0
    assert set(cfg.ttl_s) == {"osrm", "weather", "lodging", "geocode", "transit"}
    assert cfg.ttl_s["osrm"] > cfg.ttl_s["weather"]
    assert cfg.tz_offset_h == 7
    assert cfg.nominatim_min_interval_s >= 1.0  # Nominatim's usage policy


def test_the_user_agent_carries_a_contact(monkeypatch):
    monkeypatch.setenv("LIVE_CONTACT", "someone@example.com")
    settings.load.cache_clear()
    assert "someone@example.com" in settings.load(settings.PATH).user_agent
    settings.load.cache_clear()
