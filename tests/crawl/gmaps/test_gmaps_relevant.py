from corpus.crawl.gmaps import relevant


def test_wanted_only_when_maps_shows_more_than_kept():
    assert relevant.wanted({"review_count": "1.701 bài đánh giá"}, 200)
    assert not relevant.wanted({"review_count": "120 bài đánh giá"}, 120)
    assert not relevant.wanted({"review_count": None}, 0)
