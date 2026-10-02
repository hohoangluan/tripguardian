from datetime import date

import pytest

from live import holidays as mod


def test_a_listed_date_comes_back_with_its_name():
    got = mod.holidays([date(2026, 1, 1)])
    assert got == {date(2026, 1, 1): "Tết Dương lịch"}


def test_an_unlisted_date_is_simply_not_a_holiday():
    assert mod.holidays([date(2026, 3, 11)]) == {}


def test_a_mixed_list_keeps_only_the_holidays():
    got = mod.holidays([date(2026, 4, 30), date(2026, 5, 1), date(2026, 5, 2)])
    assert set(got) == {date(2026, 4, 30), date(2026, 5, 1)}


def test_an_empty_request_is_an_empty_answer():
    assert mod.holidays([]) == {}


def test_the_shipped_file_covers_the_fixed_date_holidays_of_2026():
    want = [date(2026, 1, 1), date(2026, 4, 30), date(2026, 5, 1), date(2026, 9, 2)]
    assert set(mod.holidays(want)) == set(want)


def test_tet_2026_is_several_days_long():
    span = [date(2026, 2, d) for d in range(14, 24)]
    got = mod.holidays(span)
    assert len(got) >= 5
    assert date(2026, 2, 17) in got  # mùng 1 Tết Bính Ngọ


def test_a_file_whose_keys_yaml_already_parsed_as_dates_still_loads(tmp_path):
    p = tmp_path / "h.yaml"
    p.write_text("holidays:\n  2026-01-01: Tết Dương lịch\n", encoding="utf-8")
    mod._table.cache_clear()
    assert mod.holidays([date(2026, 1, 1)], path=p) == {date(2026, 1, 1): "Tết Dương lịch"}
    mod._table.cache_clear()


def test_a_file_whose_keys_are_quoted_strings_still_loads(tmp_path):
    p = tmp_path / "h.yaml"
    p.write_text('holidays:\n  "2026-01-01": Tết Dương lịch\n', encoding="utf-8")
    mod._table.cache_clear()
    assert mod.holidays([date(2026, 1, 1)], path=p) == {date(2026, 1, 1): "Tết Dương lịch"}
    mod._table.cache_clear()
