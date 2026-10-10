import pytest

from live.geocode import address
from live.http import Unavailable


def row(text, addr, lat=10.75, lng=106.6, kind="street"):
    return {"text": text, "address": addr, "province": "Thành phố Hồ Chí Minh", "lat": lat, "lng": lng, "kind": kind,
            "source": "photon", "fetched_at": "2026-10-09T00:00:00+00:00"}


ALLEY = row("Hẻm 55/13 Đường 18B", "Bình Hưng Hòa, Thành phố Hồ Chí Minh", 10.7501, 106.5901)
ALLEY_55 = row("Hẻm 55 Đường 18B", "Bình Hưng Hòa, Thành phố Hồ Chí Minh", 10.7502, 106.5902)
STREET_BHH = row("Đường 18B", "Bình Hưng Hòa, Thành phố Hồ Chí Minh", 10.7503, 106.5903)
STREET_PL = row("Đường 18B", "Phước Long, Thành phố Hồ Chí Minh", 10.8, 106.77)
OTHER = row("Đường Lê Lợi", "Quận 1, Thành phố Hồ Chí Minh")


def fake(table, calls=None):
    def search(q, cfg, limit):
        if calls is not None:
            calls.append(q)
        got = table.get(q, [])
        if isinstance(got, Exception):
            raise got
        return got
    return search


def test_house_in_a_mapped_alley_is_the_alley_labelled_approximate():
    calls = []
    table = {"55/13/19 đường 18b": [STREET_PL, ALLEY, STREET_BHH, ALLEY_55]}
    rows = address.search("55/13/19 đường 18b", None, 6, fake(table, calls))
    lead = rows[0]
    assert lead["approx"] is True and lead["text"] == "55/13/19 đường 18b"
    assert (lead["lat"], lead["lng"]) == (ALLEY["lat"], ALLEY["lng"])  # the alley's own point, nothing made up
    assert lead["address"] == "Hẻm 55/13 Đường 18B, Bình Hưng Hòa, Thành phố Hồ Chí Minh"  # the real row it stands on
    assert [r["text"] for r in rows[1:]][0] == "Hẻm 55/13 Đường 18B"  # the real rows follow, best first
    assert calls == ["55/13/19 đường 18b"]  # the alley is already as deep as the map goes: no extra request


def test_falls_back_to_a_shorter_number_then_the_bare_street():
    calls = []
    table = {"55/13/19 đường 18b": [STREET_PL, STREET_BHH], "55/13 đường 18b": [ALLEY], "55 đường 18b": [ALLEY_55],
             "đường 18b": [STREET_BHH]}
    rows = address.search("55/13/19 đường 18b", None, 6, fake(table, calls))
    assert rows[0]["approx"] and (rows[0]["lat"], rows[0]["lng"]) == (ALLEY["lat"], ALLEY["lng"])
    assert "55/13 đường 18b" in calls and "55 đường 18b" in calls


def test_street_only_when_no_number_is_mapped():
    table = {"7/3 đường 18b": [STREET_BHH, STREET_PL], "7 đường 18b": [], "đường 18b": [STREET_BHH, STREET_PL]}
    rows = address.search("7/3 đường 18b", None, 6, fake(table))
    assert rows[0]["approx"] and (rows[0]["lat"], rows[0]["lng"]) == (STREET_BHH["lat"], STREET_BHH["lng"])


def test_a_typed_ward_picks_between_streets_of_the_same_name():
    table = {"7 đường 18b, phước long": [STREET_BHH, STREET_PL], "đường 18b, phước long": [STREET_BHH, STREET_PL]}
    rows = address.search("7 đường 18b, phước long", None, 6, fake(table))
    assert (rows[0]["lat"], rows[0]["lng"]) == (STREET_PL["lat"], STREET_PL["lng"])


def test_a_full_match_is_not_marked_approximate():
    exact = row("Hẻm 55/13/19 Đường 18B", "Bình Hưng Hòa, Thành phố Hồ Chí Minh")
    rows = address.search("55/13/19 đường 18b", None, 6, fake({"55/13/19 đường 18b": [exact, ALLEY]}))
    assert rows[0] == exact and not any(r.get("approx") for r in rows)


def test_rows_of_other_streets_never_become_the_answer():
    table = {"12 đường 18b": [OTHER], "đường 18b": [OTHER]}
    rows = address.search("12 đường 18b", None, 6, fake(table))
    assert rows == [OTHER]  # shown as the source gave them, none claimed to be the address


def test_city_abbreviations_are_spelled_out():
    calls = []
    address.search("đường 18b, tphcm", None, 6, fake({}, calls))
    assert calls[0] == "đường 18b, Hồ Chí Minh"


def test_trailing_segments_are_dropped_when_nothing_matches():
    calls = []
    table = {"đường 18b, bình hưng hòa, hồ chí minh": [], "đường 18b, bình hưng hòa": [STREET_BHH]}
    rows = address.search("đường 18b, bình hưng hòa, hồ chí minh", None, 6, fake(table, calls))
    assert rows == [STREET_BHH] and calls[-1] == "đường 18b, bình hưng hòa"


def test_text_without_a_number_is_a_plain_search():
    calls = []
    rows = address.search("hồ xuân hương", None, 6, fake({"hồ xuân hương": [OTHER]}, calls))
    assert rows == [OTHER] and calls == ["hồ xuân hương"]


def test_a_failed_shorter_search_is_skipped_but_a_failed_first_one_raises():
    table = {"55/13/19 đường 18b": [STREET_BHH], "55/13 đường 18b": Unavailable("down"), "55 đường 18b": [ALLEY_55]}
    rows = address.search("55/13/19 đường 18b", None, 6, fake(table))
    assert rows[0]["approx"] and (rows[0]["lat"], rows[0]["lng"]) == (ALLEY_55["lat"], ALLEY_55["lng"])
    with pytest.raises(Unavailable):
        address.search("55/13/19 đường 18b", None, 6, fake({"55/13/19 đường 18b": Unavailable("down")}))
