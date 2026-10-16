import hashlib
import json

from corpus import load_ontology


def put(root, path, data):
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def doc(fid="F", **changes):
    version = load_ontology().version
    observation = {"id": "gmaps:attr:0", "place_fid": fid, "feature": "outdoor_seating", "value": "present",
                   "context": {}, "source_type": "gmaps_attribute", "source_id": fid, "author": "gmaps:attributes",
                   "observed_at": "2026-09-01", "span": {"quote": "Outdoor seating", "field": "attributes"},
                   "extractor": "rules@v1", "ontology_version": version}
    return {"place_fid": fid, "place_name": fid, "as_of": "2026-09-01", "ontology_version": version,
            "observations": [observation], "details": None, "ratings": [], **changes}


def test_normalize_preserves_original_and_is_idempotent(tmp_path):
    from corpus.normalize import normalize
    p = put(tmp_path, "gmaps/observations/F.json", doc())
    before = p.read_bytes()
    result = normalize("dalat", tmp_path, canonical={})
    path, normalized = next(result.documents())
    assert path == "gmaps/observations/F.json"
    assert normalized["observations"][0]["id"] == "gmaps:attr:0"
    assert normalized["observations"][0]["context"] == dict.fromkeys(("time_of_day", "day_type", "weather"), "unknown")
    assert normalized["ontology_version"] == doc()["ontology_version"]
    assert normalized["details"] == []
    assert p.read_bytes() == before
    assert result.manifest["inputs"][0]["sha256"] == hashlib.sha256(before).hexdigest()
    assert normalize("dalat", tmp_path, canonical={}).id == result.id
    put(tmp_path, "gmaps/observations/F.json", doc(place_name="Changed"))
    assert normalize("dalat", tmp_path, canonical={}).id != result.id


def test_membership_merge_and_backup_are_explicit(tmp_path):
    from corpus.normalize import normalize
    put(tmp_path, "gmaps/list/dalat.json", {"items": [{"fid": "F"}]})
    for fid in ("F", "G", "OLD"):
        put(tmp_path, f"gmaps/observations/{fid}.json", doc(fid))
        put(tmp_path, f"gmaps/places/{fid}/place.json", {"fid": fid, "attributes": ["Outdoor seating"]})
    put(tmp_path, "gmaps/observations_under30_backup/B.json", doc("B"))
    result = normalize("dalat", tmp_path, canonical={"G": "F"})
    assert {d["place_fid"] for _, d in result.documents()} == {"F", "G"}
    old = next(i for i in result.manifest["inputs"] if i["path"].endswith("OLD.json"))
    assert old["lifecycle"] == "historical" and old["reason"] == "outside_inventory"
    assert result.manifest["backups"] == ["gmaps/observations_under30_backup"]


def test_invalid_payload_and_claim_are_reported_without_overwriting(tmp_path):
    from corpus.normalize import normalize
    p = put(tmp_path, "gmaps/observations/F.json", doc(observations=[{"id": "bad"}]))
    bad = tmp_path / "gmaps/observations/broken.json"
    bad.write_text("{broken")
    result = normalize("dalat", tmp_path, canonical={})
    assert {i["reason"] for i in result.manifest["issues"]} >= {"invalid_claim", "invalid_json"}
    assert next(result.documents())[1]["observations"] == []
    assert json.loads(p.read_text())["observations"] == [{"id": "bad"}]
    assert bad.read_text() == "{broken"


def test_missing_sources_fail_closed_with_inventory(tmp_path):
    from corpus.normalize import normalize
    put(tmp_path, "gmaps/list/dalat.json", {"items": [{"fid": "F"}]})
    put(tmp_path, "gmaps/observations/F.json", doc())
    result = normalize("dalat", tmp_path, canonical={})
    assert next(result.documents())[1]["observations"] == []
    assert any(i["reason"] == "missing_source" for i in result.manifest["issues"])


def test_scoped_ids_and_legacy_versions_survive(tmp_path):
    from corpus.normalize import normalize
    for fid in ("F", "G"):
        put(tmp_path, f"gmaps/observations/{fid}.json", doc(fid, ontology_version=0))
    result = normalize("dalat", tmp_path, canonical={})
    assert len(list(result.documents())) == 2
    assert all(d["observations"][0]["id"] == "gmaps:attr:0" for _, d in result.documents())
    assert result.manifest["summary"]["legacy_version_files"] == 2
    assert result.manifest["inventory_mode"] == "legacy_unlisted"


def test_duplicate_claim_conflicts_are_quarantined(tmp_path):
    from corpus.normalize import normalize
    d = doc()
    d["observations"].append({**d["observations"][0], "value": "absent"})
    put(tmp_path, "gmaps/observations/F.json", d)
    result = normalize("dalat", tmp_path, canonical={})
    assert next(result.documents())[1]["observations"] == []
    assert any(i["reason"] == "duplicate_claim_conflict" for i in result.manifest["issues"])


def test_aggregate_normalizes_new_inputs_and_supports_staging(tmp_path, monkeypatch):
    from corpus.aggregate import run
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    put(tmp_path, "gmaps/observations/F.json", doc())
    put(tmp_path, "intel/places/KEEP.json", {"original": True})
    out = tmp_path / "stage"
    result = run("dalat", output_root=out)
    assert (tmp_path / "intel/places/KEEP.json").exists()
    assert (out / "intel/places/F.json").exists()
    first = result["normalization_id"]
    put(tmp_path, "gmaps/observations/F.json", doc(place_name="Changed"))
    assert run("dalat", output_root=out)["normalization_id"] != first


def test_null_context_and_invalid_date_keep_claim_with_unknown(tmp_path):
    from corpus.normalize import normalize
    d = doc()
    d["observations"][0].update(context=None, observed_at="unparseable")
    put(tmp_path, "gmaps/observations/F.json", d)
    claim = next(normalize("dalat", tmp_path, canonical={}).documents())[1]["observations"][0]
    assert set(claim["context"].values()) == {"unknown"}
    assert claim["observed_at"] is None


def test_tiktok_frame_resolves_timestamp_to_saved_frame(tmp_path):
    from corpus.normalize import normalize
    put(tmp_path, "gmaps/list/dalat.json", {"items": [{"fid": "F"}]})
    d = doc()
    d["observations"][0].update(source_type="tiktok_frame", source_id="v1",
                               span={"quote": "Outdoor seating", "field": "frame", "start_s": 15.0, "end_s": 15.0})
    put(tmp_path, "tiktok/observations/F.json", d)
    put(tmp_path, "tiktok/videos/v1/video.json", {"video_id": "v1", "transcript": {"total_s": 40}})
    frame = tmp_path / "tiktok/videos/v1/frames/f2.jpg"
    frame.parent.mkdir(parents=True)
    frame.write_bytes(b"saved frame")
    result = normalize("dalat", tmp_path, canonical={})
    assert len(next(result.documents())[1]["observations"]) == 1


def test_discarded_effort_claim_does_not_turn_into_absent(tmp_path):
    from corpus.aggregate import run
    put(tmp_path, "gmaps/list/dalat.json", {"items": [{"fid": "F"}]})
    d = doc(voices=8)
    d["observations"][0].update(feature="steep_or_stairs", source_type="gmaps_review", source_id="R1")
    put(tmp_path, "gmaps/observations/F.json", d)
    run("dalat", root=tmp_path)
    intel = json.loads((tmp_path / "intel/places/F.json").read_text())
    assert "steep_or_stairs" not in intel["features"]


def test_unidentified_invalid_claim_blocks_silence_inference(tmp_path):
    from corpus.aggregate import run
    put(tmp_path, "gmaps/observations/F.json", doc(voices=20, observations=[{"id": "bad"}]))
    run("dalat", root=tmp_path)
    intel = json.loads((tmp_path / "intel/places/F.json").read_text())
    assert not {"steep_or_stairs", "long_walk", "rough_road_access"} & set(intel["features"])


def test_quarantined_containers_do_not_crash_label_stats(tmp_path):
    from corpus.aggregate import run
    put(tmp_path, "gmaps/observations/F.json", doc(observations="bad"))
    assert run("dalat", root=tmp_path)["places"] == 0


def test_attribute_without_source_value_is_excluded(tmp_path):
    from corpus.normalize import normalize
    put(tmp_path, "gmaps/list/dalat.json", {"items": [{"fid": "F"}]})
    put(tmp_path, "gmaps/places/F/place.json", {})
    put(tmp_path, "gmaps/observations/F.json", doc())
    assert next(normalize("dalat", tmp_path, canonical={}).documents())[1]["observations"] == []


def test_month_precision_is_not_promoted_to_a_day(tmp_path):
    from corpus.aggregate import run
    d = doc()
    d["observations"][0].update(feature="entry_fee", value="paid", observed_at="2026-09",
                               span={"quote": "vé vào cổng 50k", "field": "text"})
    put(tmp_path, "gmaps/observations/F.json", d)
    run("dalat", root=tmp_path)
    intel = json.loads((tmp_path / "intel/places/F.json").read_text())
    assert intel["features"]["entry_fee"]["confidence"]["freshness_days"] is None
    assert intel["estimates"]["entry_fee"]["typical_vnd"] == 50_000


def test_malformed_identity_and_fact_shapes_are_quarantined(tmp_path):
    from corpus.normalize import normalize
    put(tmp_path, "gmaps/observations/F.json", doc(place={"category": []}))
    put(tmp_path, "gmaps/observations/G.json", doc("G", place_facts={"time_spent": "bad"}))
    result = normalize("dalat", tmp_path, canonical={})
    assert not list(result.documents())
    assert all(i["reason"] == "invalid_document" for i in result.manifest["inputs"])


def test_invalidated_conflict_does_not_upgrade_remaining_claim(tmp_path):
    from corpus.aggregate import run
    from corpus.serving import build
    from datetime import date
    put(tmp_path, "gmaps/list/dalat.json", {"items": [{"fid": "F"}]})
    put(tmp_path, "gmaps/places/F/place.json", {"attributes": ["Outdoor seating"]})
    put(tmp_path, "gmaps/places/F/reviews.json", {"reviews": [{"review_id": "R1", "text": "unrelated"}]})
    d = doc()
    d["observations"].append({**d["observations"][0], "id": "review:R1", "source_type": "gmaps_review",
                              "source_id": "R1", "author": "reviewer", "value": "absent"})
    put(tmp_path, "gmaps/observations/F.json", d)
    run("dalat", root=tmp_path)
    intel = json.loads((tmp_path / "intel/places/F.json").read_text())
    assert build(intel, date(2026, 10, 14))["environment"]["outdoor_seating"]["status"] == "UNCERTAIN"


def test_malformed_auxiliary_rows_do_not_crash_aggregate(tmp_path):
    from corpus.aggregate import run
    put(tmp_path, "gmaps/observations/F.json", doc(ratings=[None, {"stars": "bad"}], proposed=[{}]))
    result = run("dalat", root=tmp_path)
    assert result["places"] == 1


def test_review_quote_must_match_its_source(tmp_path):
    from corpus.normalize import normalize
    put(tmp_path, "gmaps/list/dalat.json", {"items": [{"fid": "F"}]})
    d = doc()
    d["observations"][0].update(source_type="gmaps_review", source_id="R1")
    put(tmp_path, "gmaps/observations/F.json", d)
    put(tmp_path, "gmaps/places/F/reviews.json", {"reviews": [{"review_id": "R1", "text": "unrelated"}]})
    result = normalize("dalat", tmp_path, canonical={})
    assert next(result.documents())[1]["observations"] == []
    assert any(i["reason"] == "invalid_source_span" for i in result.manifest["issues"])


def test_dropped_agreeing_claim_does_not_taint_the_feature(tmp_path):
    from corpus.aggregate import run
    put(tmp_path, "gmaps/list/dalat.json", {"items": [{"fid": "F"}]})
    put(tmp_path, "gmaps/places/F/place.json", {"attributes": ["Outdoor seating"]})
    put(tmp_path, "gmaps/places/F/reviews.json", {"reviews": [{"review_id": "R1", "text": "unrelated"}]})
    d = doc()
    d["observations"].append({**d["observations"][0], "id": "review:R1", "source_type": "gmaps_review",
                              "source_id": "R1", "author": "reviewer"})
    put(tmp_path, "gmaps/observations/F.json", d)
    run("dalat", root=tmp_path)
    intel = json.loads((tmp_path / "intel/places/F.json").read_text())
    assert "normalization_issue" not in intel["features"]["outdoor_seating"]


def tiktok_doc(start, end):
    d = doc()
    d["observations"][0].update(id="tiktok:v1:0", source_type="tiktok_segment", source_id="v1", author="tiktok:a",
                               span={"quote": "Outdoor seating", "field": "speech", "start_s": start, "end_s": end})
    return d


def tiktok_video(root):
    put(root, "tiktok/videos/v1/video.json", {"video_id": "v1", "transcript": {"total_s": 40, "segments": [
        {"start_s": 0.0, "end_s": 7.04, "checked_text": "có outdoor seating rộng"}]}})


def test_tiktok_quote_in_a_moved_segment_is_reanchored(tmp_path):
    from corpus.normalize import normalize
    put(tmp_path, "gmaps/list/dalat.json", {"items": [{"fid": "F"}]})
    put(tmp_path, "tiktok/observations/F.json", tiktok_doc(0.0, 7.2))
    tiktok_video(tmp_path)
    result = normalize("dalat", tmp_path, canonical={})
    [claim] = next(result.documents())[1]["observations"]
    assert claim["id"] == "tiktok:v1:0" and claim["span"]["quote"] == "Outdoor seating"
    assert (claim["span"]["start_s"], claim["span"]["end_s"]) == (0.0, 7.04)
    assert claim["span"]["reanchored_from"] == {"start_s": 0.0, "end_s": 7.2}
    assert any(i["reason"] == "span_reanchored" for i in result.manifest["issues"])


def test_tiktok_quote_far_from_its_segment_is_still_rejected(tmp_path):
    from corpus.normalize import normalize
    put(tmp_path, "gmaps/list/dalat.json", {"items": [{"fid": "F"}]})
    put(tmp_path, "tiktok/observations/F.json", tiktok_doc(20.0, 25.0))
    tiktok_video(tmp_path)
    result = normalize("dalat", tmp_path, canonical={})
    assert next(result.documents())[1]["observations"] == []
    assert any(i["reason"] == "invalid_source_span" for i in result.manifest["issues"])


def test_review_without_text_is_a_missing_source(tmp_path):
    from corpus.normalize import normalize
    put(tmp_path, "gmaps/list/dalat.json", {"items": [{"fid": "F"}]})
    d = doc()
    d["observations"][0].update(source_type="gmaps_review", source_id="R1")
    put(tmp_path, "gmaps/observations/F.json", d)
    put(tmp_path, "gmaps/places/F/reviews.json", {"reviews": [{"review_id": "R1", "text": ""}]})
    result = normalize("dalat", tmp_path, canonical={})
    assert next(result.documents())[1]["observations"] == []
    assert [i["reason"] for i in result.manifest["issues"] if i.get("id")] == ["missing_source"]
