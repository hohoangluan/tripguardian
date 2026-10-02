import json

import pytest
from fixtures import si

from decision.session import Drop, State, Store


def test_store_roundtrip_and_ids(tmp_path):
    store = Store(tmp_path)
    s = store.new(si(), "abcdef012345", State(selected=["A"]))
    s.state.dropped.append(Drop(place_id="B", reason="far"))
    store.save(s)
    again = Store(tmp_path).get(s.id)
    assert again.state.dropped[0].reason == "far" and again.search_input == s.search_input
    assert json.loads((tmp_path / f"{s.id}.json").read_text(encoding="utf-8"))["trip_session"] == "abcdef012345"
    with pytest.raises(KeyError):
        store.get("../etc")
    with pytest.raises(KeyError):
        store.get("0123456789ab")
    assert store.lock(s.id) is store.lock(s.id)


def test_memory_only_store():
    store = Store(None)
    s = store.new(si(), None, State())
    store.save(s)
    assert store.get(s.id) is s
