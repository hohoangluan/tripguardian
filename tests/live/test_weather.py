from datetime import date

import pytest

from live import settings
from live.http import Unavailable
from live.weather import open_meteo
from live.weather import weather as weather_fn


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


TODAY = lambda: date(2026, 10, 2)


def doc(dates, probs):
    return {"daily": {"time": dates, "precipitation_probability_max": probs}}


def test_a_date_within_the_horizon_is_fetched_from_open_meteo(cfg, monkeypatch):
    monkeypatch.setattr(open_meteo, "get_json", lambda url, ua, timeout: doc(["2026-10-05"], [80]))
    out = weather_fn(11.94, 108.45, ["2026-10-05"], cfg, today_fn=TODAY)
    assert out["2026-10-05"]["rain_prob"] == 0.8
    assert out["2026-10-05"]["source"] == "open-meteo" and out["2026-10-05"]["fetched_at"]


def test_a_date_past_the_horizon_comes_from_climate_and_touches_no_network(cfg):
    out = weather_fn(11.94, 108.45, ["2027-06-15"], cfg, today_fn=TODAY)
    assert out["2027-06-15"]["source"] == "climate" and out["2027-06-15"]["fetched_at"] is None
    assert 0 <= out["2027-06-15"]["rain_prob"] <= 1


def test_dates_on_both_sides_of_the_horizon_are_split_and_only_the_near_one_calls_the_network(cfg, monkeypatch):
    calls = []
    monkeypatch.setattr(open_meteo, "get_json",
                        lambda url, ua, timeout: calls.append(url) or doc(["2026-10-05"], [10]))
    out = weather_fn(11.94, 108.45, ["2026-10-05", "2027-06-15"], cfg, today_fn=TODAY)
    assert len(calls) == 1 and set(out) == {"2026-10-05", "2027-06-15"}
    assert out["2026-10-05"]["source"] == "open-meteo" and out["2027-06-15"]["source"] == "climate"


def test_a_date_the_forecast_answer_does_not_cover_is_none_not_a_crash(cfg, monkeypatch):
    monkeypatch.setattr(open_meteo, "get_json", lambda url, ua, timeout: doc([], []))
    out = weather_fn(11.94, 108.45, ["2026-10-05"], cfg, today_fn=TODAY)
    assert out["2026-10-05"]["rain_prob"] is None and out["2026-10-05"]["source"] == "open-meteo"


def test_a_dead_source_is_unavailable_not_a_crash(cfg, monkeypatch):
    def dead(url, ua, timeout):
        raise Unavailable("open-meteo down")

    monkeypatch.setattr(open_meteo, "get_json", dead)
    with pytest.raises(Unavailable):
        weather_fn(11.94, 108.45, ["2026-10-05"], cfg, today_fn=TODAY)


def test_the_second_call_for_the_same_range_comes_from_the_cache(cfg, monkeypatch):
    calls = []
    monkeypatch.setattr(open_meteo, "get_json",
                        lambda url, ua, timeout: calls.append(url) or doc(["2026-10-05", "2026-10-06"], [10, 20]))
    weather_fn(11.94, 108.45, ["2026-10-05", "2026-10-06"], cfg, today_fn=TODAY)
    weather_fn(11.94, 108.45, ["2026-10-05", "2026-10-06"], cfg, today_fn=TODAY)
    assert len(calls) == 1


def test_no_dates_needs_no_network(cfg):
    assert weather_fn(11.94, 108.45, [], cfg) == {}


def test_rain_amount_gusts_and_thunderstorm_come_with_the_forecast(cfg, monkeypatch):
    body = {"daily": {"time": ["2026-10-05", "2026-10-06"], "precipitation_probability_max": [90, 10],
                      "precipitation_sum": [85.5, 0.0], "wind_gusts_10m_max": [72.0, 20.0], "weather_code": [95, 1]}}
    monkeypatch.setattr(open_meteo, "get_json", lambda url, ua, timeout: body)
    out = weather_fn(11.94, 108.45, ["2026-10-05", "2026-10-06"], cfg, today_fn=TODAY)
    assert (out["2026-10-05"]["rain_mm"], out["2026-10-05"]["gust_kmh"], out["2026-10-05"]["storm"]) == (85.5, 72.0, True)
    assert out["2026-10-06"]["storm"] is False


def test_a_figure_open_meteo_did_not_give_stays_unknown(cfg, monkeypatch):
    monkeypatch.setattr(open_meteo, "get_json", lambda url, ua, timeout: doc(["2026-10-05"], [40]))
    out = weather_fn(11.94, 108.45, ["2026-10-05"], cfg, today_fn=TODAY)["2026-10-05"]
    assert out["rain_prob"] == 0.4 and out["rain_mm"] is None and out["gust_kmh"] is None and out["storm"] is None
