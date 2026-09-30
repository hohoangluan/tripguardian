from contextlib import asynccontextmanager
import asyncio
import json

import pytest
from gmaps_helpers import fake_sessions, parse_fixture

from corpus.crawl.gmaps import search


def test_parse_feed_fixture():
    rows = parse_fixture("feed.html", search.parse_feed)
    assert rows and all(r["fid"].startswith("0x") and ":" in r["fid"] and r["name"] for r in rows)
    assert all(isinstance(r["lat"], float) and isinstance(r["lng"], float) for r in rows)


def test_single_place_page_is_one_result():
    # Maps jumps straight to the place page when a query matches exactly one place.
    rows = parse_fixture("place.html", lambda page: search.parse_feed(page, url=(
        "https://www.google.com/maps/place/X/@11.9,108.4,17z/data=!4m6!3m5!1s0x317114a1a4b93341:0xf8ce8eb72915c065"
        "!8m2!3d11.9034324!4d108.4496999")))
    assert [r["fid"] for r in rows] == ["0x317114a1a4b93341:0xf8ce8eb72915c065"]
    assert rows[0]["lat"] == 11.9034324


ANY_TILE = "any"


@pytest.fixture
def grid(data, monkeypatch):
    monkeypatch.setattr(search, "load_config", lambda city: ("Đà Lạt", {"area": [11.90, 108.40, 11.98, 108.48], "gmaps": {
        "categories": ["quán cà phê"], "cooldown_s": 0,
        "grid": {"start_zoom": 14, "max_zoom": 16, "lodging_max_zoom": 15, "full_at": 3}}}))
    monkeypatch.setattr(search, "pause", lambda *a: asyncio.sleep(0))

    searched = []

    truncated = set()  # tiles whose list stops before its end (scroll stuck); ANY_TILE = all of them
    lodging = [False]  # Maps switched to its hotel list, which ignores the viewport

    async def fake_search(ctx, query, limit, at):
        searched.append((query, at))
        full = at[2] == 14 and not [s for s in searched[:-1] if s[1][2] == 14]  # only the first root tile is capped
        rows = [{"fid": f"0x{len(searched)}:0x{i}", "name": "Cafe", "url": "u", "lat": at[0] if full else 20.0, "lng": at[1] if full else 1.0, "category": "Quán cà phê", "rating": 4.5, "reviews": 10}
                for i in range(3 if full else 1)]
        return rows, not (at in truncated or ANY_TILE in truncated), lodging[0]

    monkeypatch.setattr(search, "search", fake_search)
    return data, searched, truncated, lodging


def test_full_tile_is_split_and_done_tiles_are_not_searched_again(grid):
    data, searched, _, _ = grid
    asyncio.run(search.run("dalat", sessions=fake_sessions))
    assert all(q == "quán cà phê" for q, _ in searched)  # the viewport, not the city name, bounds the search
    assert len([s for s in searched if s[1][2] == 15]) == 4 and not [s for s in searched if s[1][2] == 16]
    # only the capped tile is split, and its children are not capped
    lines = (data / "search" / "dalat" / "quan-ca-phe.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(searched)
    assert all(json.loads(l)["tile"] and json.loads(l)["end"] and json.loads(l)["lodging"] is False for l in lines)
    assert all(i["lat"] != 20.0 for l in lines for i in json.loads(l)["items"])  # places outside the area are dropped
    n = len(searched)
    asyncio.run(search.run("dalat", sessions=fake_sessions))
    assert len(searched) == n


def test_tile_whose_list_did_not_reach_its_end_is_split(grid):
    # A short list that never showed the end marker is not the whole tile: look closer instead of trusting it.
    data, searched, truncated, _ = grid
    root = (11.96, 108.44, 14)  # the grid's second root tile: never capped in the fake
    truncated.add(root)
    asyncio.run(search.run("dalat", sessions=fake_sessions))
    tiles = [at for _, at in searched]
    assert root in tiles and len([t for t in tiles if t[2] == 15]) == 8  # capped tile + truncated tile, 4 each


def test_old_records_without_end_flag_are_searched_again(grid):
    data, searched, _, _ = grid
    out = data / "search" / "dalat" / "quan-ca-phe.jsonl"
    out.parent.mkdir(parents=True)
    tile = [11.96, 108.44, 14]
    out.write_text(json.dumps({"query": "quán cà phê", "tile": tile, "items": []}) + "\n", encoding="utf-8")
    asyncio.run(search.run("dalat", sessions=fake_sessions))
    assert tuple(tile) in [at for _, at in searched]
    assert out.read_text(encoding="utf-8").splitlines()[0] == json.dumps(
        {"query": "quán cà phê", "tile": tile, "items": []})  # append-only: the old line stays


def test_lodging_list_is_split_only_to_lodging_max_zoom(grid):
    # Hotel mode ignores the viewport: every tile returns ~the same city-wide list, cut short with no end marker.
    data, searched, truncated, lodging = grid
    lodging[0] = True
    truncated.add(ANY_TILE)  # every hotel list is cut short
    asyncio.run(search.run("dalat", sessions=fake_sessions))
    assert not [at for _, at in searched if at[2] > 15]  # max_zoom is 16, but lodging stops at 15
    line = json.loads((data / "search" / "dalat" / "quan-ca-phe.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert line["lodging"] is True


def test_old_record_without_lodging_flag_is_searched_again_only_if_it_would_split(grid):
    data, searched, _, _ = grid
    out = data / "search" / "dalat" / "quan-ca-phe.jsonl"
    out.parent.mkdir(parents=True)
    rows = [{"fid": f"0x9:0x{i}", "name": "Cafe", "url": "u", "lat": 20.0, "lng": 1.0, "category": "C", "rating": 4.5, "reviews": 10} for i in range(3)]
    out.write_text(json.dumps({"query": "quán cà phê", "tile": [11.92, 108.44, 14], "end": True, "items": rows}) + "\n"
                   + json.dumps({"query": "quán cà phê", "tile": [11.96, 108.44, 14], "end": True, "items": rows[:1]}) + "\n",
                   encoding="utf-8")
    asyncio.run(search.run("dalat", sessions=fake_sessions))
    tiles = [at for _, at in searched]
    assert (11.92, 108.44, 14) in tiles  # capped: the lodging flag decides how deep to split
    assert (11.96, 108.44, 14) not in tiles  # short and complete: no split either way, reused


def test_tiles_are_searched_in_parallel_tabs(grid, monkeypatch):
    data, searched, _, _ = grid
    cfg = search.load_config("dalat")[1]
    cfg["gmaps"].update(search_tabs=3, search_tabs_start=3)
    monkeypatch.setattr(search, "load_config", lambda city: ("Đà Lạt", cfg))
    active, peak = [0], [0]

    async def slow(ctx, query, limit, at):
        active[0] += 1
        peak[0] = max(peak[0], active[0])
        await asyncio.sleep(0.02)
        active[0] -= 1
        searched.append((query, at))
        return [{"fid": f"0x{len(searched)}:0x1", "name": "C", "url": "u", "lat": 20.0, "lng": 1.0, "category": "C", "rating": 4.5, "reviews": 10}], True, False

    monkeypatch.setattr(search, "search", slow)
    cfg["gmaps"]["categories"] = ["quán cà phê", "nhà hàng"]
    asyncio.run(search.run("dalat", sessions=fake_sessions))
    assert peak[0] == 2 and len(searched) == 4  # 2 root tiles at once; categories one after another
    assert [q for q, _ in searched] == ["quán cà phê"] * 2 + ["nhà hàng"] * 2  # a category is finished first


def test_blocked_tile_is_retried_after_cooldown(grid, monkeypatch):
    data, searched, _, _ = grid
    tries = []

    async def flaky(ctx, query, limit, at):
        tries.append(at)
        if len(tries) == 1:
            raise TimeoutError("Page.goto: Timeout 30000ms exceeded")
        return [{"fid": f"0x{len(tries)}:0x1", "name": "C", "url": "u", "lat": 20.0, "lng": 1.0, "category": "C", "rating": 4.5, "reviews": 10}], True, False

    monkeypatch.setattr(search, "search", flaky)
    asyncio.run(search.run("dalat", sessions=fake_sessions))
    assert tries[0] == tries[1] and len((data / "search" / "dalat" / "quan-ca-phe.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_parse_feed_keeps_category_and_drops_visited_suffix():
    rows = parse_fixture("feed.html", search.parse_feed)
    first = rows[0]
    assert first["category"] == "Điểm thu hút khách du lịch"
    assert "Đường liên kết" not in first["name"] and first["name"] == "Khu du lịch Thác Datanla"
    assert all("category" in r for r in rows)
    assert first["rating"] == 4.4 and first["reviews"] == 25362


def test_records_without_category_are_searched_again(grid):
    data, searched, _, _ = grid
    out = data / "search" / "dalat" / "quan-ca-phe.jsonl"
    out.parent.mkdir(parents=True)
    old = [{"fid": "0x9:0x1", "name": "Cafe", "url": "u", "lat": 20.0, "lng": 1.0}]  # before category / rating were kept
    out.write_text(json.dumps({"query": "quán cà phê", "tile": [11.96, 108.44, 14], "end": True, "lodging": False,
                               "items": old}) + "\n", encoding="utf-8")
    asyncio.run(search.run("dalat", sessions=fake_sessions))
    assert (11.96, 108.44, 14) in [at for _, at in searched]


def test_cut_short_list_is_a_soft_block_retried_after_cooldown(grid, monkeypatch):
    # Maps answers a session that loads too fast with lists that stop growing: slow down and search the tile again.
    data, searched, _, _ = grid
    calls = []

    async def throttled_once(ctx, query, limit, at):
        calls.append(at)
        end = len(calls) > 1
        return [{"fid": f"0x{len(calls)}:0x1", "name": "C", "url": "u", "lat": 20.0, "lng": 1.0, "category": "C",
                 "rating": 4.5, "reviews": 10}], end, False

    monkeypatch.setattr(search, "search", throttled_once)
    asyncio.run(search.run("dalat", sessions=fake_sessions))
    assert calls[0] == calls[1]  # same tile again after the cut-short answer
    recs = [json.loads(l) for l in (data / "search" / "dalat" / "quan-ca-phe.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all(r["end"] for r in recs) and len(recs) == 2  # the cut-short answer was not saved


def test_every_try_runs_in_its_own_fresh_session(grid, monkeypatch):
    # Google limits one session, not the IP: a retry after a cut-short list must not reuse the blocked session.
    data, searched, _, _ = grid
    opened, closed, seen = [], [], []

    class Session:
        async def close(self):
            closed.append(self)

    @asynccontextmanager
    async def sessions(headed=False):
        async def new_session():
            opened.append(Session())
            return opened[-1]
        yield new_session

    async def cut_once(ctx, query, limit, at):
        seen.append(ctx)
        return [{"fid": f"0x{len(seen)}:0x1", "name": "C", "url": "u", "lat": 20.0, "lng": 1.0, "category": "C",
                 "rating": 4.5, "reviews": 10}], len(seen) > 1, False

    monkeypatch.setattr(search, "search", cut_once)
    asyncio.run(search.run("dalat", sessions=sessions))
    assert len(set(map(id, seen))) == len(seen) and sorted(map(id, closed)) == sorted(map(id, opened))


def test_network_error_is_retried(grid, monkeypatch):
    data, searched, _, _ = grid
    tries = []

    async def dropped_once(ctx, query, limit, at):
        tries.append(at)
        if len(tries) == 1:
            raise RuntimeError("Page.goto: net::ERR_NETWORK_CHANGED at https://www.google.com/maps/search/x")
        return [{"fid": f"0x{len(tries)}:0x1", "name": "C", "url": "u", "lat": 20.0, "lng": 1.0, "category": "C",
                 "rating": 4.5, "reviews": 10}], True, False

    monkeypatch.setattr(search, "search", dropped_once)
    asyncio.run(search.run("dalat", sessions=fake_sessions))
    assert tries[0] == tries[1]


def test_list_filled_with_far_away_places_is_not_split(grid, monkeypatch):
    # Maps pads a short local list with places in other cities: the tile is not capped, looking closer finds nothing
    data, searched, _, _ = grid

    async def padded(ctx, query, limit, at):
        searched.append((query, at))
        return [{"fid": f"0x{len(searched)}:0x{i}", "name": "Mall", "url": "u", "lat": 10.78, "lng": 106.7,
                 "category": "Trung tâm thương mại", "rating": 4.5, "reviews": 10} for i in range(3)], True, False

    monkeypatch.setattr(search, "search", padded)
    asyncio.run(search.run("dalat", sessions=fake_sessions))
    assert all(at[2] == 14 for _, at in searched)  # root tiles only
