import json

from corpus.crawl.gmaps import keywords, photos

SETS = [{"words": ["dốc", "đi bộ"], "groups": ["nature", "attraction"]}, {"words": ["vé"], "groups": ["nature"]},
        {"words": ["đặt bàn"], "groups": ["restaurant"]}]


def test_each_place_gets_the_words_of_its_category_group_and_only_new_ones(tmp_path):
    lake = {"category": "Hồ", "review_count": "1.234 bài đánh giá"}
    assert keywords.category_group("Thác nước") == "nature" and keywords.category_group("Nhà hàng") == "restaurant"
    assert keywords.words_for(lake, 200, SETS) == ["dốc", "đi bộ", "vé"]
    assert keywords.words_for(lake, 1234, SETS) == []  # crawl already kept every review
    assert keywords.words_for({"category": "Nhà hàng", "review_count": "900 bài đánh giá"}, 200, SETS) == ["đặt bàn"]
    f = tmp_path / "reviews_keywords.json"
    f.write_text(json.dumps({"keywords": {"dốc": {"complete": True, "reviews": []},
                                          "đi bộ": {"complete": True, "reviews": []}}}), encoding="utf-8")
    assert keywords.missing(f, ["dốc", "đi bộ", "vé"]) == ["vé"]


def test_sights_want_more_photos_and_a_capped_old_file_is_fetched_again(tmp_path):
    c = {"photos_per_place": 12, "photos_per_sight": 30, "photo_groups": ["nature"]}
    assert photos.want({"category": "Thác"}, c) == 30 and photos.want({"category": "Quán cà phê"}, c) == 12
    f = tmp_path / "photos.json"
    assert photos.needs_fetch(f, 30, 12)
    f.write_text(json.dumps({"complete": True, "photos": [{}] * 12}), encoding="utf-8")
    assert photos.needs_fetch(f, 30, 12) and not photos.needs_fetch(f, 12, 12)
    f.write_text(json.dumps({"complete": True, "photos": [{}] * 7}), encoding="utf-8")  # the gallery ended at 7
    assert not photos.needs_fetch(f, 30, 12)
    f.write_text(json.dumps({"wanted": 30, "complete": True, "photos": [{}] * 30}), encoding="utf-8")
    assert not photos.needs_fetch(f, 30, 12)
