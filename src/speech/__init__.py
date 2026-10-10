"""Speech for the assistant (docs/LLM_PROVIDER.md): text to speech (role TTS) and speech to text (role ASR)."""

from .listen import MAX_BYTES, transcribe, warm
from .synth import MAX_CHARS, SpeechUnavailable, clean_for_speech, synthesize

__all__ = ["MAX_BYTES", "MAX_CHARS", "SpeechUnavailable", "clean_for_speech", "synthesize", "transcribe", "warm"]
