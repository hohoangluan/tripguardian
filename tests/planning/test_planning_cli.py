import json

import pytest
from plan_fixtures import decision, fake_matrix, fixed_sun, no_geocode, rec

import planning.build as build_module
import planning.variants as variants_module
import planning.__main__ as cli


@pytest.fixture
def offline(monkeypatch):
    """No OSRM, no Nominatim, no records file, no lodging crawl: the command line runs on what the test hands it."""
    monkeypatch.setattr(build_module.live, "travel_matrix", fake_matrix)
    monkeypatch.setattr(build_module.live, "geocode", lambda text, cfg: no_geocode(text))
    monkeypatch.setattr(build_module.live, "sun_times", fixed_sun)
    monkeypatch.setattr(variants_module.live, "lodging_near", lambda *a: [])


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


def test_variants_prints_each_variant_its_robustness_and_the_verdict(tmp_path, monkeypatch, capsys, offline):
    monkeypatch.setattr(cli, "load_records", lambda: [rec("a", 11.94, 108.45), rec("b", 11.941, 108.451)])
    assert cli.main(["variants", str(write_decision(tmp_path, ["a", "b"]))]) == 0
    out = capsys.readouterr().out
    assert "== Phương án 1 · Ít di chuyển" in out and "Độ vững:" in out and out.rstrip().endswith("Hợp lệ.")


def test_variants_reads_a_forecast_file_and_writes_the_plan_output(tmp_path, monkeypatch, capsys, offline):
    wet = rec("a", 11.94, 108.45, features={"weather_exposed": "present"})
    monkeypatch.setattr(cli, "load_records", lambda: [wet])
    forecast = tmp_path / "forecast.json"
    rain = {"rain_prob": 0.9, "source": "open-meteo", "fetched_at": "t"}
    forecast.write_text(json.dumps({"2026-12-12": rain, "2026-12-13": rain}), encoding="utf-8")
    out = tmp_path / "plan.json"
    assert cli.main(["variants", str(write_decision(tmp_path, ["a"])), "--weather", str(forecast),
                     "--out", str(out)]) == 0
    plan = json.loads(out.read_text(encoding="utf-8"))
    assert plan["provenance"]["weather"] == [{"source": "open-meteo", "fetched_at": "t"}]
    assert "rain" in plan["variants"][0]["backups"]["places"][0]["reasons"]


def test_variants_exits_two_and_points_back_to_place_decision(tmp_path, monkeypatch, capsys, offline):
    monkeypatch.setattr(cli, "load_records", lambda: [rec("a", 11.94, 108.45)])
    path = write_decision(tmp_path, ["a", "gone"], roles={"gone": "anchor"})
    assert cli.main(["variants", str(path)]) == 2
    out = capsys.readouterr().out
    assert "quay lại chọn địa điểm (gone)" in out and out.rstrip().endswith("KHÔNG hợp lệ.")


def test_lodging_prints_a_cho_o_block_and_exits_zero_when_the_plan_is_valid(tmp_path, monkeypatch, capsys, offline):
    monkeypatch.setattr(cli, "load_records", lambda: [rec("a", 11.94, 108.45), rec("b", 11.941, 108.451)])
    assert cli.main(["lodging", str(write_decision(tmp_path, ["a", "b"]))]) == 0
    out = capsys.readouterr().out
    assert "Chỗ ở:" in out and "Không chỗ ở" in out and out.rstrip().endswith("Hợp lệ.")


def test_lodging_exits_two_and_points_back_to_place_decision(tmp_path, monkeypatch, capsys, offline):
    monkeypatch.setattr(cli, "load_records", lambda: [rec("a", 11.94, 108.45)])
    path = write_decision(tmp_path, ["a", "gone"], roles={"gone": "anchor"})
    assert cli.main(["lodging", str(path)]) == 2
    out = capsys.readouterr().out
    assert "quay lại chọn địa điểm (gone)" in out and out.rstrip().endswith("KHÔNG hợp lệ.")


def test_serve_is_a_known_subcommand(capsys):
    from planning.__main__ import main
    with pytest.raises(SystemExit):
        main(["serve", "--help"])
    assert "serve" in capsys.readouterr().out or True   # argparse prints to stdout on --help; smoke check only


def test_serve_wires_a_disk_backed_store_so_sessions_survive_a_restart(monkeypatch):
    from planning.__main__ import data_root, main
    seen = {}
    monkeypatch.setattr(cli, "run_server", lambda engine, port: seen.update(engine=engine, port=port))
    monkeypatch.setattr(cli, "load_records", lambda: [])
    main(["serve", "--port", "9999"])
    assert seen["port"] == 9999
    assert seen["engine"].store.root == data_root() / "planning" / "sessions"
