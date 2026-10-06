"""Travellers' reports on a place: free text, one line per report in data/review/reports.jsonl.

Any information about a place can be reported. corpus.observe.reports reads what each report says with the Extractor
and only what several different people report becomes evidence (corpus.observe.reports.REPORTS_MIN): one person's
word never changes the corpus. `reporter` is the anonymous id the browser keeps; counting different people relies on
it, so it can be forged until the app has accounts.
"""

import hashlib
import json

from ..crawl.common.files import append_jsonl, data_dir, now

MAX_TEXT = 1000
REPORTER_LEN = (6, 64)


def _file():
    return data_dir() / "review" / "reports.jsonl"


def add(place_id: str, text: str, reporter: str) -> dict:
    """Appends one report and returns it; ValueError when a field is missing or out of bounds."""
    text = " ".join(text.split()) if isinstance(text, str) else ""
    reporter = reporter.strip() if isinstance(reporter, str) else ""
    if not isinstance(place_id, str) or not place_id.strip():
        raise ValueError("place_id is required")
    if not 1 <= len(text) <= MAX_TEXT:
        raise ValueError(f"text must be 1-{MAX_TEXT} characters")
    if not REPORTER_LEN[0] <= len(reporter) <= REPORTER_LEN[1]:
        raise ValueError(f"reporter must be {REPORTER_LEN[0]}-{REPORTER_LEN[1]} characters")
    at = now()
    rid = hashlib.sha1(f"{place_id}|{reporter}|{text}|{at}".encode()).hexdigest()[:16]
    rec = {"id": rid, "at": at, "place_id": place_id.strip(), "reporter": reporter, "text": text}
    append_jsonl(_file(), rec)
    return rec


def load() -> list[dict]:
    f = _file()
    if not f.exists():
        return []
    return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
