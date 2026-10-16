"""Structured name retrieval uses serving membership and needs no semantic index."""

import pytest


def test_name_search_preserves_distinctive_tokens_accents_and_release():
    from corpus.retrieval.names import NameRecord, name_score, search_names

    records = [NameRecord("other", "Vườn Xanh"), NameRecord("garden", "Vườn Phẳng Lặng Xanh"),
               NameRecord("outside", "Vườn Phẳng Lặng Xanh")]
    hits = search_names("vuon phang", records, within={"garden", "other"}, release_id="r-pinned")
    assert hits[0].place_id == "garden"
    assert all(h.place_id in {"garden", "other"} for h in hits)
    assert hits[0].release_id == "r-pinned"
    assert name_score("quán cà phê", "Quán Cà Phê Phẳng Lặng") == 0
    assert name_score("Vườn Phẳng Lặng Xanh Đà Lạt", "Vườn Phẳng Lặng Xanh") == 1


def test_name_search_empty_scope_and_limits():
    from corpus.retrieval.names import NameRecord, search_names

    records = [NameRecord("a", "Quán Tùng"), NameRecord("b", "Tùng Cà Phê")]
    assert search_names("Tùng", records, within=set(), release_id=None) == []
    assert search_names("x", records, within={"a"}, release_id=None) == []
    assert search_names("Tùng", records, within={"a", "b"}, release_id=None, limit=0) == []
    assert len(search_names("Tùng", records, within={"a", "b"}, release_id=None, limit=1)) == 1
    with pytest.raises(TypeError):
        search_names("Tùng", records, release_id=None)
