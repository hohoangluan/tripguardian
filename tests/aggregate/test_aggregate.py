import json

from corpus.aggregate import aggregate_place, run
from corpus.ontology import load

ONT = load()
RECENT, OLD = "2026-09-20", "2026-03-01"


def o(i, feature, value, author, observed_at=RECENT, source_type="gmaps_review", time_of_day="unknown",
      day_type="unknown"):
    return {"id": f"x:{i}", "place_fid": "F", "feature": feature, "value": value,
            "context": {"time_of_day": time_of_day, "day_type": day_type, "weather": "unknown"},
            "source_type": source_type, "source_id": f"s{i}", "author": author, "observed_at": observed_at,
            "span": {"quote": "q", "field": "text", "start_s": None, "end_s": None}, "extractor": "t",
            "ontology_version": ONT.version}


def f(obs, as_of="2026-09-30", ratings=(), proposed=()):
    return {"place_fid": "F", "place_name": "P", "as_of": as_of, "ontology_version": ONT.version,
            "observations": list(obs), "proposed": list(proposed), "ratings": list(ratings)}


def test_denominator_is_feature_observations_one_vote_per_author():
    res = aggregate_place([f([o(1, "crowd", "high", "a"), o(2, "crowd", "high", "b"), o(3, "crowd", "low", "c"),
                              o(4, "crowd", "high", "a")])], ONT)
    c = res["features"]["crowd"]
    assert c["n"] == 3 and c["distribution"] == {"high": 2, "low": 1}
    assert c["top_value"] == "high" and c["status"] == "signal" and c["confidence"]["agreement"] == 0.667
    assert c["observation_ids"] == ["x:1", "x:2", "x:3", "x:4"]
    assert "scenic_view" not in res["features"]  # not mentioned -> absent, never a negative value


def test_same_author_two_contexts_splits_global_vote_keeps_both_contexts():
    c = aggregate_place([f([o(1, "crowd", "low", "a", time_of_day="morning"),
                            o(2, "crowd", "high", "a", time_of_day="afternoon"),
                            o(3, "crowd", "high", "b")])], ONT)["features"]["crowd"]
    assert c["n"] == 2 and c["distribution"] == {"low": 0.5, "high": 1.5}
    assert c["by_context"] == {"time_of_day=afternoon": {"high": 1}, "time_of_day=morning": {"low": 1}}


def test_text_and_details_saying_the_same_count_once():
    c = aggregate_place([f([o(1, "noise", "quiet", "a"), o(2, "noise", "quiet", "a", source_type="gmaps_details")])],
                        ONT)["features"]["noise"]
    assert c["n"] == 1 and c["distribution"] == {"quiet": 1}
    assert c["by_source"] == {"gmaps_review": 1, "gmaps_details": 1}


def test_low_agreement_is_uncertain_and_keeps_conflict():
    c = aggregate_place([f([o(1, "crowd", "high", "a"), o(2, "crowd", "low", "b")])], ONT)["features"]["crowd"]
    assert c["status"] == "uncertain" and c["distribution"] == {"high": 1, "low": 1}


def test_trend_rising_and_insufficient():
    older = [o(i, "crowd", "high" if i < 2 else "low", f"o{i}", OLD) for i in range(5)]
    recent = [o(10 + i, "crowd", "high", f"r{i}", RECENT) for i in range(6)]
    t = aggregate_place([f(older + recent)], ONT)["features"]["crowd"]["trend"]
    assert t["direction"] == "rising" and t["recent"] == {"high": 6} and t["older"] == {"high": 2, "low": 3}
    t = aggregate_place([f(older + recent[:4])], ONT)["features"]["crowd"]["trend"]
    assert t["direction"] == "insufficient"


def test_suitability_needs_review():
    feats = aggregate_place([f([o(1, "kids", "suitable", "a"), o(2, "kids", "suitable", "b"), o(3, "kids", "suitable", "c"),
                                o(4, "elderly", "unsuitable", "a"), o(5, "elderly", "unsuitable", "b"),
                                o(6, "groups", "unsuitable", "a")])], ONT)["features"]
    assert feats["kids"]["needs_review"] is True
    assert feats["elderly"]["needs_review"] is False
    assert feats["groups"]["needs_review"] is True
    assert feats.get("crowd") is None


def test_coverage_by_group():
    obs = [o(10 * k + i, feat, val, f"a{i}") for k, (feat, val) in enumerate([("crowd", "high"), ("noise", "quiet"),
                                                                             ("parking", "easy")]) for i in range(3)]
    obs.append(o(99, "scenic_view", "present", "a"))
    cov = aggregate_place([f(obs)], ONT)["coverage"]
    assert cov["environment"] == "COMPLETE" and cov["experience"] == "PARTIAL" and cov["effort"] == "NONE"


def test_rating_trend_and_freshness():
    ratings = [{"author": f"r{i}", "observed_at": RECENT, "stars": 5} for i in range(5)] + \
              [{"author": f"o{i}", "observed_at": OLD, "stars": 3} for i in range(5)]
    res = aggregate_place([f([o(1, "crowd", "high", "a", "2026-09-16")], ratings=ratings)], ONT)
    assert res["rating_trend"] == {"recent_mean": 5.0, "recent_n": 5, "older_mean": 3.0, "older_n": 5,
                                   "direction": "rising"}
    assert res["features"]["crowd"]["confidence"]["freshness_days"] == 14


def test_two_sources_merge_without_source_specific_code():
    gm = f([o(1, "crowd", "high", "a")])
    tt = f([o(2, "crowd", "high", "t1", source_type="tiktok_comment")], as_of="2026-10-01")
    res = aggregate_place([gm, tt], ONT)
    c = res["features"]["crowd"]
    assert c["n"] == 2 and c["confidence"]["source_types"] == ["comment", "provider"]
    assert res["as_of"] == "2026-10-01"


def test_proposed_features_counted_by_label():
    res = aggregate_place([f([], proposed=[{"label": "WiFi", "author": "a", "quote": "q"},
                                           {"label": "wifi ", "author": "b", "quote": "q"},
                                           {"label": "wifi", "author": "b", "quote": "q"}])], ONT)
    assert res["proposed_features"] == [{"label": "wifi", "count": 3, "authors": 2}]


def test_deterministic():
    files = [f([o(1, "crowd", "high", "a"), o(2, "noise", "quiet", "b")])]
    assert aggregate_place(files, ONT) == aggregate_place(files, ONT)


def test_run_reads_every_source_and_skips_old_ontology(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for source, data in (("gmaps", f([o(1, "crowd", "high", "a")])),
                         ("tiktok", f([o(2, "crowd", "high", "t", source_type="tiktok_comment")]))):
        (tmp_path / source / "observations").mkdir(parents=True)
        (tmp_path / source / "observations" / "F.json").write_text(json.dumps(data), encoding="utf-8")
    stale = {**f([o(3, "crowd", "low", "z")]), "place_fid": "G", "ontology_version": 0}
    (tmp_path / "gmaps" / "observations" / "G.json").write_text(json.dumps(stale), encoding="utf-8")
    summary = run("dalat")
    intel = json.loads((tmp_path / "intel" / "places" / "F.json").read_text(encoding="utf-8"))
    assert intel["features"]["crowd"]["n"] == 2
    assert intel["inputs"] == ["gmaps/observations/F.json", "tiktok/observations/F.json"]
    assert not (tmp_path / "intel" / "places" / "G.json").exists()
    assert summary["places"] == 1 and summary["stale_files"] == 1
