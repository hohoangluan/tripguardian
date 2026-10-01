import asyncio
import json

from tiktok_helpers import fake_profile

from corpus.crawl.tiktok import comments_crawl, crawl


def _write(data, video_id, *, verdict="yes", mp4=True, comments_complete=None):
    d = data / "videos" / video_id
    d.mkdir(parents=True, exist_ok=True)
    if mp4:
        (d / "video.mp4").write_bytes(b"mp4")
    (d / "video.json").write_text(json.dumps({
        "video_id": video_id, "video_url": f"https://www.tiktok.com/@a/video/{video_id}",
        "comments_complete": comments_complete, "comments": [],
        "places": [{"fid": "f1", "name": "p", "verdict": verdict}],
    }), encoding="utf-8")


def test_only_yes_verdicts_not_yet_downloaded_or_complete_are_queued(data, monkeypatch):
    _write(data, "1", verdict="yes", comments_complete=None)  # due
    _write(data, "2", verdict="no", comments_complete=None)  # place_verify said no: never worth it
    _write(data, "3", verdict="yes", comments_complete=True)  # already done
    _write(data, "4", verdict="yes", mp4=False, comments_complete=None)  # video not downloaded yet

    monkeypatch.setattr(comments_crawl, "load_config", lambda city: ("Đà Lạt", {"tiktok": {"tabs": 1}}))
    got = []

    async def fake_crawl_comments(todo, c, root, headed, profile, profile_name=None):
        got.extend(r["video_id"] for r in todo)

    monkeypatch.setattr(crawl, "crawl_comments", fake_crawl_comments)
    asyncio.run(comments_crawl.run("dalat", profile=fake_profile))
    assert got == ["1"]
