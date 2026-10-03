from planning import settings


def test_the_shipped_config_loads_with_minutes_not_clock_strings():
    cfg = settings.load(settings.PATH)
    assert cfg.version == 1
    assert (cfg.day_start, cfg.day_end, cfg.leave_at) == (480, 1260, 900)
    assert cfg.meal_windows["lunch"] == (690, 810)
    assert cfg.pins["live_music"]["from"] == 1080 and cfg.pins["sunset_view"]["anchor"] == "sunset"
    assert cfg.visit_key == {"slow": "long", "normal": "typical", "packed": "short"}
    assert cfg.exact_n == 7 and cfg.max_days == 7 and cfg.max_clusters == 8


def test_fmt_and_to_min_round_trip():
    assert settings.to_min("08:30") == 510
    assert settings.fmt(510) == "08:30"


def test_the_p4_keys_load():
    cfg = settings.load(settings.PATH)
    assert (cfg.rain_high, cfg.buffer_extra_rain, cfg.max_variants) == (0.6, 10, 3)
    assert [s["id"] for s in cfg.robustness["scenarios"]] == ["late_15", "visit_20", "travel_25", "late_30", "rain"]
    assert set(cfg.objective_weights) == set(cfg.objective_order)


def test_the_p6_keys_load():
    cfg = settings.load(settings.PATH)
    assert cfg.history_max == 20
    assert cfg.repair_diff_weight == 5.0
    assert cfg.decision_url == "http://127.0.0.1:8767"


def test_turn_settings_are_loaded():
    from planning.settings import load
    cfg = load()
    assert cfg.first_token_s > 0 and cfg.total_s > cfg.first_token_s and cfg.rethink_drops > 0
