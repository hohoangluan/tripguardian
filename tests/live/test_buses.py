"""Vexere coaches: the parser on a saved page, region choice, cache before network, no made-up trip."""

from datetime import date
from pathlib import Path

import pytest

from live import settings
from live.buses import vexere
from live.http import Unavailable

PAGE = Path(__file__).resolve().parents[1] / "fixtures" / "live" / "vexere_hcm_dalat_20261112.html"
DAY = date(2026, 11, 12)


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


def test_the_saved_page_parses_into_trips_leaving_that_day():
    trips = vexere.parse(PAGE.read_text(encoding="utf-8"), DAY)
    assert len(trips) == 20
    first = trips[0]
    assert first["depart_at"] == "2026-11-12T00:19" and first["arrive_at"] == "2026-11-12T05:59"
    assert first["carrier"] == "Điều Hòa" and first["price_vnd"] == 299000 and first["mode"] == "bus"
    thien = next(t for t in trips if t["carrier"] == "Thiện Thành Limousine" and t["depart_at"].endswith("06:00"))
    assert thien["from_point"] == "20 Hoa Bằng - Văn phòng Tân Phú"  # the address already names the office
    assert thien["arrive_at"] == "2026-11-12T13:30"
    assert [t["depart_at"] for t in trips] == sorted(t["depart_at"] for t in trips)
    assert not vexere.parse(PAGE.read_text(encoding="utf-8"), date(2026, 11, 13))


def test_a_page_without_the_trip_list_is_unavailable():
    with pytest.raises(Unavailable):
        vexere.parse("<html><body>Access denied</body></html>", DAY)


def test_the_region_is_the_nearest_to_a_point_or_the_one_a_name_names(cfg):
    assert vexere.region((10.80, 106.70), cfg)["name"] == "Sài Gòn"
    assert vexere.region((12.25, 109.19), cfg)["name"] == "Khánh Hòa"  # Nha Trang
    assert vexere.region("Thành phố Hồ Chí Minh", cfg)["id"] == 29
    assert vexere.region("tỉnh Đắk Lắk", cfg)["id"] == 16
    with pytest.raises(Unavailable):
        vexere.region("Atlantis", cfg)


def test_the_url_goes_province_to_city_and_back(cfg):
    assert vexere.url("Sài Gòn", DAY, "inbound", cfg).endswith("-129t23991.html?date=12-11-2026")
    assert vexere.url("Sài Gòn", DAY, "outbound", cfg).endswith("-2399t1291.html?date=12-11-2026")


def test_a_cached_day_never_reaches_the_network(cfg, monkeypatch):
    pages = []

    def fake_get(link, ua, timeout):
        pages.append(link)
        return PAGE.read_text(encoding="utf-8")

    monkeypatch.setattr(vexere, "get_text", fake_get)
    assert vexere.buses("Sài Gòn", DAY, "inbound", cfg, fetch=False) is None
    first = vexere.buses((10.77, 106.68), DAY, "inbound", cfg)
    again = vexere.buses("Sài Gòn", DAY, "inbound", cfg, fetch=False)
    assert len(pages) == 1 and first == again
    assert first[0]["source"] == "vexere" and first[0]["fetched_at"]


def test_a_failed_fetch_is_unavailable_and_caches_nothing(cfg, monkeypatch, data_dir):
    def boom(*a):
        raise Unavailable("timeout")

    monkeypatch.setattr(vexere, "get_text", boom)
    with pytest.raises(Unavailable):
        vexere.buses("Sài Gòn", DAY, "outbound", cfg)
    assert not list(data_dir.rglob("*.json"))
