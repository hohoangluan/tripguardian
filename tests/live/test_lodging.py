from contextlib import asynccontextmanager

import pytest

from corpus.crawl import LoginRequired
from live import settings
from live.http import Unavailable
from live.lodging import maps


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def cfg():
    settings.load.cache_clear()
    c = settings.load(settings.PATH)
    yield c
    settings.load.cache_clear()


class FakeCtx:
    async def close(self):
        pass


@asynccontextmanager
async def fake_sessions(headed=False):
    async def new_session():
        return FakeCtx()

    yield new_session


def rows(*price_amenity):
    return [{"fid": f"h{i}", "name": f"Homestay {i}", "lat": 11.94 + i * 0.001, "lng": 108.45, "rating": 4.5,
            "reviews": 20, "price_vnd": p, "amenities": a} for i, (p, a) in enumerate(price_amenity)]


@pytest.fixture
def search(monkeypatch):
    calls = []

    async def fake(ctx, query, limit, at):
        calls.append((query, limit, at))
        return rows((500000, ["wifi"]), (None, [])), True, True

    monkeypatch.setattr(maps, "open_sessions", fake_sessions)
    monkeypatch.setattr(maps, "maps_search", fake)
    return calls


def test_candidates_carry_their_provenance(cfg, search):
    out = maps.lodging_near((11.94, 108.45), 3.0, "2026-12-12", "2026-12-14", None, cfg)
    assert {c["id"] for c in out} == {"h0", "h1"}
    assert out[0]["source"] == "gmaps" and out[0]["fetched_at"]


def test_a_price_over_the_cap_is_dropped_but_an_unknown_price_is_kept(cfg, search):
    out = maps.lodging_near((11.94, 108.45), 3.0, None, None, 400000, cfg)
    assert {c["id"] for c in out} == {"h1"}


def test_the_second_call_for_the_same_area_comes_from_the_cache(cfg, search):
    maps.lodging_near((11.94, 108.45), 3.0, None, None, None, cfg)
    maps.lodging_near((11.94, 108.45), 3.0, None, None, None, cfg)
    assert len(search) == 1


def test_a_different_radius_is_a_different_cache_entry(cfg, search):
    maps.lodging_near((11.94, 108.45), 3.0, None, None, None, cfg)
    maps.lodging_near((11.94, 108.45), 6.0, None, None, None, cfg)
    assert len(search) == 2


def test_maps_not_switching_to_its_hotel_list_is_unavailable(cfg, monkeypatch):
    async def not_lodging(ctx, query, limit, at):
        return [], True, False

    monkeypatch.setattr(maps, "open_sessions", fake_sessions)
    monkeypatch.setattr(maps, "maps_search", not_lodging)
    with pytest.raises(Unavailable):
        maps.lodging_near((11.94, 108.45), 3.0, None, None, None, cfg)


def test_login_required_is_unavailable_not_a_crash(cfg, monkeypatch):
    async def blocked(ctx, query, limit, at):
        raise LoginRequired("gmaps")

    monkeypatch.setattr(maps, "open_sessions", fake_sessions)
    monkeypatch.setattr(maps, "maps_search", blocked)
    with pytest.raises(Unavailable):
        maps.lodging_near((11.94, 108.45), 3.0, None, None, None, cfg)
