import asyncio
import json
import re

import pytest
from gmaps_helpers import fake_profile, parse_fixture

from corpus.crawl.gmaps import crawl

FID = "0x317114a1a4b93341:0xf8ce8eb72915c065"
DIR = "0x317114a1a4b93341_0xf8ce8eb72915c065"


def test_parse_place_fixture():
    p = parse_fixture("place.html", crawl.parse_place)
    assert p["name"] and p["category"] and p["address"] and p["rating"]
    assert len(p["hours"]) == 7  # table expanded before capture
    assert len(p["popular_times"]) == 7 and all(p["popular_times"])  # one list of labels per day, Sunday first
    assert len(p["rating_histogram"]) == 5 and p["rating_histogram"][0].startswith("5 sao")
    assert p["plus_code"] and "+" in p["plus_code"]
    assert p["tickets"] is None or "Vé vào cửa" in p["tickets"]
    icons = re.compile("[-]")  # Google's icon font glyphs are not text
    assert not icons.search(p["address"]) and p["address"] == p["address"].strip()
    assert not any(icons.search(h) for h in p["hours"]) and all(h == h.strip() for h in p["hours"])


def test_parse_reviews_fixture():
    rows = parse_fixture("reviews.html", crawl.parse_reviews)
    assert rows and all(r["review_id"] and r["text"] is not None and len(r["author_hash"]) == 16 for r in rows)
    assert len({r["review_id"] for r in rows}) == len(rows)
    assert "/contrib/" not in json.dumps(rows)  # authors hidden
    assert not any(k.startswith("owner") for r in rows for k in r)  # owner replies are not evidence


def test_owner_reply_is_never_taken_as_the_review_text():
    async def both(page):
        owner = await page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('div.jftiEf[data-review-id]')]
          .filter(r => r.querySelector('.CDe7pd .wiI7pd')).map(r => [r.dataset.reviewId, r.querySelector('.CDe7pd .wiI7pd').innerText.trim()]))""")
        return owner, await crawl.parse_reviews(page)

    owner, rows = parse_fixture("reviews.html", both)
    assert owner and all(r["text"] != owner[r["review_id"]] for r in rows if r["review_id"] in owner)
    assert all(isinstance(r["details"], list) and isinstance(r["photos"], int) and isinstance(r["likes"], int) for r in rows)
    assert all(r["author_meta"] is None or re.search("đánh giá|ảnh", r["author_meta"]) for r in rows)


@pytest.mark.parametrize("text,months", [
    ("9 phút trước", 0), ("2 giờ trước", 0), ("1 ngày trước", 0), ("3 tuần trước", 0),
    ("một tháng trước", 1), ("4 tháng trước", 4), ("một năm trước", 12), ("2 năm trước", 24),
    ("Đã chỉnh sửa 5 tháng trước", 5), (None, None), ("", None),
])
def test_age_months(text, months):
    assert crawl.age_months(text) == months


@pytest.mark.parametrize("text,n", [("1.701 bài đánh giá", 1701), ("27 bài đánh giá", 27), (None, None), ("", None)])
def test_count(text, n):
    assert crawl.count(text) == n


def test_keep_recent_keeps_minimum_then_drops_old():
    rows = [{"published_text": t} for t in ["2 tuần trước", "3 tháng trước", "một năm trước", "2 năm trước", "3 năm trước"]]
    assert len(crawl.keep_recent(rows, max_age_months=12, min_count=0)) == 3  # 12 months still counts
    assert len(crawl.keep_recent(rows, max_age_months=6, min_count=4)) == 4  # quiet place keeps a minimum
    assert crawl.keep_recent(rows, max_age_months=None, min_count=0) == rows


@pytest.fixture
def env(data, monkeypatch):
    monkeypatch.setattr(crawl, "load_config", lambda city: ("Đà Lạt", {"gmaps": {
        "max_reviews_per_place": 200, "cooldown_s": 0, "pause_s": [0.1, 0.2]}}))
    pauses = []

    async def rec(*a):
        pauses.append(a)

    async def ensure_login(ctx):
        return None

    monkeypatch.setattr(crawl, "pause", rec)
    monkeypatch.setattr(crawl, "ensure_login", ensure_login)
    calls = {"scrape": 0, "result": ({"name": "Thác Datanla"}, [{"review_id": "r1"}])}

    async def scrape_place(ctx, url, max_reviews, *a):
        calls["scrape"] += 1
        if isinstance(calls["result"], Exception):
            raise calls["result"]
        return calls["result"]

    monkeypatch.setattr(crawl, "scrape_place", scrape_place)
    row = {"fid": FID, "name": "Thác Datanla", "url": "https://maps/x", "lat": 11.9, "lng": 108.4, "queries": ["thác"]}
    (data / "list").mkdir(parents=True)
    (data / "list" / "dalat.json").write_text(json.dumps({"items": [row]}), encoding="utf-8")
    return data, calls, pauses


def test_crawl_writes_place_from_list_and_skips_done(env):
    data, calls, pauses = env
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    p = json.loads((data / "places" / DIR / "place.json").read_text(encoding="utf-8"))
    assert p["fid"] == FID and p["lat"] == 11.9 and p["queries"] == ["thác"] and p["fetched_at"]
    assert json.loads((data / "places" / DIR / "reviews.json").read_text(encoding="utf-8")) == [{"review_id": "r1"}]
    assert calls["scrape"] == 1 and pauses == [(0.1, 0.2)]


def test_failed_place_is_logged_and_retried_next_run(env):
    data, calls, _ = env
    calls["result"] = RuntimeError("layout changed")
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    assert "layout changed" in (data / "errors.jsonl").read_text(encoding="utf-8")
    calls["result"] = ({"name": "Thác Datanla"}, [])
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    assert (data / "places" / DIR / "place.json").exists()


def test_place_with_reviews_but_none_captured_is_not_done(env):
    # Under load the review list can still be empty when scrolling starts; that place must be retried, not saved.
    data, calls, _ = env
    calls["result"] = ({"name": "Thác Datanla", "review_count": "3.114 bài đánh giá"}, [])
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    assert not (data / "places" / DIR / "place.json").exists()
    assert "too few reviews: 0 of 3.114" in (data / "errors.jsonl").read_text(encoding="utf-8")


def test_place_with_a_handful_of_reviews_is_retried_not_saved(env):
    # A signed-out or throttled page shows ~8 reviews and no more: never saved, so the next run tries again.
    data, calls, _ = env
    calls["result"] = ({"name": "Dinh III", "review_count": "9.636 bài đánh giá"}, [{"review_id": "r1"}, {"review_id": "r2"}])
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    assert not (data / "places" / DIR / "place.json").exists()
    assert calls["scrape"] == crawl.ATTEMPTS
    assert "too few reviews: 2 of 9.636" in (data / "errors.jsonl").read_text(encoding="utf-8")


def test_saved_place_with_too_few_reviews_is_crawled_again(env):
    data, calls, _ = env
    d = data / "places" / DIR
    d.mkdir(parents=True)
    (d / "reviews.json").write_text(json.dumps([{"review_id": "r1", "published_text": "2 tuần trước"}]), encoding="utf-8")
    (d / "place.json").write_text(json.dumps({"fid": FID, "review_count": "340 bài đánh giá", "fetched_at": "t"}), encoding="utf-8")
    calls["result"] = ({"name": "Thác Datanla", "review_count": "340 bài đánh giá"}, [{"review_id": f"r{i}"} for i in range(300)])
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    assert calls["scrape"] == 1 and len(json.loads((d / "reviews.json").read_text(encoding="utf-8"))) == 300


def test_incomplete_reviews_are_retried_then_saved_flagged(env):
    data, calls, _ = env
    calls["result"] = ({"name": "Suối Bình Yên", "reviews_complete": False}, [{"review_id": "r1"}])
    asyncio.run(crawl.run("dalat", profile=fake_profile))
    p = json.loads((data / "places" / DIR / "place.json").read_text(encoding="utf-8"))
    assert calls["scrape"] == crawl.ATTEMPTS and p["reviews_complete"] is False
    assert "reviews incomplete after retries" in (data / "errors.jsonl").read_text(encoding="utf-8")


CAP = {"max_reviews_per_place": 200}


@pytest.mark.parametrize("n,count,cfg,age_cut,thin", [
    (8, "9.636 bài đánh giá", CAP, False, True),  # signed-out / throttled page
    (8, "9.636 bài đánh giá", CAP, True, False),  # only 8 reviews under a year old
    (13, "14 bài đánh giá", CAP, False, False),  # Maps' count runs a little above the list
    (120, "9.636 bài đánh giá", CAP, False, False),
    (0, None, CAP, False, False),  # no count shown
    (300, "9.636 bài đánh giá", {"max_reviews_per_place": None}, False, True),  # no cap: all of them expected
    (5000, "9.636 bài đánh giá", {"max_reviews_per_place": None}, False, False),
    (0, "50 bài đánh giá", {"max_reviews_per_place": 0}, False, False),  # reviews not wanted
])
def test_too_few(n, count, cfg, age_cut, thin):
    assert crawl.too_few(n, count, cfg, age_cut) is thin


def test_keep_recent_without_minimum_drops_every_old_review():
    rows = [{"published_text": t} for t in ["2 tuần trước", "11 tháng trước", "một năm trước", "2 năm trước"]]
    assert [r["published_text"] for r in crawl.keep_recent(rows, 11, 0)] == ["2 tuần trước", "11 tháng trước"]


def test_crawl_needs_list(data, monkeypatch):
    monkeypatch.setattr(crawl, "load_config", lambda city: ("Đà Lạt", {"gmaps": {}}))
    with pytest.raises(SystemExit, match="gmaps list"):
        asyncio.run(crawl.run("dalat", profile=fake_profile))


def test_parse_reviews_lodging_layout():
    # Hotels / homestays / glamping show "4/5" and "3 tuần trước trên Google" instead of the star label and .rsqaWe.
    rows = parse_fixture("reviews_lodging.html", crawl.parse_reviews)
    assert len(rows) == 1
    assert rows[0]["rating"] == "4/5"
    assert rows[0]["published_text"] == "3 tuần trước trên Google" and crawl.age_months(rows[0]["published_text"]) == 0
    assert rows[0]["text"].startswith("- Vị trí")


def test_list_end_signal_on_fixture():
    # The fixture pane ends in an empty div: Maps' loader after the last batch.
    assert parse_fixture("reviews_lodging.html", lambda page: page.evaluate(crawl.LIST_END_JS)) is True
