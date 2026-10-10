import asyncio

import pytest

from speech import MAX_CHARS, SpeechUnavailable, clean_for_speech, synthesize


class FakeSpeech:
    def __init__(self, audio=b"RIFFfake", fail=None):
        self.calls, self.audio, self.fail = [], audio, fail

    async def create(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise self.fail

        class Resp:
            content = self.audio

        return Resp()


class FakeClient:
    def __init__(self, **kw):
        self.audio = type("A", (), {"speech": FakeSpeech(**kw)})()


def test_clean_strips_markdown_links_and_emoji_and_keeps_words():
    out = clean_for_speech("**Đà Lạt** có [hồ Xuân Hương](https://x.vn/a) 🌲\n\n- quán A\n- quán B")
    assert "*" not in out and "http" not in out and "🌲" not in out and "[" not in out
    assert "Đà Lạt" in out and "hồ Xuân Hương" in out and "quán A" in out and "\n" not in out


def test_clean_clamps_at_a_sentence_boundary():
    text = ("Câu một khá dài để thử. " * 80).strip()
    out = clean_for_speech(text)
    assert len(out) <= MAX_CHARS and out.endswith(".")


def test_empty_text_is_not_spoken():
    with pytest.raises(ValueError):
        synthesize("  **  🌲 ", client=(FakeClient(), "m"))


def test_synthesize_calls_the_role_model_and_returns_audio(monkeypatch):
    monkeypatch.setenv("TTS_VOICE", "Mai Anh")
    client = FakeClient()
    audio, mime = synthesize("Xin chào bạn", client=(client, "vieneu-v3-turbo"))
    assert audio == b"RIFFfake" and mime == "audio/wav"
    call = client.audio.speech.calls[0]
    assert call["model"] == "vieneu-v3-turbo" and call["voice"] == "Mai Anh"
    assert call["input"] == "Xin chào bạn" and call["response_format"] == "wav"


def test_host_error_or_empty_audio_is_unavailable_not_a_crash():
    with pytest.raises(SpeechUnavailable):
        synthesize("Xin chào", client=(FakeClient(fail=ConnectionError("down")), "m"))
    with pytest.raises(SpeechUnavailable):
        synthesize("Xin chào", client=(FakeClient(audio=b""), "m"))


def test_unconfigured_role_is_unavailable(monkeypatch):
    for k in ("TTS_API_KEY", "TTS_BASE_URL", "TTS_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("corpus.llm.roles.load_dotenv", lambda *a, **k: None)
    with pytest.raises(SpeechUnavailable):
        synthesize("Xin chào")


def test_works_inside_a_running_loop_thread_safe():
    # The HTTP handler runs in worker threads; a fresh loop per call must not clash with an existing one.
    async def go():
        return await asyncio.to_thread(synthesize, "Xin chào", client=(FakeClient(), "m"))

    assert asyncio.run(go())[0] == b"RIFFfake"


def test_blank_base_url_never_falls_back_to_openai(monkeypatch):
    monkeypatch.setattr("corpus.llm.roles.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TTS_API_KEY", "k")
    monkeypatch.setenv("TTS_BASE_URL", "")
    monkeypatch.setenv("TTS_MODEL", "m")
    with pytest.raises(SpeechUnavailable):
        synthesize("Xin chào")
