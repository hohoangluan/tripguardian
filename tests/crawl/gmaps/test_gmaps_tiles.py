from gmaps_helpers import AREA

from corpus.crawl.gmaps import tiles


def test_root_tiles_cover_area():
    ts = tiles.root_tiles(AREA, 13)
    assert all(z == 13 for _, _, z in ts)
    lat_span, lng_span = tiles.span(13, 11.95)
    for lat in (AREA[0], 11.95, AREA[2]):  # every corner and the middle falls in some tile's viewport
        for lng in (AREA[1], 108.48, AREA[3]):
            assert any(abs(lat - a) <= lat_span / 2 and abs(lng - b) <= lng_span / 2 for a, b, _ in ts)


def test_children_split_viewport_in_four():
    kids = tiles.children((11.94, 108.44, 13))
    lat_span, lng_span = tiles.span(13, 11.94)
    assert len(kids) == 4 and all(z == 14 for _, _, z in kids)
    assert {round(a - 11.94, 6) for a, _, _ in kids} == {round(-lat_span / 4, 6), round(lat_span / 4, 6)}
    assert {round(b - 108.44, 6) for _, b, _ in kids} == {round(-lng_span / 4, 6), round(lng_span / 4, 6)}


def test_in_area():
    assert tiles.in_area(11.94, 108.44, AREA)  # Chợ Đà Lạt
    assert not tiles.in_area(10.93, 106.77, AREA)  # Hồ Chí Minh
    assert not tiles.in_area(None, None, AREA)
    assert tiles.in_area(None, None, None)
