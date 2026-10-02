from corpus.aggregate.estimates import amounts_vnd, entry_fee, estimates, group, visit_minutes


def _fee(i, quote, author):
    return {"id": f"x:{i}", "feature": "entry_fee", "value": "paid", "author": author, "span": {"quote": quote}}


def test_amounts_in_review_words():
    assert amounts_vnd("Vé vào cổng 50k/người/lượt") == [50000]
    assert amounts_vnd("thu phí vào cửa là 160.000 đồng/người") == [160000]
    assert amounts_vnd("Vé người lớn: 65k Vé trẻ em: 45k") == [65000, 45000]
    assert amounts_vnd("Mua vé 150.000đ/2 người") == [150000]
    assert amounts_vnd("vé 99k và 150k") == [99000, 150000]
    assert amounts_vnd("Mua vé trước, đi 2 người, 3 tiếng") == []
    assert amounts_vnd("Phí vào cửa là 120.000 dinar/người") == []


def test_entry_fee_from_quotes_one_value_per_author_then_maps_tickets():
    fee = entry_fee([_fee(1, "vé 50k", "a"), _fee(2, "Vé người lớn: 65k Vé trẻ em: 45k", "b"), _fee(3, "vé 100k", "c"),
                     _fee(4, "Mua vé trước", "d")])
    assert fee == {"min_vnd": 50000, "typical_vnd": 65000, "max_vnd": 100000, "n": 3, "source": "reviews"}
    assert entry_fee([_fee(1, "Mua vé trước", "a")], 5.78)["source"] == "maps_tickets"
    assert entry_fee([], None) is None


def test_category_groups():
    assert group("Quán cà phê")["id"] == "cafe"
    assert group("Điểm thu hút khách du lịch")["id"] == "attraction"
    assert group("Spa sức khỏe")["id"] == "spa"
    assert group("Cửa hàng thời trang")["id"] == "shop"  # not "thờ" of a temple
    assert group(None)["id"] == "other"


def test_visit_minutes_reviews_win_only_with_enough_agreeing_authors():
    assert visit_minutes("Quán cà phê", None)["source"] == "category_default"
    weak = {"n": 2, "status": "signal", "top_value": "half_day"}
    assert visit_minutes("Quán cà phê", weak)["source"] == "category_default"
    got = visit_minutes("Quán cà phê", {**weak, "n": 3})
    assert (got["short"], got["long"], got["source"]) == (180, 300, "reviews")
    assert estimates("Nhà hàng", {}, [])["usable_as_default"] == ["meal", "anchor", "backup"]
