import json

from corpus.crawl.gmaps.listing import build_stay
from corpus.crawl.gmaps.stay_price import load_prices, parse_price

AREA = [11.8, 108.3, 12.1, 108.7]

# innerText of a hotel page Maps has offers for (2026-10-13): the price chip for Maps' default dates sits above the tabs
OFFERS = ("Tải ứng dụng\n1.258.600\xa0₫\n4 – 5 thg 1\n\nXem ảnh\nThe Gardener by WeDalat\n5,0\nKhách sạn\n"
          "Tổng quan\nGiá\nGiới thiệu\nSo sánh giá\nTất cả mức giá\nBluepillow.com\n1.258.600\xa0₫\nEaseMyTrip.com\n1.402.057\xa0₫\n")
NO_OFFERS = ("Tải ứng dụng\n\nXem ảnh\nAsahi House Đà Lạt\n5,0\nKhách sạn\nĐường đi\nLưu\n52a Đ. Phạm Hồng Thái\n"
             "+84 968 816 133\n")


def test_the_price_chip_above_the_tabs_is_the_price_a_night_for_maps_default_dates():
    assert parse_price(OFFERS) == {"price_vnd": 1258600, "stay_dates": "4 – 5 thg 1"}


def test_a_page_without_offers_has_no_price():
    assert parse_price(NO_OFFERS) is None


def test_a_price_only_in_the_offer_list_is_not_guessed():
    text = OFFERS.replace("1.258.600\xa0₫\n4\u2009–\u20095 thg 1\n", "", 1)
    assert parse_price(text) is None  # the chip is not drawn yet: wait for it


def test_an_amount_elsewhere_on_the_page_is_not_a_price():
    assert parse_price("Tổng quan\nGiá\nGiới thiệu\nThực đơn 50.000 ₫\n") is None


def card(fid, price=None):
    return {"fid": fid, "name": fid, "url": "", "lat": 11.94, "lng": 108.44, "category": "Khách sạn",
            "rating": 4.5, "reviews": 50, "price_vnd": price}


def test_the_stay_list_takes_a_page_price_when_no_hotel_list_card_had_one(tmp_path):
    d = tmp_path / "dalat_stay"
    d.mkdir()
    rows = [{"at": "2026-10-01T00:00:00+00:00", "query": "a", "end": True, "items": [card("H1", 400000), card("H2")]}]
    (d / "x.jsonl").write_text("\n".join(json.dumps(x) for x in rows), encoding="utf-8")
    pages = {"H1": ("2026-10-13T00:00:00+00:00", 900000), "H2": ("2026-10-13T00:00:00+00:00", 700000)}
    items = {r["fid"]: r for r in build_stay([d], AREA, detail_prices=pages)["items"]}
    assert (items["H2"]["price_vnd"], items["H2"]["price_at"]) == (700000, "2026-10-13T00:00:00+00:00")
    assert items["H1"]["price_vnd"] == 400000  # the hotel list's card wins: same source Maps shows in its list


def test_load_prices_keeps_the_newest_found_price_and_skips_the_empty_ones(tmp_path):
    f = tmp_path / "dalat.jsonl"
    rows = [{"fid": "H1", "at": "2026-10-10T00:00:00+00:00", "price_vnd": 800000},
            {"fid": "H1", "at": "2026-10-13T00:00:00+00:00", "price_vnd": 900000},
            {"fid": "H2", "at": "2026-10-13T00:00:00+00:00", "price_vnd": None}]
    f.write_text("\n".join(json.dumps(x) for x in rows), encoding="utf-8")
    assert load_prices(f) == {"H1": ("2026-10-13T00:00:00+00:00", 900000)}
    assert load_prices(tmp_path / "missing.jsonl") == {}
