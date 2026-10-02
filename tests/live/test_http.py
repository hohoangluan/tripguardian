import io
import json
import urllib.error

import pytest

from live import http


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def test_get_json_returns_the_parsed_body_and_sends_the_user_agent(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["ua"] = req.get_header("User-agent")
        seen["timeout"] = timeout
        return _Resp(json.dumps({"code": "Ok"}).encode("utf-8"))

    monkeypatch.setattr(http.urllib.request, "urlopen", fake_urlopen)
    assert http.get_json("http://x/y?q=1", "TG/0.1", 3.5) == {"code": "Ok"}
    assert seen["url"] == "http://x/y?q=1"
    assert seen["ua"] == "TG/0.1"
    assert seen["timeout"] == 3.5


def test_a_network_error_becomes_unavailable(monkeypatch):
    def fake_urlopen(req, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(http.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(http.Unavailable) as e:
        http.get_json("http://127.0.0.1:5000/table/v1/driving/x?annotations=duration", "TG/0.1", 1)
    assert "?" not in str(e.value)  # the query string can hold user text, so it stays out of the message


def test_a_body_that_is_not_json_becomes_unavailable(monkeypatch):
    monkeypatch.setattr(http.urllib.request, "urlopen", lambda req, timeout: _Resp(b"<html>502</html>"))
    with pytest.raises(http.Unavailable):
        http.get_json("http://x/y", "TG/0.1", 1)


def test_a_timeout_becomes_unavailable(monkeypatch):
    def fake_urlopen(req, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr(http.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(http.Unavailable):
        http.get_json("http://x/y", "TG/0.1", 1)
