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


@pytest.mark.parametrize("url", ["http://100.64.0.1/", "http://224.0.0.1/", "https://user:pass@example.test/",
                                  "http://example.test:22/", "http://[::ffff:127.0.0.1]/"])
def test_read_rejects_non_global_addresses_credentials_and_non_web_ports(tmp_path, monkeypatch, url):
    monkeypatch.setattr(web_socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 80))])
    web = make_web(tmp_path, lambda request: pytest.fail("blocked URL was fetched"))
    with pytest.raises(WebError):
        web.read(url)


def test_read_connects_to_the_checked_ip_with_original_tls_name(tmp_path, monkeypatch):
    monkeypatch.setattr(web_socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 443))])
    seen = []
    web = make_web(tmp_path, lambda request: (seen.append(request), httpx.Response(200, text="travel info"))[1])
    page = web.read("https://example.test/travel")
    assert seen[0].url.host == "93.184.216.34"
    assert seen[0].headers["host"] == "example.test"
    assert seen[0].extensions["sni_hostname"] == "example.test"
    assert page.url == "https://example.test/travel" and page.domain == "example.test"


def test_redirect_to_private_address_is_rejected_before_second_fetch(tmp_path, monkeypatch):
    monkeypatch.setattr(web_socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 80))])
    seen = []
    web = make_web(tmp_path, lambda request: (seen.append(request), httpx.Response(302, headers={
        "location": "http://169.254.169.254/latest/meta-data/"}))[1])
    with pytest.raises(WebError):
        web.read("http://example.test/")
    assert len(seen) == 1


def test_pinned_https_checks_the_original_certificate_hostname(tmp_path, monkeypatch):
    import shutil
    import ssl
    import subprocess
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    openssl = shutil.which("openssl")
    if not openssl:
        pytest.skip("openssl is required for this local TLS fixture")
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                    "-keyout", str(key), "-out", str(cert), "-subj", "/CN=example.test",
                    "-addext", "subjectAltName=DNS:example.test"], check=True, capture_output=True)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.headers["Host"].startswith("example.test")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"travel info")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(cert, key)
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    client = httpx.Client(verify=ssl.create_default_context(cafile=str(cert)), trust_env=False)
    web = Web("http://search.test", tmp_path / "cache", client=client, timeout_s=2)
    # Isolate TLS pinning from the separately tested public-IP validator, connecting only to this local fixture.
    monkeypatch.setattr(web, "_check_url", lambda url: "127.0.0.1")
    try:
        assert web.read(f"https://example.test:{server.server_port}/").text == "travel info"
        with pytest.raises(WebError, match="web request failed"):
            web.read(f"https://wrong.test:{server.server_port}/")
    finally:
        client.close()
        server.shutdown()
        server.server_close()
        worker.join()
