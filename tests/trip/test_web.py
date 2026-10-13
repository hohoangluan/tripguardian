"""infrastructure.web: SearXNG search, page reading, cache, refused hosts (no network)."""

import httpx
import pytest

from trip.infrastructure import web as web_mod
from trip.infrastructure.web import Web, WebError

web_socket = web_mod.socket


def make_web(tmp_path, handler, **kwargs):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return Web("http://search.test", tmp_path, client=client, **kwargs)


def test_search_parses_dedupes_domain_and_limit(tmp_path):
    payload = {"results": [{"url": "https://www.one.test/a", "title": " A ", "content": "  one\n two "},
                            {"url": "https://one.test/b", "title": "duplicate domain"},
                            {"url": "https://two.test/x", "title": "Two"},
                            {"url": "https://three.test/x", "title": "Three"}]}
    web = make_web(tmp_path, lambda request: httpx.Response(200, json=payload))
    hits = web.search(" retro ", k=2)
    assert [hit.domain for hit in hits] == ["one.test", "two.test"]
    assert hits[0].snippet == "one two"


def test_empty_query_raises(tmp_path):
    web = make_web(tmp_path, lambda request: httpx.Response(200, json={"results": []}))
    with pytest.raises(ValueError):
        web.search("  ")


def test_search_cache_hit_avoids_second_request(tmp_path):
    calls = []
    web = make_web(tmp_path, lambda request: (calls.append(request), httpx.Response(200, json={"results": []}))[1])
    web.search("retro")
    web.search("retro")
    assert len(calls) == 1


def test_expired_cache_refetches(tmp_path):
    calls = []
    web = make_web(tmp_path, lambda request: (calls.append(request), httpx.Response(200, json={"results": []}))[1], ttl_days=0)
    web.search("retro")
    web.search("retro")
    assert len(calls) == 2


def test_read_extracts_html(tmp_path, monkeypatch):
    monkeypatch.setattr(web_socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 80))])
    body = "<html><head><title>Example</title></head><body><article><p>Useful main page text.</p></article></body></html>"
    web = make_web(tmp_path, lambda request: httpx.Response(200, text=body, headers={"content-type": "text/html"}))
    page = web.read("http://example.test/page")
    assert "Useful main page text." in page.text
    assert page.title


@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "http://localhost/x", "ftp://a/b"])
def test_read_refuses_unsafe_urls(tmp_path, url):
    web = make_web(tmp_path, lambda request: httpx.Response(200))
    with pytest.raises(WebError):
        web.read(url)


def test_read_refuses_private_dns_resolution(tmp_path, monkeypatch):
    monkeypatch.setattr(web_socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("10.0.0.1", 80))])
    web = make_web(tmp_path, lambda request: httpx.Response(200))
    with pytest.raises(WebError):
        web.read("http://private.test/x")


def test_read_truncates_oversized_stream(tmp_path, monkeypatch):
    monkeypatch.setattr(web_socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 80))])
    web = make_web(tmp_path, lambda request: httpx.Response(200, headers={"content-type": "text/plain"},
                                                            stream=httpx.ByteStream(b"a" * 10000)), max_bytes=10)
    page = web.read("http://example.test/", max_chars=100)
    assert len(page.text) == 10


def test_non_html_content_type_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(web_socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 80))])
    web = make_web(tmp_path, lambda request: httpx.Response(200, text="x", headers={"content-type": "application/json"}))
    with pytest.raises(WebError):
        web.read("http://example.test/")


def test_timeout_raises_and_failed_call_is_not_cached(tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, json={"results": []})
    web = make_web(tmp_path, handler)
    with pytest.raises(WebError):
        web.search("retro")
    assert web.search("retro") == []
    assert len(calls) == 2
