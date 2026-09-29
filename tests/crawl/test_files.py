import json

from corpus.crawl import files


def test_write_json_is_atomic_and_overwrites(tmp_path):
    p = tmp_path / "a" / "x.json"
    files.write_json(p, {"v": 1})
    files.write_json(p, {"v": "Đà Lạt"})
    assert json.loads(p.read_text(encoding="utf-8")) == {"v": "Đà Lạt"}
    assert [f.name for f in p.parent.iterdir()] == ["x.json"]  # no .tmp left


def test_append_jsonl_keeps_old_lines(tmp_path):
    p = tmp_path / "s.jsonl"
    files.append_jsonl(p, {"n": 1})
    files.append_jsonl(p, {"n": 2})
    assert [json.loads(l)["n"] for l in p.read_text(encoding="utf-8").splitlines()] == [1, 2]


def test_log_error_appends_reason(tmp_path):
    files.log_error(tmp_path, "v1", "download", ValueError("boom"))
    row = json.loads((tmp_path / "errors.jsonl").read_text(encoding="utf-8"))
    assert (row["id"], row["stage"], row["error"]) == ("v1", "download", "ValueError: boom")


def test_names_are_windows_safe():
    assert files.slug("Quán cà phê Đà Lạt!") == "quan-ca-phe-da-lat"
    assert files.safe_name("0x317114a1a4b93341:0xf8ce8eb72915c065") == "0x317114a1a4b93341_0xf8ce8eb72915c065"


def test_author_hash_is_stable_and_not_the_id():
    h = files.author_hash("12345")
    assert h == files.author_hash("12345") and len(h) == 16 and "12345" not in h


def test_data_dir_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert files.data_dir() == tmp_path


def test_load_config_known_and_unknown_city():
    name, cfg = files.load_config("dalat")
    assert name == "Đà Lạt" and cfg["tiktok"]["queries"] and cfg["gmaps"]["categories"]
    try:
        files.load_config("nowhere")
    except SystemExit as e:
        assert "dalat" in str(e)
    else:
        raise AssertionError("unknown city must exit")
