import json

from corpus.crawl.tiktok import listing


def _it(i, **kw):
    return {"video_id": str(i), "url": f"https://www.tiktok.com/@a/video/{i}", "author_id": "a", "desc": "d",
            "created_at": 1, "hashtags": [], "photo": False, **kw}


def test_build_dedupes_across_queries(tmp_path):
    d = tmp_path / "search"
    d.mkdir()
    (d / "a.jsonl").write_text(json.dumps({"group": "g", "query": "a", "items": [_it(1), _it(2)]}) + "\n", encoding="utf-8")
    (d / "b.jsonl").write_text(json.dumps({"group": "g", "query": "b", "items": [_it(2), _it(3, photo=True)]}) + "\n",
                               encoding="utf-8")
    lst = listing.build(d)
    assert lst["stats"] == {"raw": 4, "duplicates": 1, "videos": 3}
    by = {r["video_id"]: r for r in lst["items"]}
    assert by["2"]["queries"] == ["a", "b"] and by["3"]["photo"] is True


def test_run_writes_list(data):
    (data / "search" / "dalat").mkdir(parents=True)
    (data / "search" / "dalat" / "a.jsonl").write_text(json.dumps({"query": "a", "items": [_it(1)]}) + "\n", encoding="utf-8")
    assert listing.run("dalat")["videos"] == 1
    assert json.loads((data / "list" / "dalat.json").read_text(encoding="utf-8"))["items"][0]["video_id"] == "1"
