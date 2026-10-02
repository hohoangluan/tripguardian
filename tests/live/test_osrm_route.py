import json
from pathlib import Path

import pytest

from live import http, settings
from live.osrm import client

FIXTURES = Path(__file__).parent / "fixtures"
PTS = [(11.9465, 108.4419), (11.9029, 108.4482)]


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def cfg():
    settings.load.cache_clear()
    c = settings.load(settings.PATH)
    yield c
    settings.load.cache_clear()


@pytest.fixture
def route(monkeypatch):
    doc = json.loads((FIXTURES / "osrm_route.json").read_text(encoding="utf-8"))
    calls = []

    def fake(url, ua, timeout):
        calls.append(url)
        return doc

    monkeypatch.setattr(client, "get_json", fake)
    return calls


def test_the_shape_comes_back_as_lat_lng_pairs(cfg, route):
    r = client.route_shape(PTS, "car", cfg)
    assert r["coords"][0] == [11.9465, 108.4419]   # geojson is lng,lat; the app draws lat,lng
    assert r["coords"][-1] == [11.9029, 108.4482]
    assert r["minutes"] == 30                       # 1802.4 s * 1.0 / 60
    assert r["source"] == "osrm" and r["fetched_at"]


def test_the_request_asks_for_a_full_geojson_overview(cfg, route):
    client.route_shape(PTS, "car", cfg)
    assert "overview=full" in route[0] and "geometries=geojson" in route[0]
    assert "/route/v1/" in route[0]


def test_the_route_cache_is_separate_from_the_matrix_cache(cfg, route, monkeypatch):
    table = json.loads((FIXTURES / "osrm_table.json").read_text(encoding="utf-8"))
    both = []

    def fake(url, ua, timeout):
        both.append(url)
        return json.loads((FIXTURES / "osrm_route.json").read_text(encoding="utf-8")) if "/route/" in url else table

    monkeypatch.setattr(client, "get_json", fake)
    client.route_shape(PTS, "car", cfg)
    client.travel_matrix(PTS, "car", cfg)
    assert len(both) == 2


def test_a_non_ok_route_is_unavailable(cfg, monkeypatch):
    monkeypatch.setattr(client, "get_json", lambda url, ua, timeout: {"code": "NoRoute"})
    with pytest.raises(http.Unavailable):
        client.route_shape(PTS, "car", cfg)


def test_fewer_than_two_points_is_a_programming_error(cfg, route):
    with pytest.raises(ValueError):
        client.route_shape([PTS[0]], "car", cfg)
