"""Video phase asr_check: an Extractor-role read of every transcript: keep, fix misheard words, or drop nonsense.

ASR turns background songs and noise into nonsense and mishears names. Per segment the model returns ok / fixed /
garbled / lyrics (a "fixed" that keeps under MIN_KEPT of the ASR words is a rewrite and counts as garbled); the raw ASR text stays in "text", the checked text goes to "checked_text" ("" when dropped), and
transcript.text joins the usable checked segments. Writes only video.json: transcript.segments[].{checked_text,
status}, transcript.text, transcript.check = {model, prompt_hash, quality, at}. A video with no speech gets
quality "no_speech" without a model call. Checked again when the transcript or the prompt changes.
Prompt: corpus.llm.ASR_CHECK.
"""

import asyncio
import collections
import difflib
import json

from ...llm import ASR_CHECK
from ..common.files import data_dir, load_config, log_error, now, write_json
from .place_filter import places_by_video

USABLE = ("ok", "fixed")
MIN_KEPT = 0.5  # a "fixed" segment must keep at least this share of the ASR words; below that it is a rewrite


def kept_share(raw: str, fixed: str) -> float:
    """How much of the raw ASR text a fix keeps (word-level match ratio, case-insensitive)."""
    return difflib.SequenceMatcher(None, raw.lower().split(), fixed.lower().split()).ratio()


def _client():
    return ASR_CHECK.role.client()


def segment_lines(segments: list[dict]) -> str:
    return "\n".join(f"{i}. [{s['start_s']:.1f}-{s['end_s']:.1f}s] {s['text']}" for i, s in enumerate(segments))


def apply(transcript: dict, answer: dict, model: str) -> dict:
    """The checked transcript; raises when the answer does not cover every segment exactly once, in order."""
    segs = transcript["segments"]
    got = answer["segments"]
    if [a["i"] for a in got] != list(range(len(segs))):
        raise ValueError(f"asr_check answered segments {[a['i'] for a in got]} for {len(segs)} segments")
    out = []
    for s, a in zip(segs, got):
        if a["status"] == "fixed" and kept_share(s["text"], a["text"]) < MIN_KEPT:
            a = {**a, "status": "garbled", "text": ""}  # the model rewrote it: invented text is worse than none
        text = a["text"].strip() if a["status"] in USABLE else ""
        if a["status"] in USABLE and not text:
            raise ValueError(f"segment {a['i']}: status {a['status']} with empty text")
        out.append({**s, "checked_text": text, "status": a["status"]})
    return {**transcript, "segments": out, "text": " ".join(s["checked_text"] for s in out if s["checked_text"]),
            "check": {"model": model, "prompt_hash": ASR_CHECK.prompt_hash, "quality": answer["quality"],
                      "transcript_at": transcript["at"], "at": now()}}


def needs_check(t: dict | None) -> bool:
    if not t:
        return False  # asr has not run yet
    c = t.get("check") or {}
    return c.get("prompt_hash") != ASR_CHECK.prompt_hash or c.get("transcript_at") != t["at"]


async def run(city: str) -> dict:
    name, _ = load_config(city)
    root = data_dir() / "tiktok"
    docs = [d for d in sorted((root / "videos").glob("*/video.json")) if (root / "videos").exists()
            and needs_check(json.loads(d.read_text(encoding="utf-8")).get("transcript"))]
    places = places_by_video(city)
    client, model = _client()
    sem = asyncio.Semaphore(ASR_CHECK.parallel)
    quality = collections.Counter()
    errors = [0]

    async def one(doc):
        v = json.loads(doc.read_text(encoding="utf-8"))
        t = v["transcript"]
        if not t["segments"]:
            checked = {**t, "text": "", "check": {"model": None, "prompt_hash": ASR_CHECK.prompt_hash,
                                                  "quality": "no_speech", "transcript_at": t["at"], "at": now()}}
        else:
            async with sem:
                try:
                    answer = await ASR_CHECK.ask(
                        client, model, city=name, desc=v.get("caption") or "",
                        hashtags=" ".join(f"#{h}" for h in v.get("hashtags") or []),
                        places=", ".join(p["name"] for p in places.get(v["video_id"], [])) or "unknown",
                        segments=segment_lines(t["segments"]))
                    checked = apply(t, answer, model)
                except Exception as e:
                    errors[0] += 1
                    log_error(root, v["video_id"], "asr_check", e)
                    return
        v = json.loads(doc.read_text(encoding="utf-8"))  # read late: keep what other phases wrote meanwhile
        if v.get("transcript", {}).get("at") != t["at"]:
            return  # transcribed again meanwhile; checked next run
        v["transcript"] = checked
        write_json(doc, v)
        quality[checked["check"]["quality"]] += 1

    await asyncio.gather(*(one(d) for d in docs))
    summary = {"at": now(), "videos": len(docs), "quality": dict(quality), "llm_errors": errors[0]}
    print(f"asr_check {city}: {json.dumps(summary, ensure_ascii=False)}")
    return summary
