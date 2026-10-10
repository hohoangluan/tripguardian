from datetime import date

import pytest

from trip.domain import values
from trip.domain.resolve import anchor_for, search
from trip.domain.state import Base


def test_exact_name_matches(catalog):
    a = anchor_for("Vườn Phẳng Lặng Xanh", catalog)
    assert (a.state, a.place_id) == ("matched", "0x11:0x1")


def test_shared_words_ask_to_choose(catalog):
    a = anchor_for("Quán Yên Tĩnh", catalog)
    assert a.state == "choose" and len(a.candidates) == 3


def test_generic_words_never_match(catalog):
    assert anchor_for("quán cà phê", catalog).state == "missing"


def test_links(catalog):
    maps = "https://www.google.com/maps/place/X/data=!4m2!3m1!1s0x11:0x1"
    assert anchor_for(maps, catalog).place_id == "0x11:0x1"
    tt = "https://www.tiktok.com/@a/video/7565853238147255573"
    assert anchor_for(tt, catalog).place_id == "0x11:0x1"
    assert anchor_for("https://maps.app.goo.gl/abc", catalog).state == "missing"


def test_search_prefers_prefix(catalog):
    assert search("Vườn Phẳng", catalog)[0].id == "0x11:0x1"
    assert search("x", catalog) == []


def test_value_parsing(catalog):
    assert values.clock("9h") == "09:00" and values.clock("14:30") == "14:30"
    assert values.money("300k") == 300_000 and values.money("1,5tr") == 1_500_000
    assert values.parse("start_date", "2026-12-12", catalog) == date(2026, 12, 12)
    assert values.parse("days", "3 ngày", catalog) == 3
    assert values.parse("hard", "steep_or_stairs!=present", catalog) == {"feature": "steep_or_stairs", "op": "ne",
                                                                         "value": "present"}
    assert values.parse("soft", "noise=quiet", catalog) == ("noise=quiet", "love")
    assert values.parse("soft", "crowd=low@time_of_day.morning:avoid", catalog) == ("crowd=low@time_of_day.morning", "avoid")
    assert values.parse("base", "0x11:0x1", catalog) == Base(place_id="0x11:0x1", text="Vườn Phẳng Lặng Xanh")
    assert values.parse("base", "gần chợ", catalog) == Base(place_id=None, text="gần chợ")
    for field, raw in (("hard", "steep_or_stairs!=maybe"), ("soft", "nope=present"), ("checkin_at", "sáng"), ("days", "")):
        with pytest.raises(ValueError):
            values.parse(field, raw, catalog)
    assert values.parse_remove("soft", "noise=quiet:love") == "noise=quiet"
    assert values.parse_remove("hard", "steep_or_stairs!=present") == "steep_or_stairs"
