import json
from datetime import UTC, datetime, timedelta

import pytest

from live import cache


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


def test_put_then_get_returns_the_value_with_its_provenance():
    cache.put("osrm", {"points": [[1.0, 2.0]]}, [[0, 300]], "osrm")
    hit = cache.get("osrm", {"points": [[1.0, 2.0]]}, ttl_s=60)
    assert hit is not None
    assert hit["value"] == [[0, 300]]
    assert hit["source"] == "osrm"
    datetime.fromisoformat(hit["fetched_at"])  # parses, so it is a real timestamp


def test_an_entry_older_than_its_ttl_is_a_miss(data_dir):
    cache.put("osrm", {"a": 1}, "v", "osrm")
    p = next((data_dir / "live" / "osrm").glob("*.json"))
    entry = json.loads(p.read_text(encoding="utf-8"))
    entry["fetched_at"] = (datetime.now(UTC) - timedelta(seconds=120)).isoformat(timespec="seconds")
    p.write_text(json.dumps(entry), encoding="utf-8")
    assert cache.get("osrm", {"a": 1}, ttl_s=60) is None
    assert cache.get("osrm", {"a": 1}, ttl_s=3600) is not None


def test_different_payloads_do_not_share_an_entry():
    cache.put("osrm", {"a": 1}, "one", "osrm")
    cache.put("osrm", {"a": 2}, "two", "osrm")
    assert cache.get("osrm", {"a": 1}, 60)["value"] == "one"
    assert cache.get("osrm", {"a": 2}, 60)["value"] == "two"


def test_key_ignores_dict_ordering():
    assert cache.key({"a": 1, "b": 2}) == cache.key({"b": 2, "a": 1})


def test_sources_are_kept_in_separate_directories(data_dir):
    cache.put("osrm", {"a": 1}, "v", "osrm")
    cache.put("geocode", {"a": 1}, "v", "nominatim")
    assert {d.name for d in (data_dir / "live").iterdir()} == {"osrm", "geocode"}


def test_a_truncated_cache_file_is_a_miss_not_a_crash(data_dir):
    cache.put("osrm", {"a": 1}, "v", "osrm")
    p = next((data_dir / "live" / "osrm").glob("*.json"))
    p.write_text('{"source": "osrm", "fetch', encoding="utf-8")  # killed mid-write
    assert cache.get("osrm", {"a": 1}, 60) is None


def test_a_cache_file_without_a_timestamp_is_a_miss(data_dir):
    cache.put("osrm", {"a": 1}, "v", "osrm")
    p = next((data_dir / "live" / "osrm").glob("*.json"))
    p.write_text('{"source": "osrm", "value": "v"}', encoding="utf-8")
    assert cache.get("osrm", {"a": 1}, 60) is None
