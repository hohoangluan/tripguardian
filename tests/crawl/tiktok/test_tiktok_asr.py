import asyncio
import json
import types

import pytest
import torch

from corpus.crawl.tiktok import asr, asr_check, place_verify
from corpus.llm import asr as asr_model


def test_seconds_reads_chunkformer_timestamps():
    assert asr_model.seconds("00:01:02:500") == 62.5


def test_vad_stretches_are_padded_and_close_ones_joined():
    assert asr_model.join([(1.0, 2.0), (2.5, 3.0), (6.0, 7.0)], total_s=7.1) == [(0.8, 3.2), (5.8, 7.1)]


def fake_model(voiced, said):
    """VAD returns voiced; ASR returns said[k] for the k-th stretch, timestamps relative to the stretch."""
    calls = []

    def transcribe(path):
        calls.append(path)
        return said[len(calls) - 1]

    return types.SimpleNamespace(
        name=lambda: "asr-test", VAD_NAME="vad-test", read=lambda wav: torch.zeros(16000 * 20),
        speech=lambda audio: voiced, write=lambda path, audio: None, transcribe=transcribe, calls=calls)


def test_transcribe_video_shifts_segments_to_the_video_clock(monkeypatch, tmp_path):
    monkeypatch.setattr(asr, "load_audio", lambda mp4, wav: None)
    m = fake_model([(2.0, 5.0), (10.0, 12.0)], [[{"start_s": 0.5, "end_s": 2.0, "text": "đi thác Datanla"}],
                                                 [{"start_s": 0.0, "end_s": 1.0, "text": " "}]])
    t = asr.transcribe_video(tmp_path / "video.mp4", model=m)
    assert t["segments"] == [{"start_s": 2.5, "end_s": 4.0, "text": "đi thác Datanla"}]  # blank text dropped
    assert t["total_s"] == 20.0 and t["speech_s"] == 5.0 and t["model"] == "asr-test" and t["vad_model"] == "vad-test"


def test_music_only_video_gets_an_empty_transcript_without_asr(monkeypatch, tmp_path):
    monkeypatch.setattr(asr, "load_audio", lambda mp4, wav: None)
    m = fake_model([], [])
    t = asr.transcribe_video(tmp_path / "video.mp4", model=m)
    assert t["segments"] == [] and t["speech_s"] == 0 and m.calls == []


@pytest.fixture
def videos(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    root = tmp_path / "tiktok"

    def add(vid, mp4=True, **extra):
        d = root / "videos" / vid
        d.mkdir(parents=True)
        (d / "video.json").write_text(json.dumps({"video_id": vid, "caption": "Máng trượt Datanla", "hashtags": ["dalat"],
                                                  "comments": [], **extra}, ensure_ascii=False), encoding="utf-8")
        if mp4:
            (d / "video.mp4").write_bytes(b"mp4")
        return d / "video.json"

    return root, add


def _read(doc):
    return json.loads(doc.read_text(encoding="utf-8"))


def test_asr_run_writes_transcript_next_to_caption_and_skips_done(videos, monkeypatch):
    root, add = videos
    doc = add("1")
    add("2", mp4=False)  # not downloaded yet
    monkeypatch.setattr(asr.asr_model, "name", lambda: "asr-test")
    seen = []

    def transcribe_video(mp4):
        seen.append(mp4.parent.name)
        return {"model": "asr-test", "at": "t1", "segments": [{"start_s": 0, "end_s": 1, "text": "xin chào"}]}

    monkeypatch.setattr(asr, "transcribe_video", transcribe_video)
    asr.run("dalat")
    asr.run("dalat")
    v = _read(doc)
    assert seen == ["1"] and v["caption"] == "Máng trượt Datanla" and v["transcript"]["segments"][0]["text"] == "xin chào"


def test_asr_failure_is_logged_and_retried(videos, monkeypatch):
    root, add = videos
    add("1")
    monkeypatch.setattr(asr.asr_model, "name", lambda: "asr-test")
    monkeypatch.setattr(asr, "transcribe_video", lambda mp4: (_ for _ in ()).throw(RuntimeError("cuda out of memory")))
    asr.run("dalat")
    assert "cuda out of memory" in (root / "errors.jsonl").read_text(encoding="utf-8")
    assert len(asr.todo(root, "asr-test")) == 1


SEGS = [{"start_s": 0.0, "end_s": 2.0, "text": "hôm nay đi đa tan la"},
        {"start_s": 3.0, "end_s": 5.0, "text": "la la la yeah baby"},
        {"start_s": 6.0, "end_s": 8.0, "text": "xg tr bm"}]
ANSWER = {"quality": "partial", "segments": [{"i": 0, "status": "fixed", "text": "hôm nay đi Datanla"},
                                             {"i": 1, "status": "lyrics", "text": ""},
                                             {"i": 2, "status": "garbled", "text": ""}]}


def test_apply_keeps_raw_text_and_joins_usable_checked_text():
    t = asr_check.apply({"at": "t1", "segments": SEGS}, ANSWER, "gemma-test")
    assert [s["text"] for s in t["segments"]] == [s["text"] for s in SEGS]  # raw ASR kept
    assert [s["status"] for s in t["segments"]] == ["fixed", "lyrics", "garbled"]
    assert t["text"] == "hôm nay đi Datanla" and t["check"]["quality"] == "partial" and t["check"]["transcript_at"] == "t1"


def test_a_fix_that_rewrites_the_segment_is_dropped():
    segs = [{"start_s": 1.9, "end_s": 4.4, "text": "mry o dayay red vui"}]
    answer = {"quality": "partial", "segments": [{"i": 0, "status": "fixed", "text": "mọi người đi chơi vui"}]}
    t = asr_check.apply({"at": "t1", "segments": segs}, answer, "gemma-test")
    assert t["segments"][0]["status"] == "garbled" and t["text"] == ""


def test_a_name_fix_is_kept():
    assert asr_check.kept_share("hôm nay mình đi thác đa tan la nha mọi người", "hôm nay mình đi thác Datanla nha mọi người") >= asr_check.MIN_KEPT


@pytest.mark.parametrize("bad", [
    {"quality": "good", "segments": [{"i": 0, "status": "ok", "text": "a"}]},  # a segment missing
    {"quality": "good", "segments": [{"i": i, "status": "ok", "text": ""} for i in range(3)]},  # ok but empty
])
def test_apply_rejects_answers_that_do_not_cover_every_segment(bad):
    with pytest.raises(ValueError):
        asr_check.apply({"at": "t1", "segments": SEGS}, bad, "gemma-test")


@pytest.fixture
def check_env(videos, monkeypatch):
    root, add = videos
    monkeypatch.setattr(asr_check, "load_config", lambda city: ("Đà Lạt", {}))
    monkeypatch.setattr(asr_check, "_client", lambda: (None, "gemma-test"))
    monkeypatch.setattr(asr_check, "places_by_video", lambda city: {"1": [{"fid": "f1", "name": "Thác Datanla"}]})
    calls = []

    async def ask(client, model, **fields):
        calls.append(fields)
        return ANSWER

    monkeypatch.setattr(asr_check, "ASR_CHECK", types.SimpleNamespace(
        ask=ask, prompt_hash=asr_check.ASR_CHECK.prompt_hash, parallel=2))
    return root, add, calls


def test_asr_check_run_checks_once_with_place_names_and_skips_no_speech(check_env):
    root, add, calls = check_env
    doc = add("1", transcript={"at": "t1", "segments": SEGS})
    quiet = add("2", transcript={"at": "t1", "segments": []})
    add("3")  # asr not run yet
    asyncio.run(asr_check.run("dalat"))
    asyncio.run(asr_check.run("dalat"))
    assert len(calls) == 1 and calls[0]["places"] == "Thác Datanla" and "0. [0.0-2.0s] hôm nay đi đa tan la" in calls[0]["segments"]
    assert _read(doc)["transcript"]["text"] == "hôm nay đi Datanla"
    assert _read(quiet)["transcript"]["check"]["quality"] == "no_speech"


def test_asr_check_runs_again_after_a_new_transcript(check_env):
    root, add, calls = check_env
    doc = add("1", transcript={"at": "t1", "segments": SEGS})
    asyncio.run(asr_check.run("dalat"))
    v = _read(doc)
    v["transcript"] = {"at": "t2", "segments": SEGS}
    doc.write_text(json.dumps(v), encoding="utf-8")
    asyncio.run(asr_check.run("dalat"))
    assert len(calls) == 2


@pytest.fixture
def verify_env(videos, monkeypatch):
    root, add = videos
    monkeypatch.setattr(place_verify, "load_config", lambda city: ("Đà Lạt", {}))
    monkeypatch.setattr(place_verify, "_client", lambda: (None, "gemma-test"))
    monkeypatch.setattr(place_verify, "frames", lambda mp4, total_s, out: [b"jpg"] * place_verify.FRAMES)
    places = {"1": [{"fid": "f1", "name": "Thác Datanla", "category": "Thác", "address": "Đèo Prenn"},
                    {"fid": "f2", "name": "Máng trượt Datanla", "category": None, "address": None}]}
    monkeypatch.setattr(place_verify, "places_by_video", lambda city: places)
    calls, answers = [], {}

    async def ask(client, model, images=(), **fields):
        calls.append((fields["name"], len(images), fields["transcript"]))
        return answers.get(fields["name"], {"verdict": "yes", "evidence": [{"source": "frame", "quote": "frame 1: sign"}],
                                            "reason": "sign shows the name"})

    monkeypatch.setattr(place_verify, "PLACE_VIDEO_VERIFY", types.SimpleNamespace(
        ask=ask, prompt_hash=place_verify.PLACE_VIDEO_VERIFY.prompt_hash, parallel=2))
    checked = {"at": "t1", "total_s": 20, "segments": [{"start_s": 0, "end_s": 2, "text": "đa tan la",
                                                         "checked_text": "Datanla", "status": "fixed"}],
               "text": "Datanla", "check": {"quality": "good", "transcript_at": "t1"}}
    return root, add, calls, answers, checked


def test_place_verify_writes_one_entry_per_matched_place_and_skips_done(verify_env):
    root, add, calls, answers, checked = verify_env
    doc = add("1", transcript=checked)
    answers["Máng trượt Datanla"] = {"verdict": "no", "evidence": [], "reason": "a waterfall, no slide shown"}
    summary = asyncio.run(place_verify.run("dalat"))
    asyncio.run(place_verify.run("dalat"))
    assert [c[0] for c in calls] == ["Thác Datanla", "Máng trượt Datanla"] and calls[0][1] == 4
    assert calls[0][2] == "[0s] Datanla"  # the checked text, not the raw ASR
    places = _read(doc)["places"]
    assert [(p["fid"], p["verdict"]) for p in places] == [("f1", "yes"), ("f2", "no")]
    assert places[0]["evidence"][0]["source"] == "frame" and summary["verdicts"] == {"yes": 1, "no": 1}


def test_place_verify_waits_for_the_asr_check(verify_env):
    root, add, calls, _, checked = verify_env
    doc = add("1", transcript={**checked, "check": None})
    summary = asyncio.run(place_verify.run("dalat"))
    assert calls == [] and summary["waiting_for_asr"] == 1 and "places" not in _read(doc)


def test_place_verify_model_error_keeps_the_pair_unjudged(verify_env, monkeypatch):
    root, add, calls, answers, checked = verify_env
    doc = add("1", transcript=checked)

    async def boom(client, model, images=(), **fields):
        raise RuntimeError("429")

    monkeypatch.setattr(place_verify.PLACE_VIDEO_VERIFY, "ask", boom)
    summary = asyncio.run(place_verify.run("dalat"))
    assert summary["llm_errors"] == 2 and "places" not in _read(doc)


def test_verify_prompt_takes_place_caption_and_transcript():
    from corpus.llm import PLACE_VIDEO_VERIFY

    msg = PLACE_VIDEO_VERIFY.render(city="Đà Lạt", frames=4, name="Thác Datanla", category="Thác", address="Đèo Prenn",
                                    others="Máng trượt Datanla (address unknown)",
                                    desc="Máng trượt", hashtags="#datanla", transcript="[0s] Datanla")
    assert all(s in msg for s in ("Thác Datanla", "Đèo Prenn", "Máng trượt", "#datanla", "[0s] Datanla", "4 frames",
                                  "Máng trượt Datanla (address unknown)"))


def test_verify_shows_the_other_places_of_the_same_video(verify_env, monkeypatch):
    root, add, calls, answers, checked = verify_env
    add("1", transcript=checked)
    seen = []

    async def ask(client, model, images=(), **fields):
        seen.append((fields["name"], fields["others"]))
        return {"verdict": "unsure", "evidence": [], "reason": "r"}

    monkeypatch.setattr(place_verify.PLACE_VIDEO_VERIFY, "ask", ask)
    asyncio.run(place_verify.run("dalat"))
    assert seen == [("Thác Datanla", "Máng trượt Datanla (address unknown)"), ("Máng trượt Datanla", "Thác Datanla (Đèo Prenn)")]
