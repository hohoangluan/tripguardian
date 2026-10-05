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


def test_trend_splits_own_reviews_in_halves_by_date():
    # a busy place: every review is from the last two months, newest-first cap of the crawl
    days = ["2026-08-01", "2026-08-05", "2026-08-09", "2026-08-13", "2026-08-17",
            "2026-09-01", "2026-09-05", "2026-09-09", "2026-09-13", "2026-09-17"]
    obs = [o(i, "crowd", "low" if i < 4 else "high", f"a{i}", d) for i, d in enumerate(days)]
    t = aggregate_place([f(obs)], ONT)["features"]["crowd"]["trend"]
    assert t["split_at"] == "2026-09-01"
    assert t["older"] == {"low": 4, "high": 1} and t["recent"] == {"high": 5}
    assert t["direction"] == "rising"


def test_trend_halves_never_share_a_date():
    obs = [o(i, "crowd", "high", f"a{i}", "2026-09-16") for i in range(10)]
    t = aggregate_place([f(obs)], ONT)["features"]["crowd"]["trend"]
    assert t["older"] == {} and t["direction"] == "insufficient"


def test_rating_trend_on_recent_only_reviews():
    ratings = [{"author": f"a{i}", "observed_at": f"2026-08-{i + 1:02d}", "stars": 3} for i in range(5)] + \
              [{"author": f"b{i}", "observed_at": f"2026-09-{i + 1:02d}", "stars": 5} for i in range(5)]
    rt = aggregate_place([f([], ratings=ratings)], ONT)["rating_trend"]
    assert rt["split_at"] == "2026-09-01" and rt["direction"] == "rising"


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
    assert res["rating_trend"] == {"split_at": RECENT, "recent_mean": 5.0, "recent_n": 5, "older_mean": 3.0, "older_n": 5,
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


def test_run_reads_every_source_and_keeps_older_ontology_files(tmp_path, monkeypatch):
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
    older = json.loads((tmp_path / "intel" / "places" / "G.json").read_text(encoding="utf-8"))
    assert older["observation_versions"] == [0] and intel["observation_versions"] == [ONT.version]
    assert summary["places"] == 2 and summary["stale_files"] == 1


def test_run_removes_intel_not_built_this_time(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "gmaps" / "observations").mkdir(parents=True)
    (tmp_path / "gmaps" / "observations" / "F.json").write_text(json.dumps(f([o(1, "crowd", "high", "a")])), encoding="utf-8")
    old = tmp_path / "intel" / "places"
    old.mkdir(parents=True)
    (old / "OLD.json").write_text("{}", encoding="utf-8")  # older ontology / place without observations now
    summary = run("dalat")
    assert sorted(p.name for p in old.glob("*.json")) == ["F.json"] and summary["removed"] == 1


def test_unsuitable_needs_two_authors_voting_it():
    feats = aggregate_place([f([o(1, "kids", "unsuitable", "a"),
                                o(2, "kids", "unsuitable", "b", time_of_day="morning"),
                                o(3, "kids", "suitable", "b", time_of_day="evening")])], ONT)["features"]
    assert feats["kids"]["top_value"] == "unsuitable" and feats["kids"]["needs_review"] is False  # a and b both said it
    feats = aggregate_place([f([o(1, "kids", "unsuitable", "a"), o(2, "kids", "unsuitable", "a", time_of_day="morning"),
                                o(3, "kids", "suitable", "b", time_of_day="evening")])], ONT)["features"]
    assert feats["kids"]["needs_review"] is True  # only a said unsuitable


def attr(i, feature, value):
    return {**o(i, feature, value, "gmaps:attributes", "2026-09-30", source_type="gmaps_attribute")}


def test_attribute_alone_is_trusted():
    k = aggregate_place([f([attr(1, "kids", "suitable")])], ONT)["features"]["kids"]
    assert k["status"] == "signal" and k["needs_review"] is False and k["authority"] == "suitable"


def test_attribute_agreeing_with_reviews_is_trusted():
    w = aggregate_place([f([attr(1, "wheelchair", "unsuitable"), o(2, "wheelchair", "unsuitable", "a")])],
                        ONT)["features"]["wheelchair"]
    assert w["status"] == "signal" and w["needs_review"] is False and w["n"] == 2


def test_attribute_contradicted_by_a_review_is_uncertain():
    k = aggregate_place([f([attr(1, "kids", "suitable"), o(2, "kids", "unsuitable", "a")])], ONT)["features"]["kids"]
    assert k["status"] == "uncertain" and k["needs_review"] is False  # served uncertain, both sides kept
    assert k["distribution"] == {"suitable": 1, "unsuitable": 1}


def test_crowd_by_time_and_price_from_place_facts():
    pt = {"sun": {"9": 80, "18": 20}, "sat": {"9": 60}, "mon": {"9": 20, "10": 30}}
    price = {"min_vnd": 1, "max_vnd": 100000, "per": "person", "reports": 9}
    op = aggregate_place([{**f([]), "place_facts": {"popular_times": pt, "price": price}}], ONT)["operation"]
    assert op["price_range"] == price
    assert op["crowd_by_time"]["weekend"] == {"morning": 70, "evening": 20}
    assert op["crowd_by_time"]["weekday"] == {"morning": 25}
    assert op["crowd_by_time"]["peak"] == {"day": "sun", "hour": 9, "pct": 80}
    assert op["popular_times"] == pt


def test_no_place_facts_gives_empty_operation():
    assert aggregate_place([f([])], ONT)["operation"] == {"price_range": None, "hours": None, "hours_source": None,
                                                          "hours_conflict": None, "closure": None,
                                                          "crowd_by_time": None, "popular_times": None}


def test_mention_rate_uses_voices_of_all_files_and_skips_authority():
    a = {**f([o(1, "scenic_view", "present", "a"), o(2, "outdoor_seating", "present", "gmaps:attributes",
                                                   source_type="gmaps_attribute")]), "voices": 30}
    b = {**f([o(3, "scenic_view", "present", "b")]), "voices": 10}
    res = aggregate_place([a, b], ONT)
    assert res["voices"] == 40
    assert res["features"]["scenic_view"]["mention_rate"] == 0.05
    assert res["features"]["outdoor_seating"]["mention_rate"] == 0.0


def test_no_voices_gives_no_mention_rate():
    assert aggregate_place([f([o(1, "crowd", "high", "a")])], ONT)["features"]["crowd"]["mention_rate"] is None


def test_identity_and_hours_pass_through_first_non_null():
    a = {**f([]), "place": {"category": None, "lat": 11.9, "lng": 108.4, "address": "A"},
         "place_facts": {"hours": {"mon": [["07:00", "21:00"]]}, "closure": "temporary"}}
    b = {**f([]), "place": {"category": "Quán cà phê", "lat": 1.0}}
    res = aggregate_place([a, b], ONT)
    assert res["identity"] == {"lat": 11.9, "lng": 108.4, "address": "A", "category": "Quán cà phê"}
    assert res["operation"]["hours"] == {"mon": [["07:00", "21:00"]]} and res["operation"]["closure"] == "temporary"


def test_conflict_is_uncertain_for_any_feature_and_has_no_authority():
    s = aggregate_place([f([attr(1, "outdoor_seating", "present"), attr(2, "laptop_friendly", "present"),
                            o(3, "kids", "unsuitable", "a"), attr(4, "kids", "suitable")])], ONT)["features"]
    k = s["kids"]
    assert k["status"] == "uncertain" and k["needs_review"] is False and k["authority"] is None
    assert s["outdoor_seating"]["confidence"]["source_types"] == ["provider"]


def test_conflict_on_sampled_feature_is_uncertain():
    ont = load()
    # parking is sampled; an attribute-like authority on it contradicted by a review is served uncertain, unauthorised
    obs = [{**attr(1, "parking", "easy")}, o(2, "parking", "hard", "a")]
    p = aggregate_place([f(obs)], ont)["features"]["parking"]
    assert p["status"] == "uncertain" and p["needs_review"] is False and p["authority"] is None


def test_attribute_does_not_set_freshness_or_trend():
    older = [o(i, "kids", "suitable", f"o{i}", OLD) for i in range(5)]
    recent = [o(10 + i, "kids", "suitable", f"r{i}", "2026-06-01") for i in range(5)]
    k = aggregate_place([f(older + recent + [attr(99, "kids", "suitable")])], ONT)["features"]["kids"]
    assert k["confidence"]["freshness_days"] == 121  # newest review, not the crawl date of the attribute
    assert k["trend"]["recent"] == {"suitable": 5} and k["trend"]["older"] == {"suitable": 5}


def test_quality_gate_and_person_decisions_decide_servable():
    obs = [o(1, "crowd", "high", "a"), o(2, "kids", "suitable", "b"), o(3, "noise", "quiet", "c"),
           o(4, "parking", "easy", "d"), o(5, "spacious", "present", "e", source_type="gmaps_attribute")]
    passed = {"precision": 0.95, "lower": 0.85, "correct": 40, "wrong": 2, "gate": True}
    res = aggregate_place([f(obs)], ONT, quality={("crowd", "high"): passed},
                          reviewed={"kids": "accept", "noise": "disable", "parking": "report"})["features"]
    assert res["crowd"]["servable"] and res["crowd"]["quality"] == passed
    assert res["kids"]["servable"] and not res["kids"]["needs_review"] and res["kids"]["review_decision"] == "accept"
    assert res["noise"]["status"] == "disabled" and not res["noise"]["servable"]
    assert res["parking"]["needs_review"] and not res["parking"]["servable"]  # unmeasured, reported
    assert res["spacious"]["servable"] and res["spacious"]["quality"] is None  # authoritative source


def test_run_reads_feature_review_decisions(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from corpus.review import decide
    p = tmp_path / "gmaps" / "observations" / "F.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({**f([o(1, "kids", "suitable", "a")]), "voices": 1}), encoding="utf-8")
    decide("feature_review", "F#kids", "disable")
    run("dalat")
    intel = json.loads((tmp_path / "intel" / "places" / "F.json").read_text(encoding="utf-8"))
    assert intel["features"]["kids"]["status"] == "disabled"
    decide("feature_review", "F#kids", "undo")
    run("dalat")
    intel = json.loads((tmp_path / "intel" / "places" / "F.json").read_text(encoding="utf-8"))
    assert intel["features"]["kids"]["status"] == "signal" and intel["features"]["kids"]["review_decision"] is None


def _key(ob):
    from corpus.review import label_key
    return label_key(ob["source_id"], ob["feature"], ob["value"], ob["span"]["quote"])


def test_wrong_label_drops_evidence_and_all_checked_makes_servable():
    good, bad = o(1, "steep_or_stairs", "present", "a"), o(2, "steep_or_stairs", "present", "b")
    s = aggregate_place([f([good, bad])], ONT, verdicts={_key(good): "correct", _key(bad): "wrong"})["features"]
    st = s["steep_or_stairs"]
    assert st["n"] == 1 and st["checked"] == {"authors": 1, "of": 1, "all": True} and st["servable"] is True


def test_unchecked_value_that_widens_choice_waits_and_checked_one_is_served():
    k = o(1, "kids", "suitable", "a")
    assert aggregate_place([f([k])], ONT)["features"]["kids"]["needs_review"] is True
    s = aggregate_place([f([k])], ONT, verdicts={_key(k): "correct"})["features"]["kids"]
    assert s["needs_review"] is False and s["servable"] is True


def test_owner_counts_only_for_what_it_can_show():
    own = [o(1, "food_quality", "good", "tiktok:owner:x"), o(2, "scenic_view", "present", "tiktok:owner:x"),
           o(3, "steep_or_stairs", "absent", "tiktok:owner:x"), o(4, "steep_or_stairs", "present", "gmaps:owner:x")]
    s = aggregate_place([f(own)], ONT)["features"]
    assert "food_quality" not in s and "scenic_view" in s
    assert s["steep_or_stairs"]["distribution"] == {"present": 1}


def test_photos_without_poster_share_one_voice():
    ph = [{**o(i, "scenic_view", "present", None), "source_type": "gmaps_photo"} for i in range(3)]
    assert aggregate_place([f(ph)], ONT)["features"]["scenic_view"]["n"] == 1


def test_targeted_sample_counts_for_effort_and_facts_not_opinions():
    low = {**o(2, "service_quality", "poor", "b"), "sample": "extremes"}
    stairs = {**o(3, "steep_or_stairs", "present", "b"), "sample": "extremes"}
    kw = {**o(4, "long_walk", "present", "c"), "sample": "keywords"}
    doc = {**f([o(1, "service_quality", "good", "a"), low, stairs, kw],
               ratings=[{"author": "a", "observed_at": RECENT, "stars": 5},
                        {"author": "b", "observed_at": RECENT, "stars": 1, "sample": "extremes"}]),
           "voices": 4, "voices_targeted": 2}
    res = aggregate_place([doc], ONT)
    sq = res["features"]["service_quality"]
    assert sq["distribution"] == {"good": 1} and sq["mention_rate"] == 0.25  # opinion: newest / relevant voices only
    assert res["features"]["steep_or_stairs"]["mention_rate"] == round(1 / 6, 3)  # effort: all voices
    assert res["features"]["long_walk"]["n"] == 1
    assert res["rating_trend"]["recent_n"] + res["rating_trend"]["older_n"] == 1


def test_official_site_wins_for_hours_and_entry_fee_and_keeps_the_conflict():
    maps = {**f([o(1, "entry_fee", "paid", "a")]), "place_facts": {
        "hours": {"mon": [["07:00", "17:00"]], "tue": [["07:00", "17:00"]]}, "tickets": {"usd": 2.0}}}
    site = {**f([o(2, "entry_fee", "paid", "official:F", source_type="official_page")]), "source": "official",
            "place_facts": {"hours": {"mon": [["08:00", "18:00"]]}, "tickets_vnd": {"adult": [100000, 150000],
                                                                                    "child": [50000]}}}
    res = aggregate_place([maps, site], ONT)
    op = res["operation"]
    assert op["hours"] == {"mon": [["08:00", "18:00"]], "tue": [["07:00", "17:00"]]}
    assert op["hours_source"] == "official" and op["hours_conflict"] == {"mon": [["07:00", "17:00"]]}
    assert res["estimates"]["entry_fee"] == {"min_vnd": 50000, "typical_vnd": 150000, "max_vnd": 150000, "n": 2,
                                             "source": "official"}
    assert res["features"]["entry_fee"]["authority"] == "paid"  # the site declares it, no review says otherwise
