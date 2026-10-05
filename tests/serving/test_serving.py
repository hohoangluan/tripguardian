import json
from datetime import date

from corpus.serving import areas, build, check, mmr, near_duplicate_groups, run

BUILT = date(2026, 10, 2)


def sig(top, dist=None, n=3, status="signal", servable=True, needs_review=False, fresh=10, rate=0.1, authority=None):
    return {"n": n, "distribution": dist or {top: n}, "top_value": top, "status": status, "authority": authority,
            "by_context": {}, "mention_rate": rate, "needs_review": needs_review, "servable": servable,
            "quality": None, "observation_ids": [f"x:{i}" for i in range(9)],
            "confidence": {"independent_sources": n, "agreement": 1.0, "freshness_days": fresh, "source_types": ["provider"]}}


def intel(fid="F", features=None, closure=None, category="Quán cà phê", group="cafe", lat=11.94, lng=108.44,
          usable=("experience", "meal", "backup"), coverage=None):
    return {"place_fid": fid, "place_name": fid, "as_of": "2026-09-30", "voices": 30,
            "identity": {"category": category, "lat": lat, "lng": lng, "address": "Đà Lạt"},
            "features": features or {}, "coverage": coverage or {"experience": "PARTIAL"},
            "operation": {"closure": closure, "hours": {"mon": [["07:00", "22:00"]]}, "price_range": None,
                          "crowd_by_time": None},
            "estimates": {"category_group": group, "usable_as_default": list(usable), "effort_hint": "unknown",
                          "visit_minutes": {"short": 45, "typical": 75, "long": 150, "source": "category_default", "n": 0},
                          "entry_fee": None}}


def test_statuses_never_serve_needs_review_or_disabled_and_unmeasured_is_uncertain():
    rec = build(intel(features={"scenic_view": sig("present"), "kids": sig("suitable", needs_review=True),
                                "noise": sig("quiet", status="disabled", servable=False),
                                "crowd": sig("high", servable=False), "parking": sig("easy", fresh=900)}), BUILT)
    assert rec["experience"]["scenic_view"]["status"] == "VERIFIED"
    assert "kids" not in rec["suitability"] and "noise" not in rec["environment"]
    assert (rec["environment"]["crowd"]["status"], rec["environment"]["crowd"]["reason"]) == ("UNCERTAIN", "unmeasured_precision")
    assert rec["environment"]["parking"]["status"] == "OUTDATED"
    assert rec["operation"]["visit_minutes"]["kind"] == "estimate" and rec["status"] == "VERIFIED"
    assert build(intel(closure="permanent"), BUILT)["status"] == "DISABLED"


def test_check_is_fail_closed():
    rec = build(intel(features={
        "steep_or_stairs": sig("absent"),
        "long_walk": sig("absent", dist={"absent": 3, "present": 1}),  # somebody said it: not safe
        "rough_road_access": sig("present"),
        "elderly": sig("suitable", servable=False)}), BUILT)
    assert check(rec, "steep_or_stairs", "present") == "pass"
    assert check(rec, "long_walk", "present") == "unknown"
    assert check(rec, "rough_road_access", "present") == "fail"
    assert check(rec, "elderly", "unsuitable") == "unknown"  # unmeasured value never passes a hard filter
    assert check(rec, "wheelchair", "unsuitable") == "unknown"  # no evidence is never safe


def test_experience_none_cannot_be_used_as_experience():
    rec = build(intel(coverage={"experience": "NONE"}), BUILT)
    assert rec["usable_as"] == ["meal", "backup"]


def _rec(fid, kinds, lat=11.94, lng=108.44, group="cafe"):
    return build(intel(fid, {k: sig("present") for k in kinds}, group=group, lat=lat, lng=lng), BUILT)


def test_near_duplicates_by_leader_not_chained_and_only_within_group():
    a = _rec("A", ["scenic_view", "photo_spot", "cozy_decor", "nature"])
    b = _rec("B", ["scenic_view", "photo_spot", "cozy_decor", "nature", "animals"])
    c = _rec("C", ["photo_spot", "cozy_decor", "nature", "animals", "live_music", "camping"])
    d = _rec("D", ["scenic_view", "photo_spot", "cozy_decor", "nature"], group="restaurant")
    # C leads (most features) but B shares only 4/7 with it; B leads A; D is a restaurant
    assert near_duplicate_groups([a, b, c, d]) == [["B", "A"]]


def test_mmr_prefers_a_different_place_over_a_near_duplicate():
    a = _rec("A", ["scenic_view", "photo_spot", "cozy_decor", "nature"])
    b = _rec("B", ["scenic_view", "photo_spot", "cozy_decor", "nature"])
    c = _rec("C", ["live_music", "laptop_friendly", "long_stay_chill"])
    assert mmr([a, b, c], {"A": 1.0, "B": 0.95, "C": 0.7}, 2) == ["A", "C"]


def test_areas_group_close_places():
    near = [_rec(f"N{i}", [], lat=11.94 + i * 0.001) for i in range(3)]
    far = _rec("F", [], lat=12.10)
    got = areas(near + [far])
    assert len({got[r["id"]] for r in near}) == 1 and got["F"] != got["N0"] and got["N0"] == "area-1"


def test_run_writes_served_records_only(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    d = tmp_path / "intel" / "places"
    d.mkdir(parents=True)
    (d / "A.json").write_text(json.dumps(intel("A")), encoding="utf-8")
    (d / "B.json").write_text(json.dumps(intel("B", closure="temporary")), encoding="utf-8")
    summary = run("dalat")
    assert summary["places"] == 1 and summary["disabled"] == {"closure_temporary": 1}
    doc = json.loads((tmp_path / "serving" / "places.json").read_text(encoding="utf-8"))
    assert [r["id"] for r in doc["records"]] == ["A"] and doc["records"][0]["identity"]["area"] == "area-1"


def test_place_status_from_maps_closure_then_judge():
    from corpus.serving.record import place_status
    assert place_status("permanent", "open") == ("DISABLED", "closure_permanent")
    assert place_status(None, "closed") == ("DISABLED", "judge_closed")
    assert place_status(None, "changed") == ("DISABLED", "judge_changed")
    assert place_status(None, "unclear") == ("UNCERTAIN", "closure_reported")
    assert place_status(None, None) == ("VERIFIED", None)
