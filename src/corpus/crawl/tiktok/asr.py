"""Video phase asr: speech in every saved video -> video.json "transcript" (next to caption, hashtags, comments).

Audio goes to 16 kHz mono (ffmpeg); VAD keeps only the stretches with a voice, so music-only videos get no text and
the ASR never hears long silences. Each stretch is transcribed on its own and its timestamps shifted back to the
video's clock. Writes only video.json of data/tiktok/videos/<video_id>/ (after video.mp4 exists):
transcript = {model, vad_model, at, total_s, speech_s, segments:[{start_s, end_s, text}]}. A video is transcribed
again when the ASR model changes or the field is missing (crawl rewrote video.json). Model: corpus.llm.asr (ASR role).
"""

import json
import subprocess
import tempfile
from pathlib import Path

from ...llm import asr as asr_model
from ..common.files import data_dir, log_error, now, write_json

RATE = 16000


def load_audio(mp4: Path, wav: Path) -> None:
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(mp4), "-vn", "-ac", "1",
                    "-ar", str(RATE), str(wav)], check=True)


def transcribe_video(mp4: Path, model=asr_model) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        load_audio(mp4, wav)
        audio = model.read(wav)
        voiced = model.speech(audio)  # VAD: voiced stretches, seconds
        segments = []
        for start_s, end_s in voiced:
            part = Path(tmp) / f"{start_s:.2f}.wav"
            model.write(part, audio[int(start_s * RATE):int(end_s * RATE)])
            segments += [{"start_s": round(start_s + s["start_s"], 2), "end_s": round(start_s + s["end_s"], 2),
                          "text": s["text"]} for s in model.transcribe(part) if s["text"].strip()]
    return {"model": model.name(), "vad_model": model.VAD_NAME, "at": now(), "total_s": round(len(audio) / RATE, 2),
            "speech_s": round(sum(e - s for s, e in voiced), 2), "segments": segments}


def todo(root: Path, model_name: str) -> list[Path]:
    out = []
    for doc in sorted((root / "videos").glob("*/video.json")) if (root / "videos").exists() else []:
        if not (doc.parent / "video.mp4").exists():
            continue
        t = json.loads(doc.read_text(encoding="utf-8")).get("transcript")
        if not t or t.get("model") != model_name:
            out.append(doc)
    return out


def run(city: str) -> dict:
    root = data_dir() / "tiktok"
    docs = todo(root, asr_model.name())
    print(f"asr: {len(docs)} videos to transcribe")
    done = 0
    for doc in docs:
        vid = doc.parent.name
        try:
            t = transcribe_video(doc.parent / "video.mp4")
            v = json.loads(doc.read_text(encoding="utf-8"))  # read late: other phases may have written meanwhile
            v["transcript"] = t
            v.pop("transcript_check", None)  # new text: the check runs again
            write_json(doc, v)
            done += 1
        except Exception as e:
            log_error(root, vid, "asr", e)
    print(f"asr: {done}/{len(docs)} done, the rest in errors.jsonl")
    return {"videos": len(docs), "done": done}
