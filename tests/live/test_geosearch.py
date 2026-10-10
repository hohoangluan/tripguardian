import pytest

from live import settings
from live.geocode import nominatim, photon
from live.http import Unavailable

FEATURES = {"type": "FeatureCollection", "features": [
    {"geometry": {"coordinates": [106.7107, 10.8149]},
     "properties": {"name": "Bến xe Miền Đông", "housenumber": "292", "street": "Đường Đinh Bộ Lĩnh",
                    "district": "Bình Thạnh", "city": "Thành phố Hồ Chí Minh", "state": "Thành phố Hồ Chí Minh",
                    "countrycode": "VN"}},
    {"geometry": {"coordinates": [106.7107, 10.8149]},  # the same row twice: kept once
     "properties": {"name": "Bến xe Miền Đông", "housenumber": "292", "street": "Đường Đinh Bộ Lĩnh",
                    "district": "Bình Thạnh", "city": "Thành phố Hồ Chí Minh", "state": "Thành phố Hồ Chí Minh",
                    "countrycode": "VN"}},
    {"geometry": {"coordinates": [109.58, 19.52]},  # inside the search box but in China: dropped
     "properties": {"name": "儋州市", "state": "海南省", "countrycode": "CN"}},
    {"geometry": {}, "properties": {"name": "no point", "countrycode": "VN"}}]}


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


@pytest.fixture
def cfg():
    settings.load.cache_clear()
    yield settings.load(settings.PATH)
    settings.load.cache_clear()


def test_photon_rows_carry_name_address_province_and_provenance(cfg, monkeypatch):
    calls = []
    monkeypatch.setattr(photon, "get_json", lambda url, ua, t: calls.append(url) or FEATURES)
    rows = photon.geosearch("bến xe miền đông", cfg)
    assert len(rows) == 1 and rows[0]["text"] == "Bến xe Miền Đông" and rows[0]["province"] == "Thành phố Hồ Chí Minh"
    assert rows[0]["address"] == "292 Đường Đinh Bộ Lĩnh, Bình Thạnh, Thành phố Hồ Chí Minh" and rows[0]["source"] == "photon"
    assert photon.geosearch("Bến xe  Miền Đông", cfg) == rows and len(calls) == 1  # cached, same text folded
    assert photon.geosearch("b", cfg) == [] and len(calls) == 1  # one letter is not a search


def test_nominatim_answers_when_photon_does_not(cfg, monkeypatch):
    def down(*a):
        raise Unavailable("photon down")
    monkeypatch.setattr(photon, "get_json", down)
    monkeypatch.setattr(nominatim, "get_json", lambda url, ua, t: [
        {"name": "Chợ Đà Lạt", "display_name": "Chợ Đà Lạt, Xuân Hương, Lâm Đồng", "lat": "11.94", "lon": "108.43",
         "address": {"state": "Lâm Đồng"}}])
    monkeypatch.setattr(nominatim, "_last_call", 0.0)
    (row,) = photon.geosearch("chợ đà lạt", cfg)
    assert row["source"] == "nominatim" and row["province"] == "Lâm Đồng" and row["lat"] == 11.94


def test_both_down_is_unavailable_never_a_guess(cfg, monkeypatch):
    def down(*a):
        raise Unavailable("down")
    monkeypatch.setattr(photon, "get_json", down)
    monkeypatch.setattr(nominatim, "get_json", down)
    monkeypatch.setattr(nominatim, "_last_call", 0.0)
    with pytest.raises(Unavailable):
        photon.geosearch("quận 1", cfg)


def _feature(name, key, value, district="Ba Đình", city="Hà Nội", lng=105.8, lat=21.0):
    return {"geometry": {"coordinates": [lng, lat]},
            "properties": {"name": name, "osm_key": key, "osm_value": value, "district": district, "city": city,
                           "countrycode": "VN"}}


def test_roads_under_construction_plots_and_rail_lines_are_not_places_and_rows_carry_a_kind(cfg, monkeypatch):
    body = {"features": [
        _feature("Hà Nội", "place", "city"),
        _feature("Đường cao tốc Vành đai 3", "highway", "motorway", "Lĩnh Nam"),
        _feature("Dự án khách sạn", "landuse", "plot"),
        _feature("Khách sạn và nhà ở kết hợp", "building", "construction"),
        _feature("Đường sắt đô thị số 1", "railway", "subway"),
        _feature("Sân bay quốc tế Nội Bài", "aeroway", "aerodrome"),
        _feature("Hẻm 55/13 Đường 18B", "highway", "service"),
        _feature("Ana Mandara Villas", "tourism", "resort")]}
    monkeypatch.setattr(photon, "get_json", lambda url, ua, t: body)
    rows = photon.geosearch("noi", cfg)
    assert [(r["text"], r["kind"]) for r in rows] == [
        ("Hà Nội", "area"), ("Sân bay quốc tế Nội Bài", "transport"), ("Hẻm 55/13 Đường 18B", "street"),
        ("Ana Mandara Villas", "stay")]
