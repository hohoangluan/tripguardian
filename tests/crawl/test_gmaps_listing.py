import json

from corpus.crawl.gmaps.listing import build_stay

AREA = [11.8, 108.3, 12.1, 108.7]


def card(fid, price=None, reviews=50):
    return {"fid": fid, "name": fid, "url": "", "lat": 11.94, "lng": 108.44, "category": "Khách sạn",
            "rating": 4.5, "reviews": reviews, "price_vnd": price}


def test_stay_list_keeps_the_newest_hotel_list_price(tmp_path):
    d = tmp_path / "dalat_stay"
    d.mkdir()
    lines = [{"at": "2026-10-01T00:00:00+00:00", "query": "a", "end": True, "items": [card("H1", 400000)]},
             {"at": "2026-10-08T00:00:00+00:00", "query": "b", "end": True, "items": [card("H1", 467000), card("H2")]},
             {"at": "2026-10-09T00:00:00+00:00", "query": "c", "end": True, "items": [card("H1", None)]}]
    (d / "x.jsonl").write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    items = {r["fid"]: r for r in build_stay([d], AREA)["items"]}
    assert (items["H1"]["price_vnd"], items["H1"]["price_at"]) == (467000, "2026-10-08T00:00:00+00:00")
    assert "price_vnd" not in items["H2"]
