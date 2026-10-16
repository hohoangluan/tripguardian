"""Deterministic input screening. Unknown language is reviewed; travel keywords never grant blanket access."""

import base64
import binascii
import ipaddress
import re
import unicodedata
from typing import Literal
from urllib.parse import SplitResult, unquote, urlsplit

Screen = Literal["travel", "off_topic", "attack", "invalid", "review"]

_ATTACK = re.compile(
    r"(?:ignore|disregard|override|forget|bo qua|ghi de).{0,60}(?:instructions?|system|prompt|huong dan|he thong)"
    r"|(?:reveal|print|show|expose|in ra|tiet lo|hien thi).{0,60}(?:system prompt|api.?key|secret|mat khau|khoa api)"
    r"|(?:you are now|act as|pretend to be).{0,40}(?:developer|unrestricted|system|dan\b)"
    r"|(?:developer mode|jailbreak|<\|im_start\|>|\[/?inst\]|<\|(?:system|developer)\|>)"
    r"|(?:curl|wget)\b[^\n]{0,300}\|\s*(?:ba)?sh\b"
    r"|\brm\s+-[a-z]*r[a-z]*f\b|\bpowershell\b.{0,40}(?:-enc|iex)"
    r"|\b(?:drop|truncate)\s+(?:table|database)\b|\bunion\s+(?:all\s+)?select\b"
    r"|['\"]\s*(?:or|and)\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+"
    r"|\b(?:__import__|eval|exec)\s*\(|\b(?:os|subprocess)\.(?:system|popen|run)\s*\("
    r"|<\s*(?:script|iframe)\b|\bon(?:error|load)\s*=|javascript\s*:"
    r"|/(?:etc/passwd|proc/self|root/\.ssh)\b|\b(?:read|cat|doc|in ra)\b.{0,30}\.env\b",
    re.I | re.S,
)
_OFF_TOPIC = re.compile(r"\b(?:giai|lam|solve|do)\b.{0,30}(?:bai tap|homework|assignment)"
                        r"|\b(?:viet|write|generate)\s+(?:code|python|javascript|essay|bai luan)\b", re.I | re.S)
_SIMPLE = re.compile(
    r"(?:(?:toi|minh|muon|di|khong)\s+){0,3}"
    r"(?:\d{1,2}(?:\s*(?:ngay|dem|nguoi|ban))?|thang\s+\d{1,2}|\d{1,2}/\d{1,2}(?:/\d{4})?"
    r"|da lat|it dong|dong vua|song cham|thu tha|san may|ngam canh|an uong|tiet kiem"
    r"|xe may|motorbike|o to|xe hoi|car|xe khach|may bay"
    r"|(?:di )?voi (?:nguoi yeu|ban be|bo me|gia dinh)|mot minh)"
    r"(?: thoi| nhe| a)?",
)
_SHORT = {"co", "khong", "bo qua", "chua chac", "khong biet", "cam on", "xin chao", "chao", "dung", "ok", "vang"}


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold()).replace("đ", "d")
    return " ".join("".join(c for c in normalized if not unicodedata.combining(c)).split())


def validate_public_url(url: str) -> SplitResult:
    """Check syntax/literal hosts here; DNS is checked and pinned separately at fetch time."""
    if len(url) > 2048 or any(c.isspace() or unicodedata.category(c) in {"Cc", "Cf"} for c in url):
        raise ValueError("blocked URL")
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname or parsed.username is not None \
            or parsed.password is not None or parsed.port not in {None, 80, 443} or "\\" in url:
        raise ValueError("blocked URL")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")) or "." not in host and ":" not in host:
        raise ValueError("blocked URL")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global or address.is_multicast:
            raise ValueError("blocked URL")
    return parsed


def screen_input(text: str, context: str = "", max_chars: int = 4000) -> Screen:
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= max_chars:
        return "invalid"
    if any(unicodedata.category(c) in {"Cc", "Cf"} and c not in "\n\r\t" for c in text):
        return "invalid"
    normalized = _fold(unquote(text))
    if _ATTACK.search(normalized):
        return "attack"
    # Decode bounded tokens for inspection only; decoded bytes are never executed or fetched.
    for token in re.findall(r"(?<![\w+/])[A-Za-z0-9+/]{40,}={0,2}(?![\w+/])", text):
        try:
            decoded = base64.b64decode(token, validate=True).decode("utf-8")
        except (ValueError, UnicodeError, binascii.Error):
            continue
        if _ATTACK.search(_fold(decoded)):
            return "attack"
    try:
        for url in re.findall(r"(?:https?://|file:|javascript:|data:|ftp://)[^\s<>]+", text, re.I):
            validate_public_url(url.rstrip(".,;!?)]}"))
    except ValueError:
        return "invalid"
    if _OFF_TOPIC.search(normalized):
        return "off_topic"
    if context and normalized.strip(".!?") in _SHORT:
        return "travel"
    parts = [p.strip(" .!?") for p in re.split(r"[,;\n]", _fold(text))]
    if all(_SIMPLE.fullmatch(p) for p in parts):
        return "travel"
    return "review"
