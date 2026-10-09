import pytest
from gmaps_helpers import data  # noqa: F401  (fixtures)


@pytest.fixture(autouse=True)
def _isolated_gate(monkeypatch, tmp_path):
    """Tests never touch the real data/gmaps/block.json (it rests the live crawl) and never wait out a cooldown."""
    from corpus.crawl.gmaps import gate

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(gate, "BASE_COOL_S", 0)
    monkeypatch.setattr(gate, "MAX_COOL_S", 0)
