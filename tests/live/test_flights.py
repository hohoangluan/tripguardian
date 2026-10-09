"""Google Flights: the parser on a saved page, cache before the browser, no made-up flight."""

from datetime import date
from pathlib import Path

import pytest

from live import settings
from live.flights import google
from live.http import Unavailable

PAGE = Path(__file__).resolve().parents[1] / "fixtures" / "live" / "flights_sgn_dli_20261112.html"
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


def test_the_saved_page_parses_into_flights():
    out = google.parse(PAGE.read_text(encoding="utf-8"), DAY)
    assert [(f["carrier"], f["depart_at"], f["arrive_at"], f["price_vnd"]) for f in out] == [
        ("Vietnam Airlines", "2026-11-12T06:10", "2026-11-12T07:05", 890181),
        ("Vietjet", "2026-11-12T06:30", "2026-11-12T07:25", 994781),
        ("Vietnam Airlines", "2026-11-12T09:55", "2026-11-12T10:50", 1344181),
        ("Vietjet", "2026-11-12T16:20", "2026-11-12T17:15", 994781),
        ("Vietnam Airlines", "2026-11-12T17:25", "2026-11-12T18:20", 1096181)]
    assert out[0]["from_point"] == "Cảng hàng không quốc tế Tân Sơn Nhất"
    assert out[0]["to_point"] == "Cảng Hàng Không Quốc Tế Liên Khương" and out[0]["mode"] == "plane"
    assert all(f["stops"] == 0 for f in out)


def test_a_date_without_a_year_takes_the_year_nearest_the_search():
    label = ('<div aria-label="Từ 1000000 đồng Việt Nam trở lên. Chuyến bay thẳng của Vietjet. Rời A lúc 23:30 vào '
             'Thứ Năm, tháng 12 31 và đến B lúc 01:10 vào Thứ Sáu, tháng 1 1. Tổng thời gian bay: 1 giờ 40 phút."></div>')
    (f,) = google.parse(label, date(2026, 12, 31))
    assert f["arrive_at"] == "2027-01-01T01:10"


def test_the_url_names_the_route_and_the_day():
    link = google.url("SGN", "DLI", DAY)
    assert "SGN%20to%20DLI%20on%202026-11-12" in link and "hl=vi" in link and "curr=VND" in link


def test_a_cached_day_never_opens_the_browser(cfg, monkeypatch):
    opened = []

    async def fake_page(link):
        opened.append(link)
        return PAGE.read_text(encoding="utf-8")

    monkeypatch.setattr(google, "_page", fake_page)
    assert google.flights("SGN", "DLI", DAY, cfg, fetch=False) is None
    first = google.flights("SGN", "DLI", DAY, cfg)
    assert google.flights("sgn", "dli", DAY, cfg) == first and len(opened) == 1
    assert first[0]["source"] == "google_flights" and first[0]["fetched_at"]


@pytest.mark.parametrize("page", ["<html>Our systems have detected unusual traffic</html>", None])
def test_a_captcha_an_empty_page_or_a_dead_browser_is_unavailable(cfg, monkeypatch, data_dir, page):
    async def fake_page(link):
        if page is None:
            raise TimeoutError("no row in 20 s")
        return page

    monkeypatch.setattr(google, "_page", fake_page)
    with pytest.raises(Unavailable):
        google.flights("SGN", "DLI", DAY, cfg)
    assert not list(data_dir.rglob("*.json"))


def test_a_connecting_flight_keeps_its_stops_and_carrier_and_is_not_merged_with_another_connection():
    def row(carrier, kind, arr):
        return (f'<div aria-label="Từ 3000000 đồng Việt Nam trở lên. Chuyến bay {kind} của {carrier}. Rời Phú Bài lúc '
                f'07:50 vào Thứ Ba, tháng 10 20 và đến Liên Khương lúc {arr} vào Thứ Ba, tháng 10 20. Tổng thời gian bay: '
                f'3 giờ.  Thời gian quá cảnh (1/1) là 1 giờ tại Tân Sơn Nhất."></div>')

    page = (row("Vietnam Airlines. Do Pacific Airlines khai thác", "có 1 điểm dừng", "11:15")
            + row("Vietnam Airlines", "có 1 điểm dừng", "13:25") + row("Vietjet", "thẳng", "09:00"))
    out = google.parse(page, date(2026, 10, 20))
    assert [(f["carrier"], f["arrive_at"][11:], f["stops"]) for f in out] == [
        ("Vietnam Airlines", "11:15", 1), ("Vietnam Airlines", "13:25", 1), ("Vietjet", "09:00", 0)]
