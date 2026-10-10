import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from speech import SpeechUnavailable
from test_dispatch import make
from test_harness_server import ORIGIN, FakeAccounts


def serve(speak):
    from harness.server import handler
    harness, _ = make()
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(harness, FakeAccounts(), ORIGIN, speak=speak))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def post():
    servers, spoken = [], []

    def go(speak, body, token="tok-a", origin=ORIGIN):
        server = serve(lambda text: (spoken.append(text), speak(text))[1])
        servers.append(server)
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        headers = {"Content-Type": "application/json", **({"Cookie": f"tg_session={token}"} if token else {}),
                   **({"Origin": origin} if origin else {})}
        conn.request("POST", "/api/harness/speech", json.dumps(body), headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, resp.getheader("Content-Type"), data

    yield go, spoken
    for s in servers:
        s.shutdown()
        s.server_close()


def test_speech_returns_audio_for_a_signed_in_same_origin_request(post):
    go, spoken = post
    code, ctype, data = go(lambda t: (b"RIFFaudio", "audio/wav"), {"text": "Xin chào"})
    assert (code, ctype, data) == (200, "audio/wav", b"RIFFaudio") and spoken == ["Xin chào"]


def test_speech_needs_sign_in_and_own_origin(post):
    go, spoken = post
    ok = lambda t: (b"x", "audio/wav")
    assert go(ok, {"text": "a"}, token=None)[0] == 401
    assert go(ok, {"text": "a"}, origin="http://evil.test")[0] == 403
    assert spoken == []


def test_speech_rejects_bad_text(post):
    go, _ = post
    def empty(text):
        raise ValueError("nothing to say")
    assert go(empty, {"text": " "})[0] == 400
    assert go(empty, {"text": 5})[0] == 400
    assert go(empty, {})[0] == 400


def test_speech_host_down_is_503_with_a_stable_code(post):
    go, _ = post
    def down(text):
        raise SpeechUnavailable("TTS not configured")
    code, ctype, data = go(down, {"text": "Xin chào"})
    assert code == 503 and json.loads(data)["error"] == "speech_unavailable"


# --- speech in: POST /api/harness/transcribe takes the recording as the raw body ---------------------------------------

@pytest.fixture
def upload():
    servers = []

    def go(listen, body=b"audio-bytes", token="tok-a", origin=ORIGIN, ctype="audio/webm"):
        from harness.server import handler
        harness, _ = make()
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler(harness, FakeAccounts(), ORIGIN, listen=listen))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        headers = {"Content-Type": ctype, **({"Cookie": f"tg_session={token}"} if token else {}),
                   **({"Origin": origin} if origin else {})}
        conn.request("POST", "/api/harness/transcribe", body, headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, json.loads(data)

    yield go
    for s in servers:
        s.shutdown()
        s.server_close()


def test_a_recording_comes_back_as_text(upload):
    heard = []
    code, out = upload(lambda audio: (heard.append(audio), "yên tĩnh hơn đi")[1])
    assert (code, out) == (200, {"text": "yên tĩnh hơn đi"}) and heard == [b"audio-bytes"]


def test_transcribe_needs_sign_in_and_own_origin(upload):
    ok = lambda audio: "x"
    assert upload(ok, token=None)[0] == 401
    assert upload(ok, origin="http://evil.test")[0] == 403


def test_a_guest_may_speak_too(upload):
    assert upload(lambda audio: "xin chào", token="tok-g")[0] == 200


def test_silence_or_bad_audio_is_400_and_a_down_model_is_503(upload):
    def silent(audio):
        raise ValueError("no speech heard")

    def down(audio):
        raise SpeechUnavailable("ASR failed")

    code, out = upload(silent)
    assert code == 400 and out["error"] == "no speech heard"
    code, out = upload(down)
    assert code == 503 and out["error"] == "speech_unavailable"


def test_an_oversized_recording_is_refused_before_it_is_read(upload, monkeypatch):
    from harness import server
    monkeypatch.setattr(server, "AUDIO_MAX_BYTES", 10)
    assert upload(lambda audio: "x", body=b"x" * 11)[0] == 413
    assert upload(lambda audio: "x", body=b"x" * 10)[0] == 200
