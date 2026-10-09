"""Video phase asr_alt: segments asr_check could not trust, heard again by a second ASR model.

A segment gets needs_alt when asr_check left it garbled or had to undo some of the model's edits. Its audio (same
start / end as the first ASR) goes through the second model (ASR role, .env ASR_ALT_MODEL); the text lands in
segment.alt_text, which changes the transcript's alt_hash, so the next asr_check run re-checks the video with both
hearings (ASR + ASR2). Writes only video.json: transcript.segments[].alt_text, transcript.alt_model. Each segment is
heard by the second model once (alt_text set, even when empty).
"""

import json
import tempfile
from pathlib import Path

from ...llm import asr as asr_model
from ..common.files import data_dir, log_error, write_json
from .asr import RATE, load_audio


def todo(root: Path) -> list[Path]:
    out = []
    for doc in sorted((root / "videos").glob("*/video.json")) if (root / "videos").exists() else []:
        if not (doc.parent / "video.mp4").exists():
            continue  # clip deleted after place_verify (clip_removed): nothing left to hear again
        if _pending(json.loads(doc.read_text(encoding="utf-8")).get("transcript") or {}):
            out.append(doc)
    return out


def hear_again(mp4: Path, segments: list[dict], model=asr_model) -> dict[int, str]:
    """segment index -> second-model text, for the segments that need it."""
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        load_audio(mp4, wav)
        audio = model.read(wav)
        return {i: model.transcribe_alt(audio[int(s["start_s"] * RATE):int(s["end_s"] * RATE)])
                for i, s in enumerate(segments) if s.get("needs_alt") and "alt_text" not in s}


def _pending(t: dict) -> bool:
    return any(s.get("needs_alt") and "alt_text" not in s for s in t.get("segments", []))


def run(city: str, shard: tuple[int, int] | None = None) -> dict:
    """shard = (i, n): this process's 1/n of the todo list, so n processes can each take a GPU (CUDA_VISIBLE_DEVICES)."""
    root = data_dir() / "tiktok"
    docs = todo(root)
    if shard:
        docs = [d for k, d in enumerate(docs) if k % shard[1] == shard[0]]
    print(f"asr_alt: {len(docs)} videos with segments to hear again")
    done = segs = 0
    for doc in docs:
        v = json.loads(doc.read_text(encoding="utf-8"))
        if not _pending(v.get("transcript") or {}):
            continue  # another asr_alt process (other GPU, other shard count) got here first
        try:
            heard = hear_again(doc.parent / "video.mp4", v["transcript"]["segments"])
        except Exception as e:
            log_error(root, v["video_id"], "asr_alt", e)
            continue
        v = json.loads(doc.read_text(encoding="utf-8"))  # read late: other phases may have written meanwhile
        t = v["transcript"]
        for i, text in heard.items():
            if i < len(t["segments"]):
                t["segments"][i]["alt_text"] = text
        t["alt_model"] = asr_model.alt_name()
        write_json(doc, v)
        done += 1
        segs += len(heard)
    print(f"asr_alt: {done}/{len(docs)} videos, {segs} segments heard again")
    return {"videos": len(docs), "done": done, "segments": segs}
