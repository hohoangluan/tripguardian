import importlib
from datetime import date

import pytest

events_mod = importlib.import_module("live.events")
adv_mod = importlib.import_module("live.advisories")


def write(tmp_path, text):
    f = tmp_path / "f.yaml"
    f.write_text(text, encoding="utf-8")
    return f


def test_an_event_covers_every_date_inside_it_and_none_outside(tmp_path):
    f = write(tmp_path, 'events:\n  - {name: Noel, start: "2026-12-24", end: "2026-12-26", crowd: peak}\n')
    got = events_mod.events([date(2026, 12, 23), date(2026, 12, 24), date(2026, 12, 26), date(2026, 12, 27)], f)
    assert set(got) == {date(2026, 12, 24), date(2026, 12, 26)}
    assert got[date(2026, 12, 24)] == [{"name": "Noel", "crowd": "peak", "closure_risk": False}]


def test_a_bad_event_is_refused_not_guessed(tmp_path):
    with pytest.raises(ValueError):
        events_mod.events([date(2026, 12, 24)], write(tmp_path, 'events:\n  - {name: X, start: "2026-12-26", end: "2026-12-24"}\n'))
    with pytest.raises(ValueError):
        events_mod.events([date(2026, 12, 24)], write(tmp_path, 'events:\n  - {name: X, start: "2026-12-24", end: "2026-12-26", crowd: huge}\n'))


def test_the_shipped_events_mark_tet_as_a_closure_period():
    got = events_mod.events([date(2027, 2, 6)])
    assert got[date(2027, 2, 6)][0]["closure_risk"] is True


def test_an_advisory_keeps_its_source_and_area(tmp_path):
    f = write(tmp_path, 'advisories:\n  - {kind: landslide, severity: severe, start: "2026-11-02", end: "2026-11-03", '
                        'area: {lat: 11.9, lng: 108.4, radius_km: 5}, note: n, source: "KTTV"}\n')
    (a,) = adv_mod.advisories([date(2026, 11, 3)], f)[date(2026, 11, 3)]
    assert a["area"] == {"lat": 11.9, "lng": 108.4, "radius_km": 5.0} and a["source"] == "KTTV"
    assert adv_mod.advisories([date(2026, 11, 4)], f) == {}


def test_an_advisory_without_a_source_or_with_an_unknown_kind_is_refused(tmp_path):
    for body in ('{kind: storm, severity: severe, start: "2026-11-02", end: "2026-11-03"}',
                 '{kind: ufo, severity: severe, start: "2026-11-02", end: "2026-11-03", source: x}',
                 '{kind: storm, severity: mild, start: "2026-11-02", end: "2026-11-03", source: x}'):
        with pytest.raises(ValueError):
            adv_mod.advisories([date(2026, 11, 2)], write(tmp_path, f"advisories:\n  - {body}\n"))


def test_the_shipped_advisory_file_is_empty_which_is_not_the_same_as_safe():
    assert adv_mod.advisories([date(2026, 11, 2)]) == {}
