"""Speech in: a recording from the browser becomes text through the ASR role (local ChunkFormer, src/corpus/llm/asr.py).

ffmpeg brings whatever the browser recorded (webm / ogg / mp4) to 16 kHz mono wav. The model is loaded on the first
call (or by warm()), not at import. A silent clip is refused (ValueError); a model that cannot run is SpeechUnavailable.
"""

import subprocess
import tempfile
import threading

from .synth import SpeechUnavailable

MAX_BYTES = 4 * 1024 * 1024
MAX_SECONDS = 30  # a spoken sentence or two; longer audio is cut here
FFMPEG_TIMEOUT_S = 20
_SLOTS = threading.BoundedSemaphore(2)  # the model runs on a shared GPU: beyond this, say "busy"


def _wav16k(audio: bytes) -> bytes:
    try:
        done = subprocess.run(["ffmpeg", "-v", "error", "-i", "pipe:0", "-t", str(MAX_SECONDS), "-ac", "1", "-ar", "16000",
                               "-f", "wav", "pipe:1"], input=audio, capture_output=True, timeout=FFMPEG_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SpeechUnavailable(f"ffmpeg failed: {type(exc).__name__}") from exc
    if done.returncode or not done.stdout:
        raise ValueError("audio could not be read")
    return done.stdout


def _asr(path: str) -> str:
    from corpus.llm import transcribe_file  # heavy (torch, ChunkFormer): only when someone speaks

    return transcribe_file(path)


def warm() -> None:
    """Load the ASR model now, so the first user does not wait for it. Failures are left for the first real call."""
    try:
        from corpus.llm import asr

        asr._asr()
    except Exception as exc:  # no GPU, missing model id, not installed: speech in stays off
        print(f"speech in not warmed: {type(exc).__name__}: {exc}")


def transcribe(audio: bytes, asr=None) -> str:
    """Text of one recording. ValueError: empty, too large, unreadable or silent; SpeechUnavailable: busy or the model
    cannot run. `asr(path) -> str` replaces the model (tests)."""
    if not audio:
        raise ValueError("no audio")
    if len(audio) > MAX_BYTES:
        raise ValueError("audio too large")
    if not _SLOTS.acquire(blocking=False):
        raise SpeechUnavailable("busy")
    try:
        wav = _wav16k(audio)
        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
            f.write(wav)
            f.flush()
            try:
                text = (asr or _asr)(f.name)
            except Exception as exc:
                raise SpeechUnavailable(f"ASR failed: {type(exc).__name__}") from exc
    finally:
        _SLOTS.release()
    text = " ".join(text.split())
    if not text:
        raise ValueError("no speech heard")
    return text
