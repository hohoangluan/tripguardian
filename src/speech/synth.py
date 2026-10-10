"""Speak a reply: the TTS role (an OpenAI-compatible /v1/audio/speech host, VieNeu-TTS) turns text into WAV.

Everything about the host is config (TTS_BASE_URL, TTS_MODEL, TTS_API_KEY, optional TTS_VOICE). A host that is not
deployed, down or busy raises SpeechUnavailable; the web then stays silent and shows the text it already has.
"""

import asyncio
import os
import re
import threading

from corpus.llm import TTS

MAX_CHARS = 500  # one reply is a few sentences; a longer text is cut at a sentence end
TIMEOUT_S = 20.0
_SLOTS = threading.BoundedSemaphore(TTS.own_parallel())  # the TTS host is small: beyond this, say "busy"

_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_URL = re.compile(r"https?://\S+")
_MARK = re.compile(r"[*_`#>~|]+|^\s*[-+•]\s+", re.MULTILINE)
_SENTENCE_END = re.compile(r"[.!?…](?=\s|$)")
_KEEP = re.compile(r"[^\w\s.,;:!?…'\"()%/+&-]", re.UNICODE)  # drops emoji and pictographs, keeps Vietnamese letters


class SpeechUnavailable(Exception):
    """The voice cannot be produced right now (not configured, host down or busy, empty audio)."""


def clean_for_speech(text: str) -> str:
    """Plain words only: no markdown, links or emoji; one line; at most MAX_CHARS, ending on a sentence."""
    text = _URL.sub(" ", _LINK.sub(r"\1", text))
    text = _KEEP.sub(" ", _MARK.sub(" ", text))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= MAX_CHARS:
        return text
    cut = text[:MAX_CHARS]
    ends = [m.end() for m in _SENTENCE_END.finditer(cut)]
    return cut[: ends[-1]] if ends else cut[: cut.rfind(" ")] or cut


async def _speak(client, model: str, text: str) -> bytes:
    voice = os.environ.get("TTS_VOICE", "").strip()
    args = {"model": model, "input": text, "response_format": "wav", **({"voice": voice} if voice else {})}
    resp = await asyncio.wait_for(client.audio.speech.create(**args), TIMEOUT_S)
    return resp.content


def synthesize(text: str, client: tuple | None = None) -> tuple[bytes, str]:
    """(audio bytes, mime type) for text. ValueError if nothing speakable is left; SpeechUnavailable otherwise.
    `client` = (async OpenAI-style client, model) replaces the role's own endpoint (tests)."""
    text = clean_for_speech(text)
    if not text:
        raise ValueError("nothing to say")
    if not _SLOTS.acquire(blocking=False):
        raise SpeechUnavailable("busy")
    try:
        if client is None:
            try:
                client = TTS.own_client()  # also loads .env
            except KeyError as exc:  # TTS_* not in .env: the host is not deployed
                raise SpeechUnavailable(f"TTS not configured: {exc}") from exc
            # An empty base URL makes the SDK fall back to api.openai.com: never send the text there.
            if not os.environ.get(TTS.base_url_env, "").strip() or not client[1].strip():
                raise SpeechUnavailable("TTS not configured: empty TTS_BASE_URL or TTS_MODEL")
        api, model = client
        try:
            audio = asyncio.run(_speak(api, model, text))
        except Exception as exc:
            raise SpeechUnavailable(f"TTS host failed: {type(exc).__name__}") from exc
        if not audio:
            raise SpeechUnavailable("TTS host returned no audio")
        return audio, "audio/wav"
    finally:
        _SLOTS.release()
