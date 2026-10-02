from corpus.crawl.gmaps.photos import month, norm, sized


def test_sized_asks_for_the_wanted_size():
    url = "https://lh3.googleusercontent.com/gps-cs-s/ABC=w203-h360-k-no"
    assert sized(url, 768) == "https://lh3.googleusercontent.com/gps-cs-s/ABC=w768-h768-k-no"
    assert sized("//lh3.googleusercontent.com/p/XYZ", 512) == "https://lh3.googleusercontent.com/p/XYZ=w512-h512-k-no"


def test_month_of_the_viewer_lines():
    assert month("Ảnh - thg 9 2026") == "2026-09" and month("thg 12 2024") == "2024-12"
    assert month("Ảnh - 2 tuần trước") is None and month(None) is None


def test_owner_name_match_ignores_case_and_punctuation():
    assert norm("Mộc Hương Spa - Dưỡng sinh") == norm("mộc hương spa dưỡng sinh")
