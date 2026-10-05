from corpus.observe.gmaps.extract import prune


def test_prune_drops_flagged_reviews_evidence_keeps_attributes():
    doc = {"observations": [
        {"id": "a", "source_type": "gmaps_review", "source_id": "r1"},
        {"id": "b", "source_type": "gmaps_details", "source_id": "r2"},
        {"id": "c", "source_type": "gmaps_attribute", "source_id": "r2"},
        {"id": "d", "source_type": "gmaps_review", "source_id": "r3"}],
        "ratings": [{"author": "h2", "stars": 5}, {"author": "h3", "stars": 4}],
        "proposed": [{"source_id": "r2"}], "voices": 3, "stats": {}}
    reviews = [{"review_id": "r1", "author_hash": "h1", "text": "ok"},
               {"review_id": "r2", "author_hash": "h2", "text": "Cảm ơn quý khách đã ủng hộ quán nhé!"},
               {"review_id": "r3", "author_hash": "h3", "text": "Quán ngon, view đẹp, sẽ quay lại"}]
    out = prune(doc, reviews, {"r2"})
    assert [o["id"] for o in out["observations"]] == ["a", "c", "d"]
    assert out["ratings"] == [{"author": "h3", "stars": 4}] and out["proposed"] == []
    assert out["voices"] == 2 and out["qc_dropped"] == ["r2"]
