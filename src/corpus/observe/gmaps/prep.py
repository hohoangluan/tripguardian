"""Maps review helpers before the model: absolute dates, star ratings, which reviews go to the model, batching."""

import re
import unicodedata
from datetime import datetime, timedelta

MIN_CHARS = 15  # of the cleaned text: "Được rồi", "Ok" carry no observation
MIN_LETTERS = 8  # letters (any script) left after cleaning: "!!!!!!!!!!!!!!!!" or "10/10 ..." carry none
_DECOR = {"So", "Sk", "Cf", "Cs", "Co", "Cn"}  # emoji, pictographs, hearts, stars, joiners, selectors, unassigned
_TRUNCATED = re.compile(r"\s*…\s*$")  # Maps' own cut of a long review ("Xem thêm" not opened)
_RUNS = re.compile(r"([^\w\s])\1{2,}")  # "!!!!", "....." -> one mark
_SELECTORS = range(0xFE00, 0xFE10)  # variation selectors emoji leave behind (category Mn)
_LETTER = re.compile(r"[^\W\d_]")
BATCH_REVIEWS = 15
BATCH_CHARS = 12000  # keeps prompt + answer well under the 32k-token UIT limit (docs/LLM_PROVIDER.md)

_AGE = re.compile(r"(một|\d+) (phút|giờ|ngày|tuần|tháng|năm) trước")
_DAYS = {"phút": 0, "giờ": 0, "ngày": 1, "tuần": 7, "tháng": 30, "năm": 365}


def age_days(published_text: str | None) -> int | None:
    m = _AGE.search(published_text or "")
    if not m:
        return None
    return (1 if m.group(1) == "một" else int(m.group(1))) * _DAYS[m.group(2)]


def observed_at(published_text: str | None, fetched_at: str) -> str | None:
    days = age_days(published_text)
    if days is None:
        return None
    return (datetime.fromisoformat(fetched_at).date() - timedelta(days=days)).isoformat()


def stars(rating: str | None) -> int | None:
    m = re.match(r"\s*([1-5])", rating or "")
    return int(m.group(1)) if m else None


def clean_text(text: str | None) -> str:
    """What the model reads: NFC, no emoji / decorative symbols / joiners (they carry no fact and cost tokens), no
    trailing "…" Maps put on a cut review, runs of one punctuation mark shortened, one space between words."""
    t = unicodedata.normalize("NFC", text or "")
    t = "".join(ch for ch in t if unicodedata.category(ch) not in _DECOR and ord(ch) not in _SELECTORS
                and not 0x1F000 <= ord(ch) <= 0x1FAFF and ord(ch) != 0x20E3)
    t = _TRUNCATED.sub("", t)
    return " ".join(_RUNS.sub(chr(92) + "1", t).split())


def keep_for_llm(reviews: list[dict], bad_ids: set[str]) -> list[dict]:
    """Reviews worth a model call, as copies whose `text` is the cleaned text: dropped when flagged, a duplicate
    (author + cleaned text), shorter than MIN_CHARS or with fewer than MIN_LETTERS letters once cleaned."""
    seen, out = set(), []
    for r in reviews:
        text = clean_text(r.get("text"))
        key = (r.get("author_hash"), text)
        if (len(text) < MIN_CHARS or len(_LETTER.findall(text)) < MIN_LETTERS or r["review_id"] in bad_ids
                or key in seen):
            continue
        seen.add(key)
        out.append({**r, "text": text})
    return out


def batches(items: list[tuple[str, dict]], max_n: int = BATCH_REVIEWS,
            max_chars: int = BATCH_CHARS) -> list[list[tuple[str, dict]]]:
    out, cur, size = [], [], 0
    for ref, review in items:
        n = len(review["text"])
        if cur and (len(cur) >= max_n or size + n > max_chars):
            out.append(cur)
            cur, size = [], 0
        cur.append((ref, review))
        size += n
    if cur:
        out.append(cur)
    return out
