import json

import pytest
from plan_fixtures import decision, fake_matrix, fixed_sun, no_geocode, rec

import planning.build as build_module
import planning.__main__ as cli


@pytest.fixture
def offline(monkeypatch):
    """No OSRM, no Nominatim, no records file: the command line runs on what the test hands it."""
    monkeypatch.setattr(build_module.live, "travel_matrix", fake_matrix)
    monkeypatch.setattr(build_module.live, "geocode", lambda text, cfg: no_geocode(text))
    monkeypatch.setattr(build_module.live, "sun_times", fixed_sun)


def write_decision(tmp_path, ids, **kw):
    p = tmp_path / "decision.json"
    p.write_text(json.dumps(decision(ids, **kw), ensure_ascii=False), encoding="utf-8")
    return p


def test_build_prints_the_itinerary_and_exits_zero_when_the_plan_is_valid(tmp_path, monkeypatch, capsys, offline):
    monkeypatch.setattr(cli, "load_records", lambda: [rec("a", 11.94, 108.45), rec("b", 11.941, 108.451)])
    assert cli.main(["build", str(write_decision(tmp_path, ["a", "b"]))]) == 0
    out = capsys.readouterr().out
    assert "Ngày 1" in out and out.rstrip().endswith("Hợp lệ.")


def test_build_exits_two_and_names_the_violation_when_the_plan_is_not_valid(tmp_path, monkeypatch, capsys, offline):
    monkeypatch.setattr(cli, "load_records", lambda: [rec("a", 11.94, 108.45)])
    path = write_decision(tmp_path, ["a", "gone"], roles={"gone": "anchor"})
    assert cli.main(["build", str(path)]) == 2
    out = capsys.readouterr().out
    assert "X anchor" in out and out.rstrip().endswith("KHÔNG hợp lệ.")


def test_build_can_also_write_the_full_plan_output_as_json(tmp_path, monkeypatch, capsys, offline):
    monkeypatch.setattr(cli, "load_records", lambda: [rec("a", 11.94, 108.45)])
    out = tmp_path / "plan.json"
    assert cli.main(["build", str(write_decision(tmp_path, ["a"])), "--out", str(out)]) == 0
    plan = json.loads(out.read_text(encoding="utf-8"))
    assert plan["ok"] and {"itinerary", "travel_load", "warnings", "uncertainty", "provenance"} <= set(plan)
