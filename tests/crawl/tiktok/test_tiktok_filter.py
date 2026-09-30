import asyncio
import dataclasses
import json

import pytest

from corpus.crawl.tiktok import filter as tfilter


def _row(i, desc="Đà Lạt có gì chơi #dalat"):
    return {"video_id": str(i), "url": f"https://www.tiktok.com/@a/video/{i}", "author_id": "a", "desc": desc,
            "created_at": 1, "hashtags": ["dalat"], "photo": False, "queries": ["Đà Lạt có gì chơi"]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(tfilter, "load_config", lambda city: ("Đà Lạt", {}))
    monkeypatch.setattr(tfilter, "_client", lambda: (None, "gemma-test"))
    root = tmp_path / "tiktok"
    (root / "list").mkdir(parents=True)

    def write_list(rows):
        (root / "list" / "dalat.json").write_text(json.dumps({"items": rows}, ensure_ascii=False), encoding="utf-8")

    calls, answers = [], {}

    async def classify(client, model, row, city):
        calls.append(row["video_id"])
        return answers.get(row["video_id"], {"relevance": "yes", "reason": "travel in Da Lat"})

    monkeypatch.setattr(tfilter, "classify", classify)
    return root, write_list, calls, answers


def test_run_judges_each_video_once_and_writes_summary(env):
    root, write_list, calls, answers = env
    write_list([_row(1), _row(2, "Được 105 ngày thất nghiệp rùi #dailyvlog"), _row(3, "#comga20k")])
    answers["2"] = {"relevance": "no", "reason": "personal life, not travel"}
    answers["3"] = {"relevance": "unsure", "reason": "caption too short"}
    summary = asyncio.run(tfilter.run("dalat"))
    assert summary["relevance"] == {"yes": 1, "no": 1, "unsure": 1} and summary["kept"] == 2
    out = json.loads((root / "filter" / "2.json").read_text(encoding="utf-8"))
    assert out["llm"]["relevance"] == "no" and out["model"] == "gemma-test" and out["desc"].startswith("Được 105")
    asyncio.run(tfilter.run("dalat"))
    assert sorted(calls) == ["1", "2", "3"]  # unchanged captions are not judged again


def test_changed_caption_is_judged_again(env):
    root, write_list, calls, _ = env
    write_list([_row(1)])
    asyncio.run(tfilter.run("dalat"))
    write_list([_row(1, "Caption mới #dalat")])
    asyncio.run(tfilter.run("dalat"))
    assert calls == ["1", "1"]


def test_changed_prompt_is_judged_again(env, monkeypatch):
    root, write_list, calls, _ = env
    write_list([_row(1)])
    asyncio.run(tfilter.run("dalat"))
    monkeypatch.setattr(tfilter, "VIDEO_FILTER", dataclasses.replace(tfilter.VIDEO_FILTER, prompt="new {city}{desc}{hashtags}"))
    asyncio.run(tfilter.run("dalat"))
    assert calls == ["1", "1"]


def test_prompt_shows_caption_and_hashtags_only():
    msg = tfilter.VIDEO_FILTER.render(city="Đà Lạt", desc="Quán ốc ngon", hashtags="#dalat")
    assert "Quán ốc ngon" in msg and "#dalat" in msg and "query" not in msg.lower()


def test_photo_posts_are_not_judged(env):
    root, write_list, calls, _ = env
    write_list([{**_row(1), "photo": True}])
    asyncio.run(tfilter.run("dalat"))
    assert calls == []


def test_model_error_keeps_the_video_unjudged(env, monkeypatch):
    root, write_list, calls, _ = env
    write_list([_row(1)])

    async def broken(client, model, row, city):
        raise RuntimeError("model down")

    monkeypatch.setattr(tfilter, "classify", broken)
    summary = asyncio.run(tfilter.run("dalat"))
    assert summary["llm_errors"] == 1 and not (root / "filter" / "1.json").exists()  # judged on the next run
    assert tfilter.kept_ids("dalat") == set()


def test_kept_ids_are_yes_and_unsure(env):
    root, write_list, _, answers = env
    write_list([_row(1), _row(2), _row(3)])
    answers["2"] = {"relevance": "no", "reason": "x"}
    answers["3"] = {"relevance": "unsure", "reason": "x"}
    asyncio.run(tfilter.run("dalat"))
    assert tfilter.kept_ids("dalat") == {"1", "3"}
