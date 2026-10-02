import json

import pytest

from trip.catalog import Catalog
from trip.coverage import admissible, coverage, verdict
from trip.state import Evidence, Hard

from trip_fixtures import rec

EV = (Evidence(turn=1, quote="x"),)


def hard(**kw):
    return Hard(feature="steep_or_stairs", op="ne", value="present", evidence=EV, **kw)


def test_only_served_values_count():
    c = Catalog.from_records([
        rec(1, "A", {"noise": ("quiet", 1)}),
        rec(2, "B", {"noise": ("quiet", 5)}, status="uncertain"),
        rec(3, "C", {"kids": ("suitable", 5)}, needs_review=True),
    ], n_min=2)
    assert c.by_id["0x1:0x1"].value("noise") is None
    assert c.by_id["0x2:0x1"].value("noise") is None
    assert c.by_id["0x3:0x1"].value("kids") is None


def test_context_value_wins_when_present():
    c = Catalog.from_records([rec(1, "A", {"crowd": ("high", 5, {"time_of_day=morning": {"low": 3, "high": 1}})})], 1)
    p = c.by_id["0x1:0x1"]
    assert p.value("crowd") == "high"
    assert p.value("crowd", (("time_of_day", "morning"),)) == "low"
    assert p.value("crowd", (("time_of_day", "night"),)) == "high"


def test_count_and_hours(catalog):
    assert catalog.count("noise=quiet") == 6
    assert catalog.count("crowd=low@time_of_day.morning") == 6
    assert catalog.by_id["0x11:0x1"].hours["mon"] == ()


def test_load_reads_intel_and_tiktok(tmp_path, records):
    (tmp_path / "intel" / "places").mkdir(parents=True)
    for r in records[:2]:
        (tmp_path / "intel" / "places" / f"{r['place_fid'].replace(':', '_')}.json").write_text(json.dumps(r), "utf-8")
    (tmp_path / "tiktok" / "place_filter").mkdir(parents=True)
    (tmp_path / "tiktok" / "place_filter" / "x.json").write_text(json.dumps({"fid": "0x1:0x1", "videos": [
        {"video_id": "111", "llm": {"relevance": "yes"}}, {"video_id": "222", "llm": {"relevance": "no"}}]}), "utf-8")
    c = Catalog.load(tmp_path, n_min=1)
    assert len(c.places) == 2 and c.video_place == {"111": "0x1:0x1"}


def test_load_without_intel_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        Catalog.load(tmp_path, n_min=1)


def test_coverage_counts_pass_fail_unknown(catalog):
    c = coverage(hard(), catalog.places, enough=4)
    assert (c.passed, c.failed, c.level) == (1, 4, "thin")
    assert c.passed + c.failed + c.unknown == len(catalog.places)
    assert coverage(Hard(feature="long_walk", op="ne", value="present", evidence=EV), catalog.places, 4).level == "none"


def test_unknown_is_excluded_unless_flagged(catalog):
    flat, steep, quiet = catalog.by_id["0x11:0x1"], catalog.by_id["0xd:0x1"], catalog.by_id["0x1:0x1"]
    assert verdict(flat, hard()) == "pass" and verdict(steep, hard()) == "fail" and verdict(quiet, hard()) == "unknown"
    assert admissible(flat, [hard()]) and not admissible(steep, [hard(unknown_policy="flag")])
    assert not admissible(quiet, [hard()]) and admissible(quiet, [hard(unknown_policy="flag")])


def test_load_skips_place_filter_files_without_a_video_list(tmp_path, records):
    (tmp_path / "intel" / "places").mkdir(parents=True)
    (tmp_path / "intel" / "places" / "a.json").write_text(json.dumps(records[0]), "utf-8")
    (tmp_path / "tiktok" / "place_filter").mkdir(parents=True)
    (tmp_path / "tiktok" / "place_filter" / "x.json").write_text(json.dumps({"fid": "0x1:0x1", "videos": 3}), "utf-8")
    assert Catalog.load(tmp_path, n_min=1).video_place == {}
