from corpus.observe.gmaps.details import day_type, details_pairs, lookup

R = {"details": [
    "Đã đến vào\nCuối tuần…",
    "Độ ồn\nYên tĩnh, dễ trò chuy…",
    "Thời gian chờ\n10 đến 30 phút",
    "Điểm đỗ xe\nKhông rõ",
    "Đồ ăn: 5…",
    "Dịch vụ: 2",
    "Bầu không khí: 5",
    "Dịch vụ:…",
    "Nhóm khách du lịch\nGia đình",
    "Nên đặt vé trước\nCó",
    "Thông tin đánh giá về mức giá\nQuá đắt",
]}


def test_details_map_to_features_and_skip_the_rest():
    assert [(f, v) for f, v, _ in details_pairs(R)] == [
        ("noise", "quiet"), ("wait_time", "short"), ("food_quality", "good"),
        ("service_quality", "poor"), ("booking_needed", "yes"), ("value_for_money", "poor")]


def test_quote_is_the_raw_line():
    assert details_pairs({"details": ["Độ ồn\nRất ồn, khó nghe"]}) == [("noise", "loud", "Độ ồn\nRất ồn, khó nghe")]


def test_more_tables():
    rows = ["Thời gian đợi\n1 giờ trở lên", "Điểm đỗ xe\nHơi khó tìm điểm đỗ xe", "Đặt chỗ\nChỉ khách vãng lai",
            "Đặt chỗ\nTuỳ theo ngày/giờ", "Đồ ăn: 3", "Thông tin đánh giá về mức giá\nGiá cả phải chăng"]
    assert [(f, v) for f, v, _ in details_pairs({"details": rows})] == [
        ("wait_time", "long"), ("parking", "hard"), ("booking_needed", "no"), ("food_quality", "mixed"),
        ("value_for_money", "good")]


def test_every_rule_value_is_in_the_ontology():
    from corpus.ontology import load
    ont = load()
    rows = [f"Đồ ăn: {n}" for n in "12345"] + [f"Dịch vụ: {n}" for n in "12345"]
    pairs = details_pairs({"details": rows})
    assert all(ont.valid(f, v) for f, v, _ in pairs)
    assert ("service_quality", "mixed") in [(f, v) for f, v, _ in pairs]  # Maps "Dịch vụ" stars rate the service
    assert not any(f == "service_attitude" for f, _, _ in pairs)  # stars say nothing about staff attitude


def test_day_type():
    assert day_type(R) == "weekend"
    assert day_type({"details": ["Đã đến vào\nNgày nghỉ lễ"]}) == "holiday"
    assert day_type({"details": []}) == "unknown"
    assert day_type({"details": ["Đã đến vào…"]}) == "unknown"
    assert day_type({}) == "unknown"


def test_truncated_value_needs_unambiguous_prefix():
    table = {"Abcd x": "a", "Abcd y": "b", "Efgh": "c"}
    assert lookup(table, "Abcd x…") == "a"
    assert lookup(table, "Abcd…") is None  # two different values
    assert lookup(table, "Abcd") is None  # not cut by Maps: must match exactly
    assert lookup(table, "Ef…") is None  # too short to trust
    assert lookup({"Ồn ào ở mức vừa phải": "moderate", "Ồn ào, nhưng bạn vẫn trò chuyện được": "moderate"}, "Ồn ào…") == "moderate"


def test_cut_value_that_could_be_khong_ro_gives_nothing():
    rows = ["Đặt chỗ\nKhông…", "Thời gian đợi\nKhông…", "Nên đặt vé trước\nKhông…", "Độ ồn\nKhông rõ",
            "Nên đặt vé trước\nKhông", "Thời gian đợi\nKhông cần đ…"]
    assert [(f, v) for f, v, _ in details_pairs({"details": rows})] == [("booking_needed", "no"), ("wait_time", "none")]


def test_free_text_answers_for_kids_wheelchair_vegetarian():
    rows = ["Độ thân thiện với trẻ em\nRất thân thiện", "Độ thân thiện với trẻ em\nBình thường",
            "Tình trạng có lối đi cho xe lăn\nKo", "Các món chay\nThuần chay", "Các món chay\nKHÔNG",
            "Các món chay\nKhông rõ"]
    assert [(f, v) for f, v, _ in details_pairs({"details": rows})] == [
        ("kids", "suitable"), ("wheelchair", "unsuitable"), ("vegetarian_options", "yes"), ("vegetarian_options", "no")]
