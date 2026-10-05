import json

from corpus.crawl.gmaps import keywords, photos

GROUPS = {"nature", "attraction", "cafe"}


def test_keywords_only_for_experience_places_with_reviews_left():
    lake = {"category": "Hồ", "review_count": "1.234 bài đánh giá"}
    assert keywords.category_group("Thác nước") == "nature" and keywords.category_group("Nhà hàng") == "restaurant"
    assert keywords.wanted(lake, 200, GROUPS)
    assert not keywords.wanted(lake, 1234, GROUPS)  # crawl already kept every review
    assert not keywords.wanted({"category": "Nhà hàng", "review_count": "900 bài đánh giá"}, 200, GROUPS)


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
