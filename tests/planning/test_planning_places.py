
import pytest
from plan_fixtures import all_days, decision, rec

from live import Unavailable
from planning import places as pl
from planning import settings

CFG = settings.load(settings.PATH)


def test_hours_become_minutes_and_a_close_after_midnight_runs_into_the_next_day():
    got = pl.parse_hours({"mon": [["09:00", "21:00"]], "fri": [["18:00", "02:00"]], "sat": [["00:00", "23:59"]]})
    assert got["mon"] == [(540, 1260)] and got["fri"] == [(1080, 1560)] and got["sat"] == [(0, 1439)]


def test_windows_on_tells_closed_from_unknown():
    hours = pl.parse_hours({**all_days(), "mon": []})
    assert pl.windows_on(hours, "mon") == []                       # closed that day
    assert pl.windows_on(hours, "tue") == [(480, 1260)]
    assert pl.windows_on(None, "tue") is None                      # the record has no hours
    assert pl.windows_on(hours, None) == [(480, 1260)]             # weekday unknown: the hours every open day shares
    assert pl.windows_on(pl.parse_hours(all_days()), None) == [(480, 1260)]   # the same every day: weekday not needed


def test_a_confirmed_place_becomes_a_place_with_its_record_facts():
    r = rec("a", 11.94, 108.45, usable=("experience", "backup"), features={"sunset_view": "present"},
            price={"min_vnd": 50000, "typical_vnd": 60000, "max_vnd": 70000})
    d = decision(["a"], roles={"a": "anchor"}, flags={"a": ["giờ mở cửa chưa chắc"]}, relaxed={"a": ["long_walk"]})
    places, unplaced = pl.build_places(d, {"a": r}, CFG)
    p = places[0]
    assert unplaced == []
    assert (p.id, p.kind, p.role, p.visit["typical"], p.cost_vnd) == ("a", "experience", "anchor", 60, 60000)
    assert p.pins == ("sunset_view",) and p.flags == ("giờ mở cửa chưa chắc",) and p.relaxed == ("long_walk",)


def test_a_place_that_cannot_be_scheduled_is_reported_with_its_reason_not_dropped_silently():
    no_coord = rec("c", None, None)
    meal_less = rec("d", 11.9, 108.4, usable=("backup",))
    d = decision(["missing", "c", "d"])
    places, unplaced = pl.build_places(d, {"c": no_coord, "d": meal_less}, CFG)
    assert places == []
    assert {u.id: u.reason for u in unplaced} == {"missing": "no_record", "c": "no_coordinates", "d": "not_plannable"}


def test_a_meal_only_place_is_a_meal_and_a_place_with_both_is_an_experience():
    both = rec("a", 11.9, 108.4, usable=("experience", "meal", "backup"))
    meal = rec("b", 11.9, 108.4, usable=("meal", "backup"))
    places, _ = pl.build_places(decision(["a", "b"]), {"a": both, "b": meal}, CFG)
    assert {p.id: p.kind for p in places} == {"a": "experience", "b": "meal"}


def test_cost_comes_from_the_fee_then_the_price_range_and_is_none_when_unknown():
    assert pl.cost_of({"entry_fee": {"typical_vnd": 40000}, "price_per_person": None}) == 40000
    assert pl.cost_of({"entry_fee": None, "price_per_person": {"value": {"min_vnd": 100000, "max_vnd": 200000}}}) == 150000
    assert pl.cost_of({"entry_fee": None, "price_per_person": None}) is None


def test_a_base_in_the_corpus_resolves_without_geocoding():
    by_id = {"x": rec("x", 11.95, 108.44, name="Quán X")}
    point, why = pl.resolve_point({"place_id": "x", "text": "Quán X"}, by_id, geocode=lambda t: pytest.fail("no call"))
    assert (point.lat, point.lng, point.source, why) == (11.95, 108.44, "corpus", None)


def test_a_typed_point_is_geocoded_and_keeps_its_source():
    hit = {"lat": 11.9404, "lng": 108.4583, "label": "Bến xe", "source": "nominatim", "fetched_at": "t"}
    point, why = pl.resolve_point({"place_id": None, "text": "Bến xe Liên tỉnh"}, {}, geocode=lambda t: hit)
    assert (point.source, point.fetched_at, why) == ("nominatim", "t", None)


@pytest.mark.parametrize("base,geo,reason", [
    (None, lambda t: None, "unknown"),
    ({"place_id": None, "text": "  "}, lambda t: None, "unknown"),
    ({"place_id": None, "text": "nơi lạ"}, lambda t: None, "not_found"),
])
def test_a_point_that_cannot_be_resolved_says_why(base, geo, reason):
    assert pl.resolve_point(base, {}, geo) == (None, reason)


def test_a_dead_geocoder_is_a_reason_not_a_crash():
    def dead(text):
        raise Unavailable("down")

    assert pl.resolve_point({"place_id": None, "text": "Bến xe"}, {}, dead) == (None, "geocode_unavailable")


def test_with_an_unknown_weekday_a_place_open_later_some_days_is_held_to_the_later_hours():
    hours = pl.parse_hours({**all_days(), "mon": [["15:00", "21:00"]]})
    assert pl.windows_on(hours, None) == [(900, 1260)]
    assert pl.windows_on(pl.parse_hours({"mon": [["08:00", "10:00"]], "tue": [["15:00", "20:00"]]}), None) is None
    assert pl.hours_vary(hours) and not pl.hours_vary(pl.parse_hours(all_days()))
