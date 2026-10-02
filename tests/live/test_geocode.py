import json
from pathlib import Path

import pytest

from live import settings
from live.geocode import nominatim
from live.http import Unavailable

FIXTURES = Path(__file__).parent / "fixtures"


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
def hit(monkeypatch):
    rows = json.loads((FIXTURES / "nominatim_hit.json").read_text(encoding="utf-8"))
    calls = []

    def fake(url, ua, timeout):
        calls.append(url)
        return rows

    monkeypatch.setattr(nominatim, "get_json", fake)
    return calls


def test_a_match_becomes_a_point_with_its_provenance(cfg, hit):
    p = nominatim.geocode("Bến xe Liên tỉnh", cfg, sleep=lambda s: None)
    assert p["lat"] == 11.9404 and p["lng"] == 108.4583
    assert "Đà Lạt" in p["label"]
    assert p["source"] == "nominatim" and p["fetched_at"]


def test_the_city_is_appended_when_the_text_does_not_name_it(cfg, hit):
    nominatim.geocode("Bến xe Liên tỉnh", cfg, sleep=lambda s: None)
    assert "%C4%90%C3%A0+L%E1%BA%A1t" in hit[0]  # "Đà Lạt" is urlencoded into the query
    assert "countrycodes=vn" in hit[0]
    assert "limit=1" in hit[0]


def test_text_that_already_names_the_city_is_not_doubled(cfg, hit):
    nominatim.geocode("Sân bay Liên Khương, Đà Lạt", cfg, sleep=lambda s: None)
    assert hit[0].count("%C4%90%C3%A0+L%E1%BA%A1t") == 1


def test_the_second_lookup_comes_from_the_cache(cfg, hit):
    nominatim.geocode("Bến xe Liên tỉnh", cfg, sleep=lambda s: None)
    nominatim.geocode("Bến xe Liên tỉnh", cfg, sleep=lambda s: None)
    assert len(hit) == 1


def test_empty_text_is_a_programming_error(cfg, hit):
    with pytest.raises(ValueError):
        nominatim.geocode("   ", cfg, sleep=lambda s: None)


def test_two_lookups_in_a_row_wait_out_the_rate_limit(cfg, monkeypatch):
    rows = json.loads((FIXTURES / "nominatim_hit.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(nominatim, "get_json", lambda url, ua, timeout: rows)
    monkeypatch.setattr(nominatim, "_last_call", 0.0)
    slept, t = [], [100.0]
    nominatim.geocode("Bến xe Liên tỉnh", cfg, clock=lambda: t[0], sleep=slept.append)
    nominatim.geocode("Sân bay Liên Khương", cfg, clock=lambda: t[0], sleep=slept.append)
    assert slept[-1] == pytest.approx(cfg.nominatim_min_interval_s)


def test_no_match_is_none_and_is_remembered(cfg, monkeypatch):
    calls = []

    def empty(url, ua, timeout):
        calls.append(url)
        return []

    monkeypatch.setattr(nominatim, "get_json", empty)
    assert nominatim.geocode("Homestay Không Tồn Tại XYZ", cfg, sleep=lambda s: None) is None
    assert nominatim.geocode("Homestay Không Tồn Tại XYZ", cfg, sleep=lambda s: None) is None
    assert len(calls) == 2  # the city query and the boxed retry the first time; the cached miss asks nothing


def test_a_body_that_is_not_a_list_is_unavailable(cfg, monkeypatch):
    monkeypatch.setattr(nominatim, "get_json", lambda url, ua, timeout: {"error": "blocked"})
    with pytest.raises(Unavailable):
        nominatim.geocode("Bến xe Liên tỉnh", cfg, sleep=lambda s: None)


def test_a_place_outside_the_city_proper_is_found_by_the_province_wide_retry(cfg, monkeypatch):
    """The airport sits in Hiệp Thạnh, so '..., Đà Lạt' finds nothing; the retry has no city but is boxed to Lâm Đồng."""
    rows = json.loads((FIXTURES / "nominatim_hit.json").read_text(encoding="utf-8"))
    calls = []

    def fake(url, ua, timeout):
        calls.append(url)
        return [] if "%C4%90%C3%A0+L%E1%BA%A1t" in url else rows  # empty for the city-suffixed query only

    monkeypatch.setattr(nominatim, "get_json", fake)
    p = nominatim.geocode("Sân bay Liên Khương", cfg, sleep=lambda s: None)
    assert p is not None and p["lat"] == 11.9404
    assert len(calls) == 2
    assert "viewbox=" in calls[1] and "bounded=1" in calls[1]
    assert "%C4%90%C3%A0+L%E1%BA%A1t" not in calls[1]
    nominatim.geocode("Sân bay Liên Khương", cfg, sleep=lambda s: None)
    assert len(calls) == 2  # the answer of the retry is cached under the same text


def test_when_both_queries_find_nothing_it_is_none_and_remembered(cfg, monkeypatch):
    calls = []
    monkeypatch.setattr(nominatim, "get_json", lambda url, ua, timeout: calls.append(url) or [])
    assert nominatim.geocode("Nơi Không Có XYZ", cfg, sleep=lambda s: None) is None
    assert nominatim.geocode("Nơi Không Có XYZ", cfg, sleep=lambda s: None) is None
    assert len(calls) == 2  # two queries the first time, none the second
