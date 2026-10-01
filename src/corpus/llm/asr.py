"""ASR role (docs/LLM_PROVIDER.md): local ChunkFormer on the GPU, Silero VAD in front of it.

The model id is config (.env ASR_MODEL), loaded once per process. Audio I/O goes through soundfile: torchaudio >= 2.9
needs torchcodec for files.
"""

import os
import re
from functools import cache

import soundfile as sf
import torch
from dotenv import load_dotenv

from ..crawl.common.files import ROOT

RATE = 16000
VAD_NAME = "silero-vad"
VAD_PAD_S = 0.2  # kept around each voiced stretch so first and last syllables are not cut
VAD_JOIN_S = 1.0  # stretches closer than this are transcribed together (one sentence, a breath apart)


def name() -> str:
    load_dotenv(ROOT / ".env")
    return os.environ["ASR_MODEL"]


@cache
def _asr():
    from chunkformer import ChunkFormerModel  # heavy import, only when a video is transcribed

    m = ChunkFormerModel.from_pretrained(name())
    return m.to("cuda") if torch.cuda.is_available() else m


@cache
def _vad():
    from silero_vad import load_silero_vad

    return load_silero_vad()


def read(path) -> torch.Tensor:
    audio, rate = sf.read(str(path), dtype="float32")
    if rate != RATE:
        raise ValueError(f"{path}: {rate} Hz, expected {RATE}")
    return torch.from_numpy(audio)


def write(path, audio: torch.Tensor) -> None:
    sf.write(str(path), audio.numpy(), RATE)


def join(stretches: list[tuple[float, float]], total_s: float) -> list[tuple[float, float]]:
    """Pad each voiced stretch and merge those that touch or sit closer than VAD_JOIN_S."""
    out: list[tuple[float, float]] = []
    for s, e in stretches:
        s, e = max(0.0, s - VAD_PAD_S), min(total_s, e + VAD_PAD_S)
        if out and s - out[-1][1] < VAD_JOIN_S:
            out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    return out


def speech(audio: torch.Tensor) -> list[tuple[float, float]]:
    """Voiced stretches in seconds; [] for music only or silence."""
    from silero_vad import get_speech_timestamps

    ts = get_speech_timestamps(audio, _vad(), sampling_rate=RATE, return_seconds=True)
    return join([(t["start"], t["end"]) for t in ts], len(audio) / RATE)


_TS = re.compile(r"(\d+):(\d+):(\d+)[:.](\d+)")


def seconds(ts: str) -> float:
    """ChunkFormer's "HH:MM:SS:mmm" -> seconds."""
    h, m, s, ms = _TS.fullmatch(ts.strip()).groups()
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def transcribe(path) -> list[dict]:
    """[{start_s, end_s, text}] for a 16 kHz mono wav."""
    out = _asr().endless_decode(audio_path=str(path), return_timestamps=True)
    return [{"start_s": seconds(r["start"]), "end_s": seconds(r["end"]), "text": r["decode"].strip()} for r in out]
