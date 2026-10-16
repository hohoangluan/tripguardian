"""The web for the Trip agent (docs/TRIP_UNDERSTANDING.md §18): a self-hosted SearXNG and a page reader. What it returns
is data, never instructions and never evidence about a place. Both calls are cached on disk; private hosts are refused."""

from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import os
import re
import socket
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
import trafilatura
from pydantic import ValidationError
from agents import validate_public_url

from ..domain.state import Frozen


class WebHit(Frozen):
    url: str
    title: str
    domain: str
    snippet: str


class WebPage(Frozen):
    url: str
    title: str
    domain: str
    text: str


class WebError(Exception):
    """A web request failed or its response was unsafe or unusable."""


_USER_AGENT = "TripGuardian/1.0 (+travel planner; contact via site)"
_SPACE = re.compile(r"\s+")


def _squash(value: str) -> str:
    return _SPACE.sub(" ", value).strip()


def _domain(url: str) -> str:
    host = urlsplit(url).hostname or ""
    return host.lower().removeprefix("www.")


class Web:
    def __init__(self, base_url: str, cache_dir: Path, timeout_s: float = 6.0, ttl_days: int = 30,
                 max_bytes: int = 2_000_000, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.cache_dir = Path(cache_dir)
        self.timeout_s = timeout_s
        self.ttl_s = ttl_days * 86400
        self.max_bytes = max_bytes
        self.client = client or httpx.Client(timeout=timeout_s, headers={"User-Agent": _USER_AGENT},
                                             follow_redirects=False, trust_env=False)

    def _cache_path(self, kind: str, key: str) -> Path:
        digest = hashlib.sha256((kind + key).encode("utf-8")).hexdigest()[:24]
        return self.cache_dir / f"{digest}.json"

    def _cached(self, kind: str, key: str):
        try:
            item = json.loads(self._cache_path(kind, key).read_text(encoding="utf-8"))
            age = time.time() - float(item["fetched_at"])
            if 0 <= age <= self.ttl_s:
                return item["value"]
        except (OSError, ValueError, TypeError, KeyError):
            pass
        return None

    def _store(self, kind: str, key: str, value) -> None:
        path = self._cache_path(kind, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + f".{os.getpid()}.{time.time_ns()}.tmp")
        try:
            temp.write_text(json.dumps({"fetched_at": time.time(), "value": value}, ensure_ascii=False),
                            encoding="utf-8")
            os.replace(temp, path)
        finally:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass

    def _get(self, url: str, params: dict | None = None, *, check_host: bool = False,
             limit: int | None = None) -> tuple[str, str, str, bytes]:
        """-> (final url, content type, encoding, body read up to `limit` bytes). Redirects are followed by hand (at
        most 3), each target checked again when check_host."""
        current = url
        deadline = time.monotonic() + self.timeout_s
        for redirects in range(4):
            headers = {"User-Agent": _USER_AGENT}
            extensions = {}
            target = current
            if check_host:
                address = self._check_url(current)
                parsed = urlsplit(current)
                original = httpx.URL(current)
                target = original.copy_with(host=address)
                headers.update({"Host": original.netloc.decode("ascii"), "Connection": "close"})
                extensions["sni_hostname"] = parsed.hostname
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WebError("web request timed out")
            try:
                with self.client.stream("GET", target, params=params if redirects == 0 else None,
                                        timeout=remaining, headers=headers, extensions=extensions,
                                        follow_redirects=False) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            raise WebError("redirect without a location")
                        current = urljoin(current, location)
                        continue
                    response.raise_for_status()
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic() >= deadline:
                            raise WebError("web request timed out")
                        room = (limit or self.max_bytes) - len(body)
                        body.extend(chunk[:room])
                        if len(body) >= (limit or self.max_bytes):
                            break
                    return (current if check_host else str(response.url), response.headers.get("content-type", ""),
                            response.encoding or "utf-8", bytes(body))
            except httpx.TimeoutException as exc:
                raise WebError("web request timed out") from exc
            except httpx.HTTPError as exc:
                raise WebError("web request failed") from exc
        raise WebError("too many redirects")

    def search(self, query: str, k: int = 5) -> list[WebHit]:
        query = query.strip()
        if not 1 <= len(query) <= 200:
            raise ValueError("query must contain 1 to 200 characters")
        key = json.dumps([query, k], ensure_ascii=False)
        cached = self._cached("search", key)
        if cached is not None:
            try:
                return [WebHit.model_validate(row) for row in cached]
            except (ValidationError, TypeError):
                pass
        _, _, _, body = self._get(self.base_url + "/search", {
            "q": query, "format": "json", "language": "vi-VN", "safesearch": 1,
        })
        try:
            payload = json.loads(body)
        except ValueError as exc:
            raise WebError("invalid search response") from exc
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            raise WebError("invalid search response")
        hits, seen_urls, seen_domains = [], set(), set()
        for result in results:
            if not isinstance(result, dict):
                continue
            url = result.get("url")
            if not isinstance(url, str) or urlsplit(url).scheme.lower() not in ("http", "https") or not urlsplit(url).hostname:
                continue
            domain = _domain(url)
            if url in seen_urls or domain in seen_domains:
                continue
            seen_urls.add(url)
            seen_domains.add(domain)
            hits.append(WebHit(url=url, title=_squash(str(result.get("title") or "")), domain=domain,
                               snippet=_squash(str(result.get("content") or result.get("snippet") or ""))[:300]))
            if len(hits) >= max(0, k):
                break
        self._store("search", key, [hit.model_dump() for hit in hits])
        return hits

    def _check_url(self, url: str) -> str:
        try:
            parsed = validate_public_url(url)
        except ValueError as exc:
            raise WebError("blocked URL") from exc
        host = parsed.hostname.rstrip(".").lower()
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal is not None:
            return str(literal)
        try:
            records = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        except (OSError, ValueError) as exc:
            raise WebError("could not resolve URL host") from exc
        addresses = []
        for record in records:
            try:
                address = ipaddress.ip_address(record[4][0].split("%", 1)[0])
            except ValueError:
                raise WebError("invalid resolved address")
            if not address.is_global or address.is_multicast:
                raise WebError("blocked URL")
            addresses.append(str(address))
        if not addresses:
            raise WebError("could not resolve URL host")
        return addresses[0]

    def read(self, url: str, max_chars: int = 6000) -> WebPage:
        self._check_url(url)
        key = json.dumps([url, max_chars, self.max_bytes], ensure_ascii=False)
        cached = self._cached("read", key)
        if cached is not None:
            try:
                return WebPage.model_validate(cached)
            except (ValidationError, TypeError):
                pass
        final, ctype, encoding, body = self._get(url, check_host=True)
        media_type = ctype.split(";", 1)[0].strip().lower()
        if media_type not in ("text/html", "text/plain"):
            raise WebError("unsupported content type")
        content = body.decode(encoding, errors="replace")
        title = ""
        if media_type == "text/html":
            extracted = trafilatura.extract(content, include_comments=False, include_tables=False)
            metadata = trafilatura.extract_metadata(content)
            title = _squash(metadata.title or "") if metadata else ""
            if not title:
                match = re.search(r"<title\b[^>]*>(.*?)</title\s*>", content, flags=re.I | re.S)
                if match:
                    title = _squash(html.unescape(re.sub(r"<[^>]+>", " ", match.group(1))))
            text = _squash(extracted or "")
        else:
            text = _squash(content)
        if not text:
            raise WebError("empty page")
        page = WebPage(url=final, title=title, domain=_domain(final), text=text[:max_chars])
        self._store("read", key, page.model_dump())
        return page
