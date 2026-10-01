from corpus.observe.gmaps.prep import age_days, batches, keep_for_llm, observed_at, stars


def test_age_days():
    assert age_days("2 tuần trước") == 14
    assert age_days("một tháng trước") == 30
    assert age_days("3 ngày trước trên Google") == 3
    assert age_days("5 giờ trước") == 0
    assert age_days("một năm trước") == 365
    assert age_days("") is None and age_days(None) is None


def test_observed_at():
    assert observed_at("2 tuần trước", "2026-09-30T08:00:00+00:00") == "2026-09-16"
    assert observed_at("không rõ", "2026-09-30T08:00:00+00:00") is None


def test_stars():
    assert stars("5 sao") == 5 and stars("4/5") == 4 and stars(None) is None and stars("") is None


def rv(i, text, author="a"):
    return {"review_id": f"R{i}", "text": text, "author_hash": author}


def test_keep_for_llm_drops_empty_short_flagged_and_duplicates():
    reviews = [rv(1, "Quán đẹp, view đồi thông rất chill"), rv(2, ""), rv(3, "Được rồi"),
               rv(4, "Liên hệ 0909 để đặt tour giá rẻ"), rv(5, "Quán đẹp, view đồi thông rất chill"),
               rv(6, "Quán đẹp, view đồi thông rất chill", author="b")]
    assert [r["review_id"] for r in keep_for_llm(reviews, {"R4"})] == ["R1", "R6"]


def test_batches_by_count_and_chars():
    small = [(f"r{i}", {"text": "x" * 10}) for i in range(20)]
    assert [len(b) for b in batches(small)] == [15, 5]
    big = [(f"r{i}", {"text": "x" * 5000}) for i in range(3)]
    assert [len(b) for b in batches(big, max_chars=12000)] == [2, 1]
    huge = [("r1", {"text": "x" * 20000}), ("r2", {"text": "x"})]
    assert [len(b) for b in batches(huge, max_chars=12000)] == [1, 1]
