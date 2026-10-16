from corpus.crawl.gmaps import menu

SKIP = {*menu.MAIN_TABS, "Cơm", "Menu", "Điểm nổi bật"}


def test_parse_lines_names_english_popular_price():
    text = "\n".join(["Tổng quan", "Thực đơn", "Menu", " ", "Điểm nổi bật", "Phổ biến", "Cơm Lam", "(Bamboo rice)", "Cá Tầm", "50.000 ₫", "Cơm"])
    got = menu.parse_lines(text, SKIP)
    assert got == [{"name": "Cơm Lam", "popular": True, "name_en": "Bamboo rice"},
                   {"name": "Cá Tầm", "popular": False, "price": "50.000 ₫"}]


def test_best_takes_the_widest_picture_and_ignores_thumbnails():
    small, big = ("x=w112-h112-p", b"s" * 10), ("y=w1024-h1024-k", b"b" * 70_000)
    assert menu.best([small, big]) == big
    assert menu.best([small]) is None
