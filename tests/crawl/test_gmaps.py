import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from corpus.crawl import gmaps

FIX = Path(__file__).parents[1] / "fixtures" / "gmaps"


def _parse(fixture: str, fn):
    async def run():
        async with async_playwright() as p:
            b = await p.chromium.launch()
            page = await (await b.new_context(java_script_enabled=False)).new_page()
            await page.set_content((FIX / fixture).read_text(encoding="utf-8"), wait_until="domcontentloaded")
            try:
                return await fn(page)
            finally:
                await b.close()
    return asyncio.run(run())


def test_parse_feed_fixture():
    rows = _parse("feed.html", gmaps.parse_feed)
    assert rows and all(r["fid"].startswith("0x") and ":" in r["fid"] and r["name"] for r in rows)
    assert all(isinstance(r["lat"], float) and isinstance(r["lng"], float) for r in rows)


def test_parse_place_fixture():
    p = _parse("place.html", gmaps.parse_place)
    assert p["name"] and p["category"] and p["address"] and p["rating"]
    assert len(p["hours"]) == 7  # table expanded before capture
    assert len(p["popular_times"]) == 7 and all(p["popular_times"])  # one list of labels per day, Sunday first


def test_parse_reviews_fixture_hides_authors():
    rows = _parse("reviews.html", gmaps.parse_reviews)
    assert rows and all(r["review_id"] and r["text"] is not None and len(r["author_hash"]) == 16 for r in rows)
    assert len({r["review_id"] for r in rows}) == len(rows)
    assert "/contrib/" not in json.dumps(rows)


def test_single_place_page_is_one_result():
    # Maps jumps straight to the place page when a query matches exactly one place.
    rows = _parse("place.html", lambda page: gmaps.parse_feed(page, url=(
        "https://www.google.com/maps/place/X/@11.9,108.4,17z/data=!4m6!3m5!1s0x317114a1a4b93341:0xf8ce8eb72915c065"
        "!8m2!3d11.9034324!4d108.4496999")))
    assert [r["fid"] for r in rows] == ["0x317114a1a4b93341:0xf8ce8eb72915c065"]
    assert rows[0]["lat"] == 11.9034324


@pytest.fixture
def fake_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(gmaps, "load_config", lambda city: ("Đà Lạt", {"gmaps": {
        "max_places_per_query": 5, "max_reviews_per_place": 3, "categories": ["thác"]}}))
    monkeypatch.setattr(gmaps, "pause", lambda *a: asyncio.sleep(0))
    fid = "0x317114a1a4b93341:0xf8ce8eb72915c065"
    calls = {"scrape": 0, "fail": False}

    async def ensure_login(ctx):
        return None

    async def search(ctx, query, limit):
        return [{"fid": fid, "name": "Thác Datanla", "url": "https://maps/x", "lat": 11.9, "lng": 108.4}]

    async def scrape_place(ctx, url, max_reviews):
        calls["scrape"] += 1
        if calls["fail"]:
            raise RuntimeError("layout changed")
        return {"name": "Thác Datanla"}, [{"review_id": "r1"}]

    for name, fn in (("ensure_login", ensure_login), ("search", search), ("scrape_place", scrape_place)):
        monkeypatch.setattr(gmaps, name, fn)

    @asynccontextmanager
    async def profile(source, headed=False):
        yield object()

    return tmp_path / "gmaps", calls, profile


def test_run_writes_place_and_skips_done(fake_env):
    root, calls, profile = fake_env
    asyncio.run(gmaps.run("dalat", profile=profile))
    asyncio.run(gmaps.run("dalat", profile=profile))
    d = root / "places" / "0x317114a1a4b93341_0xf8ce8eb72915c065"
    place = json.loads((d / "place.json").read_text(encoding="utf-8"))
    assert place["fid"].endswith(":0xf8ce8eb72915c065") and place["lat"] == 11.9 and place["fetched_at"]
    assert json.loads((d / "reviews.json").read_text(encoding="utf-8")) == [{"review_id": "r1"}]
    assert calls["scrape"] == 1
    assert len((root / "search" / "dalat" / "thac-da-lat.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_failed_place_is_logged_and_retried(fake_env):
    root, calls, profile = fake_env
    calls["fail"] = True
    asyncio.run(gmaps.run("dalat", profile=profile))
    assert "layout changed" in (root / "errors.jsonl").read_text(encoding="utf-8")
    calls["fail"] = False
    asyncio.run(gmaps.run("dalat", profile=profile))
    assert (root / "places" / "0x317114a1a4b93341_0xf8ce8eb72915c065" / "place.json").exists()


def test_pause_comes_from_config(fake_env, monkeypatch):
    root, calls, profile = fake_env
    seen = []

    async def rec(*a):
        seen.append(a)

    monkeypatch.setattr(gmaps, "pause", rec)
    monkeypatch.setattr(gmaps, "load_config", lambda city: ("Đà Lạt", {"gmaps": {
        "max_places_per_query": 5, "max_reviews_per_place": 3, "pause_s": [0.1, 0.2], "categories": ["thác"]}}))
    asyncio.run(gmaps.run("dalat", profile=profile))
    assert seen and all(a == (0.1, 0.2) for a in seen)
