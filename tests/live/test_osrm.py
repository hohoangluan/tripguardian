import json
from pathlib import Path

import pytest

from live import http, settings
from live.osrm import client

FIXTURES = Path(__file__).parent / "fixtures"
PTS = [(11.9465, 108.4419), (11.9404, 108.4583), (11.9029, 108.4482)]


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
def table(monkeypatch):
    """Serve the saved OSRM table and count the calls, so cache behaviour is visible."""
    doc = json.loads((FIXTURES / "osrm_table.json").read_text(encoding="utf-8"))
    calls = []

    def fake(url, ua, timeout):
        calls.append(url)
        return doc

    monkeypatch.setattr(client, "get_json", fake)
    return calls


def test_the_matrix_is_minutes_with_zero_on_the_diagonal(cfg, table):
    m = client.travel_matrix(PTS, "car", cfg)
    assert m["minutes"][0][0] == 0 and m["minutes"][1][1] == 0
    assert m["minutes"][0][1] == 9       # 540.3 s * 1.0 / 60
    assert m["minutes"][0][2] == 21      # 1260.8 s * 1.0 / 60
    assert m["source"] == "osrm" and m["fetched_at"]


def test_the_request_sends_lng_then_lat(cfg, table):
    client.travel_matrix(PTS, "car", cfg)
    assert "108.441900,11.946500" in table[0]
    assert "annotations=duration" in table[0]


def test_the_motorbike_factor_scales_the_car_times(cfg, table):
    car = client.travel_matrix(PTS, "car", cfg)["minutes"][0][1]
    moto = client.travel_matrix(PTS, "motorbike", cfg)["minutes"][0][1]
    assert moto <= car
    assert moto == 9  # 540.3 s * 0.95 / 60 rounds to 9


def test_an_unknown_mode_falls_back_to_a_factor_of_one(cfg, table):
    assert client.travel_matrix(PTS, "hovercraft", cfg)["minutes"][0][1] == 9


def test_the_second_call_comes_from_the_cache(cfg, table):
    client.travel_matrix(PTS, "car", cfg)
    client.travel_matrix(PTS, "car", cfg)
    assert len(table) == 1


def test_changing_only_the_mode_does_not_refetch(cfg, table):
    client.travel_matrix(PTS, "car", cfg)
    client.travel_matrix(PTS, "motorbike", cfg)
    assert len(table) == 1


def test_a_different_point_set_refetches(cfg, table):
    client.travel_matrix(PTS, "car", cfg)
    client.travel_matrix(PTS[:2], "car", cfg)
    assert len(table) == 2


def test_fewer_than_two_points_is_a_programming_error(cfg, table):
    with pytest.raises(ValueError):
        client.travel_matrix([PTS[0]], "car", cfg)


def test_a_pair_with_no_road_is_none_and_the_others_still_work(cfg, monkeypatch):
    doc = {"code": "Ok", "durations": [[0, None, 1260.8], [None, 0, 980.2], [1272.4, 991.6, 0]]}
    monkeypatch.setattr(client, "get_json", lambda url, ua, timeout: doc)
    m = client.travel_matrix(PTS, "car", cfg)["minutes"]
    assert m[0][1] is None and m[1][0] is None
    assert m[0][2] == 21 and m[2][1] == 17
    assert m[0][0] == 0


def test_a_non_ok_code_is_unavailable_and_nothing_is_cached(cfg, data_dir, monkeypatch):
    monkeypatch.setattr(client, "get_json", lambda url, ua, timeout: {"code": "NoSegment", "message": "no road"})
    with pytest.raises(http.Unavailable):
        client.travel_matrix(PTS, "car", cfg)
    assert not (data_dir / "live" / "osrm").exists()


def test_an_ok_code_with_no_durations_is_unavailable(cfg, monkeypatch):
    monkeypatch.setattr(client, "get_json", lambda url, ua, timeout: {"code": "Ok"})
    with pytest.raises(http.Unavailable):
        client.travel_matrix(PTS, "car", cfg)


def test_a_dead_osrm_is_unavailable_not_a_crash(cfg, monkeypatch):
    def dead(url, ua, timeout):
        raise http.Unavailable("http://127.0.0.1:5000/table/v1/driving: connection refused")

    monkeypatch.setattr(client, "get_json", dead)
    with pytest.raises(http.Unavailable):
        client.travel_matrix(PTS, "car", cfg)
