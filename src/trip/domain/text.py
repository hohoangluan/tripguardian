"""Vietnamese text folding that keeps character positions, so a match in folded text maps back to the user's words."""

import re
import unicodedata


def fold(s: str) -> str:
    """Lowercase, strip diacritics, đ -> d. Same length as unicodedata.normalize('NFC', s)."""
    out = []
    for ch in unicodedata.normalize("NFC", s):
        c = ch.lower()
        out.append("d" if c == "đ" else unicodedata.normalize("NFD", c)[0])
    return "".join(out)


def squash(s: str) -> str:
    """fold, then anything that is not a letter or digit becomes one space."""
    return re.sub(r"[^a-z0-9]+", " ", fold(s)).strip()


def contains(haystack: str, needle: str) -> bool:
    """needle occurs in haystack as whole words, ignoring case, diacritics and punctuation."""
    n = squash(needle)
    return bool(n) and f" {n} " in f" {squash(haystack)} "


def language(text: str) -> str:
    """Choose the reply language from words, including Vietnamese typed without marks."""
    words = re.findall(r"\w+", fold(text))
    vi = {"di", "ngay", "dem", "voi", "gia", "dinh", "co", "con", "nho", "tuoi", "minh", "ban", "toi",
          "muon", "chuyen", "cua", "nguoi", "khong", "thich", "nhan", "lai", "gi", "roi", "nhe", "nha"}
    en = {"i", "we", "are", "want", "would", "like", "with", "from", "days", "day", "couples", "love",
          "the", "and", "night", "markets", "how", "will", "you", "your", "get", "around", "got", "it", "have"}
    return "en" if sum(w in en for w in words) > max(1, sum(w in vi for w in words)) else "vi"
