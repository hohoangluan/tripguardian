from corpus.observe.gmaps.place_rules import attribute_pairs, parse_popular_times, parse_price
from corpus.ontology import load


def test_attributes_map_to_features():
    attrs = ["Phù hợp cho trẻ em", "Có hoạt động phù hợp với trẻ em", "Phù hợp khi đi theo nhóm", "Có chỗ ngồi ngoài trời",
             "Không có lối vào cho xe lăn", "Phù hợp để làm việc trên máy tính xách tay", "Có nhà vệ sinh", "Có Wi-Fi"]
    assert [(f, v) for f, v, _ in attribute_pairs(attrs)] == [
        ("kids", "suitable"), ("kids", "suitable"), ("groups", "suitable"), ("outdoor_seating", "present"),
        ("wheelchair", "unsuitable"), ("laptop_friendly", "present")]
    assert attribute_pairs(["Có lối vào dành riêng cho xe lăn"]) == [("wheelchair", "suitable", "Có lối vào dành riêng cho xe lăn")]
    assert attribute_pairs(None) == []


def test_attribute_values_are_in_the_ontology():
    from corpus.observe.gmaps.place_rules import ATTRIBUTES
    ont = load()
    assert all(ont.valid(f, v) for f, v in ATTRIBUTES.values())


def day(pcts, start=6):
    return [f"Mức độ đông là {p}% lúc {start + i:02d} giờ." for i, p in enumerate(pcts)]


def test_popular_times_sunday_first_by_hour():
    raw = [day([10, 50])] + [day([0, 0])] * 5 + [day([30, 90])]
    pt = parse_popular_times(raw)
    assert pt["sun"] == {6: 10, 7: 50}
    assert "mon" not in pt  # all zero: closed that day
    assert pt["sat"] == {6: 30, 7: 90}


def test_popular_times_live_line_and_missing():
    raw = [["Hiện mức độ đông là 40%, thường mức độ đông là 50%.", "Mức độ đông là 20% lúc 09 giờ."]] + [[]] * 6
    assert parse_popular_times(raw) == {"sun": {9: 20}}
    assert parse_popular_times(None) is None and parse_popular_times([]) is None
    assert parse_popular_times([[]] * 7) is None


def test_price():
    assert parse_price("Khoảng giá, 100.000-200.000\xa0₫/người, 7 người đã báo cáo") == {
        "min_vnd": 100000, "max_vnd": 200000, "per": "person", "reports": 7}
    assert parse_price("Khoảng giá, 1-100.000\xa0₫/người, 12 người đã báo cáo")["max_vnd"] == 100000
    assert parse_price("Giá vừa phải") == {"level": "moderate"}
    assert parse_price(None) is None and parse_price("Khoảng giá, lạ") is None


def test_inferred_or_bare_labels_are_not_mapped():
    assert attribute_pairs(["Có thực đơn dành cho trẻ em", "Lối vào cho xe lăn"]) == []


def test_price_above():
    assert parse_price("Khoảng giá, Trên 1.000.000\xa0₫/người, 3 người đã báo cáo") == {
        "min_vnd": 1000000, "max_vnd": None, "per": "person", "reports": 3}
