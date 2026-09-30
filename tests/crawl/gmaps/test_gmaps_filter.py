import asyncio
import dataclasses
import json

import pytest
from gmaps_helpers import AREA

from corpus import review
from corpus.crawl.gmaps import filter as gfilter, listing


def _row(fid, name=None, category="Thác nước", lat=11.94, lng=108.44, rating=4.5, reviews=100):
    return {"fid": fid, "name": name or fid, "url": f"https://maps/{fid}", "lat": lat, "lng": lng, "category": category,
            "rating": rating, "reviews": reviews}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(gfilter, "load_config", lambda city: ("Đà Lạt", {"area": AREA}))
    monkeypatch.setattr(gfilter, "_client", lambda: (None, "gemma-test"))
    root = tmp_path / "gmaps"
    search = root / "search" / "dalat"
    search.mkdir(parents=True)

    def write_search(query, rows, lodging=False):
        rec = {"query": query, "tile": [1, 1, 13], "end": True, "lodging": lodging, "items": rows}
        (search / f"{query}.jsonl").write_text(json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8")

    calls, answers = [], {}

    async def classify(client, model, row, city):
        calls.append(row["fid"])
        return answers.get(row["fid"], {"relevance": "yes", "reason": "a sight"})

    monkeypatch.setattr(gfilter, "classify", classify)
    return root, write_search, calls, answers


def test_each_place_judged_once_across_queries(env):
    root, write_search, calls, answers = env
    write_search("thac", [_row("a"), _row("b", "Công ty Thác Mơ", "Công ty xây dựng")])
    write_search("ho", [_row("a"), _row("c", "Đồi 1508", None)])
    answers["b"] = {"relevance": "no", "reason": "a company"}
    answers["c"] = {"relevance": "unsure", "reason": "bare name"}
    summary = asyncio.run(gfilter.run("dalat"))
    assert summary["places"] == 3 and summary["relevance"] == {"yes": 1, "no": 1, "unsure": 1} and summary["kept"] == 2
    asyncio.run(gfilter.run("dalat"))
    assert sorted(calls) == ["a", "b", "c"]  # unchanged places are not judged again
    assert listing.kept_fids(root / "filter") == {"a", "c"}


def test_outside_area_and_lodging_are_not_judged(env):
    root, write_search, calls, _ = env
    write_search("thac", [_row("a"), _row("hcm", lat=10.9, lng=106.7), _row("hotel", category="Khách sạn")])
    write_search("ks", [_row("list-hotel")], lodging=True)
    asyncio.run(gfilter.run("dalat"))
    assert calls == ["a"]


def test_changed_category_or_prompt_is_judged_again(env, monkeypatch):
    root, write_search, calls, _ = env
    write_search("thac", [_row("a")])
    asyncio.run(gfilter.run("dalat"))
    write_search("thac", [_row("a", category="Công viên")])
    asyncio.run(gfilter.run("dalat"))
    monkeypatch.setattr(gfilter, "PLACE_FILTER", dataclasses.replace(gfilter.PLACE_FILTER, prompt="new {city}{name}{category}"))
    asyncio.run(gfilter.run("dalat"))
    assert calls == ["a", "a", "a"]


def test_model_error_leaves_place_unjudged_and_not_kept(env, monkeypatch):
    root, write_search, calls, _ = env
    write_search("thac", [_row("a")])

    async def broken(client, model, row, city):
        raise RuntimeError("model down")

    monkeypatch.setattr(gfilter, "classify", broken)
    summary = asyncio.run(gfilter.run("dalat"))
    assert summary["llm_errors"] == 1 and listing.kept_fids(root / "filter") == set()


def test_person_overrides_model_and_list_ranks_only_kept(env):
    root, write_search, _, answers = env
    write_search("thac", [_row("a"), _row("b"), _row("c")])
    answers["b"] = {"relevance": "no", "reason": "x"}
    asyncio.run(gfilter.run("dalat"))
    assert ("place_filter", "b") in {(i["kind"], i["id"]) for i in review.queue("dalat")}
    review.decide("place_filter", "b", "keep")
    review.decide("place_filter", "c", "drop")
    kept = listing.kept_fids(root / "filter")
    assert kept == {"a", "b"}
    lst = listing.build(root / "search" / "dalat", AREA, kept=kept)
    assert sorted(r["fid"] for r in lst["items"]) == ["a", "b"] and lst["stats"]["not_kept"] == 1


def test_prompt_shows_name_and_category():
    msg = gfilter.PLACE_FILTER.render(city="Đà Lạt", name="Thác Datanla", category="Thắng cảnh")
    assert "Thác Datanla" in msg and "Thắng cảnh" in msg


def test_counts_opens_only_kept_places_whose_cards_hid_the_count(tmp_path):
    from corpus.crawl.gmaps import counts
    d = tmp_path / "search"
    d.mkdir()
    rows = [[_row("hidden", reviews=None), _row("seen-later", reviews=None), _row("unrated", rating=None, reviews=None),
             _row("dropped", reviews=None)], [_row("seen-later", reviews=300)]]
    (d / "a.jsonl").write_text("\n".join(json.dumps({"query": "q", "tile": [i, i, 13], "end": True, "lodging": False,
                                                     "items": r}) for i, r in enumerate(rows)) + "\n", encoding="utf-8")
    kept = {"hidden", "seen-later", "unrated"}
    assert [r["fid"] for r in counts.missing(d, AREA, kept)] == ["hidden"]
