"""Speech in: a recording from the browser becomes 16 kHz mono wav, and the ASR role (ChunkFormer) turns it into text."""

import io
import math
import struct
import wave

import pytest

from speech import SpeechUnavailable, transcribe


def tone(seconds=1.0, rate=44100) -> bytes:
    """A real wav file (44.1 kHz stereo), what ffmpeg has to bring down to 16 kHz mono."""
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(struct.pack("<hh", s, s) for s in (int(8000 * math.sin(i / 20)) for i in range(int(rate * seconds))))
        w.writeframes(frames)
    return out.getvalue()


def test_the_recording_reaches_the_asr_as_16k_mono_wav_and_its_text_is_returned():
    seen = {}

    def asr(path):
        with wave.open(path) as w:
            seen["fmt"] = (w.getframerate(), w.getnchannels())
        return "  mình muốn   đi chỗ yên tĩnh "

    assert transcribe(tone(), asr=asr) == "mình muốn đi chỗ yên tĩnh"
    assert seen["fmt"] == (16000, 1)


def test_nothing_heard_is_a_refusal_not_an_empty_message():
    with pytest.raises(ValueError, match="no speech"):
        transcribe(tone(), asr=lambda path: "   ")


def test_empty_oversized_or_unreadable_audio_is_refused():
    with pytest.raises(ValueError):
        transcribe(b"", asr=lambda p: "x")
    with pytest.raises(ValueError, match="too large"):
        transcribe(b"x" * (4 * 1024 * 1024 + 1), asr=lambda p: "x")
    with pytest.raises(ValueError, match="could not be read"):
        transcribe(b"this is not audio at all", asr=lambda p: "x")


def test_a_model_that_cannot_run_is_unavailable_not_a_server_error():
    def broken(path):
        raise RuntimeError("CUDA out of memory")

    with pytest.raises(SpeechUnavailable):
        transcribe(tone(), asr=broken)


def test_the_asr_is_not_loaded_just_by_importing_speech():
    import sys
    assert "chunkformer" not in sys.modules
