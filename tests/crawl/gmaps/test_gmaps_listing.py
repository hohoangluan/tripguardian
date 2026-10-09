import json

import pytest
from gmaps_helpers import AREA

from corpus.crawl.gmaps import listing


def _row(fid, lat=11.94, lng=108.44, category="Thác nước", rating=4.5, reviews=100):
    return {"fid": fid, "name": fid, "url": f"https://maps/{fid}", "lat": lat, "lng": lng, "category": category,
            "rating": rating, "reviews": reviews}


def _rec(query, items, tile=(1, 1, 13), lodging=False, **extra):
    return {"query": query, "tile": list(tile), "end": True, "lodging": lodging, "items": items, **extra}


def _write(d, name, recs):
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n", encoding="utf-8")


def test_build_dedupes_drops_outside_area_lodging_and_old_records(tmp_path):
    d = tmp_path / "search"
    _write(d, "thac.jsonl", [
        _rec("thác", [_row("a"), _row("b"), _row("hcm", 10.93, 106.77)]),
        _rec("thác", [_row("a"), _row("nocoord", None, None), _row("hotel", category="Khách sạn nghỉ dưỡng")], tile=(2, 2, 13)),
        _rec("thác", [_row("resort-list")], tile=(3, 3, 13), lodging=True),  # Maps' hotel list
        {"query": "thác", "tile": [4, 4, 13], "end": True, "items": [{"fid": "old", "name": "old", "lat": 11.9, "lng": 108.4}]},
    ])
    _write(d, "cho.jsonl", [_rec("chợ", [_row("b", category="Chợ"), _row("c", category="Chợ")])])
    lst = listing.build(d, AREA, top=100)
    assert lst["stats"] == {"raw": 9, "outside_area": 2, "lodging": 2, "duplicates": 2, "candidates": 3, "not_kept": 0, "same_place": 0,
                             "few_reviews": 0, "places": 3}
    by = {r["fid"]: r for r in lst["items"]}
    assert sorted(by) == ["a", "b", "c"] and by["b"]["queries"] == ["chợ", "thác"]


def test_same_name_same_point_is_one_place(tmp_path):
    d = tmp_path / "search"
    big = {**_row("lake-big", reviews=2800), "name": "Hồ Xuân Hương"}
    small = {**_row("lake-small", reviews=400), "name": "hồ  xuân hương"}
    shop = {**_row("shop"), "name": "Maze Bar"}  # another shop in the same building: kept
    far = {**_row("lake-far", lat=11.95, reviews=5), "name": "Hồ Xuân Hương"}  # same name elsewhere: kept
    _write(d, "ho.jsonl", [_rec("hồ", [small, shop, far])])
    _write(d, "cv.jsonl", [_rec("công viên", [big])])
    lst = listing.build(d, AREA, top=100)
    by = {r["fid"]: r for r in lst["items"]}
    assert sorted(by) == ["lake-big", "lake-far", "shop"] and lst["stats"]["same_place"] == 1
    assert by["lake-big"]["queries"] == ["công viên", "hồ"] and by["lake-big"]["reviews"] == 2800


def test_same_plain_name_nearby_is_one_place(tmp_path):
    d = tmp_path / "search"
    rows = [{**_row("ga-big", reviews=4667), "name": "Ga Đà Lạt"},
            {**_row("ga-copy", lat=11.9408, reviews=1480), "name": "ga da lat"},  # ~90 m, no accents
            {**_row("ga-noname", lat=11.945, reviews=30), "name": "Ga"},  # city name removed: same name, ~550 m
            {**_row("branch", lat=11.96, reviews=900), "name": "Ga Đà Lạt"},  # ~2.2 km: another place
            {**_row("other", reviews=50), "name": "Ga Trại Mát"}]  # same point, other name: kept
    _write(d, "ga.jsonl", [_rec("ga xe lửa", rows)])
    lst = listing.build(d, AREA, top=100, city="Đà Lạt", same_name_m=1000)
    assert sorted(r["fid"] for r in lst["items"]) == ["branch", "ga-big", "other"] and lst["stats"]["same_place"] == 2


def test_few_reviews_or_unrated_are_not_listed(tmp_path):
    d = tmp_path / "search"
    _write(d, "a.jsonl", [_rec("thác", [_row("ok", rating=2.0, reviews=50), _row("few", rating=5.0, reviews=49),
                                         _row("unrated", rating=None, reviews=None)])])
    lst = listing.build(d, AREA, top=None, min_reviews=50)
    assert [r["fid"] for r in lst["items"]] == ["ok"] and lst["stats"]["few_reviews"] == 2


def test_card_without_reviews_does_not_hide_the_place(tmp_path):
    d = tmp_path / "search"
    _write(d, "a.jsonl", [_rec("thác", [_row("vale", rating=None, reviews=None)]),
                          _rec("thác", [_row("vale", rating=4.1, reviews=4712)], tile=(2, 2, 13))])
    _write(d, "b.jsonl", [_rec("khu rừng thông", [_row("vale", rating=None, reviews=None)])])
    lst = listing.build(d, AREA, top=None, min_reviews=50)
    assert [(r["fid"], r["reviews"], r["queries"]) for r in lst["items"]] == [("vale", 4712, ["khu rừng thông", "thác"])]


def test_few_reviews_do_not_beat_many(tmp_path):
    d = tmp_path / "search"
    _write(d, "cafe.jsonl", [_rec("quán cà phê", [
        _row("five-stars-3-reviews", rating=5.0, reviews=3),
        _row("4.7-2000-reviews", rating=4.7, reviews=2000),
        _row("4.4-100", rating=4.4, reviews=100),
        _row("3.9-150", rating=3.9, reviews=150),
    ])])
    order = [r["fid"] for r in listing.build(d, AREA, top=100)["items"]]
    assert order.index("4.7-2000-reviews") < order.index("five-stars-3-reviews")


def test_top_n_per_category(tmp_path):
    d = tmp_path / "search"
    _write(d, "a.jsonl", [_rec("quán cà phê", [_row(f"c{i}", rating=3 + i / 10, reviews=50) for i in range(10)])])
    _write(d, "b.jsonl", [_rec("chợ", [_row(f"m{i}", rating=4.0, reviews=10 * (i + 1)) for i in range(5)])])
    lst = listing.build(d, AREA, top=3)
    by_q = {}
    for r in lst["items"]:
        for q in r["queries"]:
            by_q.setdefault(q, []).append(r["fid"])
    assert by_q["quán cà phê"] == ["c9", "c8", "c7"] and len(by_q["chợ"]) == 3
    assert all(r["score"] is not None for r in lst["items"])


def test_unrated_places_come_last(tmp_path):
    d = tmp_path / "search"
    _write(d, "a.jsonl", [_rec("thác", [_row("unrated", rating=None, reviews=None), _row("rated", rating=3.0, reviews=5)])])
    assert [r["fid"] for r in listing.build(d, AREA, top=1)["items"]] == ["rated"]


@pytest.mark.parametrize("category", ["Khách sạn", "Nhà nghỉ", "Homestay", "Khu nghỉ dưỡng", "Biệt thự nghỉ dưỡng",
                                      "Nhà khách", "Căn hộ dịch vụ", "Nhà trọ", "Chỗ ở", "Nhà nghỉ thanh niên"])
def test_lodging_categories(category):
    assert listing.is_lodging(category)


@pytest.mark.parametrize("category", ["Quán cà phê", "Thác nước", "Điểm thu hút khách du lịch", "Khu cắm trại", None])
def test_not_lodging(category):
    assert not listing.is_lodging(category)


def test_run_writes_list(data, monkeypatch):
    monkeypatch.setattr(listing, "load_config", lambda city: ("Đà Lạt", {"area": AREA, "gmaps": {}}))
    _write(data / "search" / "dalat", "thac.jsonl", [_rec("thác", [_row("a"), _row("b")])])
    with pytest.raises(SystemExit):  # filter has not run
        listing.run("dalat")
    for fid, rel in (("a", "yes"), ("b", "no")):
        (data / "filter").mkdir(parents=True, exist_ok=True)
        (data / "filter" / f"{fid}.json").write_text(json.dumps({"fid": fid, "llm": {"relevance": rel, "reason": "r"}}))
    (data / "filter" / "summary.json").write_text("{}")
    assert listing.run("dalat")["places"] == 1
    assert json.loads((data / "list" / "dalat.json").read_text(encoding="utf-8"))["items"][0]["fid"] == "a"


def test_page_counts_replace_hidden_card_counts(tmp_path):
    d = tmp_path / "search"
    _write(d, "a.jsonl", [_rec("công viên", [_row("vale", rating=4.4, reviews=None), _row("small", rating=4.0, reviews=None)])])
    counts = {"vale": {"rating": 4.4, "reviews": 20225}, "small": {"rating": 4.0, "reviews": 12}}
    lst = listing.build(d, AREA, top=None, min_reviews=50, counts=counts)
    assert [(r["fid"], r["reviews"]) for r in lst["items"]] == [("vale", 20225)]


def test_place_filed_as_lodging_anywhere_is_lodging(tmp_path):
    d = tmp_path / "search"
    _write(d, "a.jsonl", [_rec("quán cà phê", [_row("hotel-cafe", category="Quán cà phê"), _row("cafe", category="Quán cà phê")]),
                          _rec("khu cắm trại", [_row("hotel-cafe", category="Khách sạn nghỉ dưỡng")], tile=(2, 2, 13))])
    assert [r["fid"] for r in listing.build(d, AREA, top=None)["items"]] == ["cafe"]


def test_stay_list_keeps_lodging_only_from_every_search(tmp_path):
    places, stay = tmp_path / "search" / "dalat", tmp_path / "search" / "dalat_stay"
    _write(places, "thac.jsonl", [_rec("thác", [_row("fall"), _row("hotel", category="Khách sạn", reviews=80)])])
    _write(stay, "homestay.jsonl", [_rec("homestay Phường 1 Đà Lạt", [
        _row("home", category="Homestay", reviews=40), _row("cafe", category="Quán cà phê"),
        _row("tiny", category="Nhà nghỉ", reviews=3), _row("far", 10.9, 106.7, category="Khách sạn")], lodging=True)])
    lst = listing.build_stay([places, stay], AREA, min_reviews=30)
    by = {r["fid"]: r for r in lst["items"]}
    assert sorted(by) == ["home", "hotel"]  # the cafe and the waterfall never enter it, the place list never gets hotels
    assert by["home"]["queries"] == ["homestay Phường 1 Đà Lạt"] and lst["stats"]["few_reviews"] == 1
    assert "hotel" not in {r["fid"] for r in listing.build(places, AREA, top=100)["items"]}


def test_stay_list_merges_one_hotel_seen_twice(tmp_path):
    stay = tmp_path / "search" / "dalat_stay"
    _write(stay, "khach-san.jsonl", [_rec("khách sạn Phường 1", [{**_row("h1", category="Khách sạn", reviews=200), "name": "Ana"}]),
                                     _rec("khách sạn Phường 2", [{**_row("h2", category="Khách sạn", reviews=50), "name": "Ana"}], tile=(2, 2, 13))])
    (h,) = listing.build_stay([stay], AREA, same_name_m=1000)["items"]  # same name, same point
    assert h["fid"] == "h1" and h["queries"] == ["khách sạn Phường 1", "khách sạn Phường 2"]
