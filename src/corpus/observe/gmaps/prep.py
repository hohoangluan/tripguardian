"""Maps review helpers before the model: absolute dates, star ratings, which reviews go to the model, batching."""

import re
from datetime import datetime, timedelta

MIN_CHARS = 15  # "Được rồi", "Ok" carry no observation
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


def keep_for_llm(reviews: list[dict], bad_ids: set[str]) -> list[dict]:
    seen, out = set(), []
    for r in reviews:
        text = (r.get("text") or "").strip()
        key = (r.get("author_hash"), text)
        if len(text) < MIN_CHARS or r["review_id"] in bad_ids or key in seen:
            continue
        seen.add(key)
        out.append(r)
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
