"""Gate for `detail` observations (docs/CORPUS.md §6): free text an Extractor copied from a source, plus the numbers,
months, days, hours and people it read in it. A detail stands only if every claim is in the quote; the quote is in the
source. Nothing here guesses a value the source did not state."""

import re

from ..ontology import UNKNOWN, Ontology, fold_text as norm

AUDIENCES = ("adult", "child", "senior", "all")
UNITS = ("person", "group", "vehicle", "item")
VERDICTS = ("good", "bad", "conditional")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
TIME = re.compile(r"^([01]\d|2[0-4]):([0-5]\d)$")
_DAY_WORDS = {"mon": r"thứ\s*(?:2|hai)|t2", "tue": r"thứ\s*(?:3|ba)|t3", "wed": r"thứ\s*(?:4|tư)|t4",
              "thu": r"thứ\s*(?:5|năm)|t5", "fri": r"thứ\s*(?:6|sáu)|t6", "sat": r"thứ\s*(?:7|bảy)|t7",
              "sun": r"chủ\s*nhật|cn"}


def amount_in(quote: str, amount: int) -> bool:
    digits = re.sub(r"(?<=\d)[.,\s](?=\d{3}(?!\d))", "", quote)
    if re.search(rf"(?<!\d){amount}(?!\d)", digits):
        return True
    return amount % 1000 == 0 and bool(re.search(rf"(?<!\d){amount // 1000}\s*(?:k|nghìn|ngàn|n)(?!\w)", quote, re.I))


def hour_in(quote: str, hhmm: str) -> bool:
    h = int(hhmm[:2])
    return any(re.search(rf"(?<!\d)0?{x}(?!\d)", quote) for x in {h, h - 12, h % 24} if x >= 0)


def month_in(quote: str, month: int) -> bool:
    return bool(re.search(rf"(?:tháng|thg|th)\s*0?{month}(?!\d)", norm(quote)))


def day_in(quote: str, day: str) -> bool:
    return day in _DAY_WORDS and bool(re.search(rf"(?<!\w)(?:{_DAY_WORDS[day]})(?!\w)", norm(quote)))


def _int(value) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def gate_detail(d: dict, source_text: str, ont: Ontology) -> tuple[dict | None, str | None]:
    """({"kind", "text", "quote", "time_of_day", "detail"}, None) when the detail stands, else (None, why it is dropped)."""
    kind = ont.details.get(str(d.get("kind") or ""))
    if kind is None:
        return None, "unknown_kind"
    quote, text = str(d.get("quote") or "").strip(), str(d.get("text") or "").strip()
    if not quote or norm(quote) not in norm(source_text):
        return None, "quote_not_in_source"
    if not text or norm(text) not in norm(quote):
        return None, "text_not_in_quote"

    amount, people = _int(d.get("amount_vnd")), _int(d.get("min_people"))
    months = sorted({_int(m) for m in d.get("months") or ()})
    days = [x for x in DAYS if x in (d.get("days") or ())]
    hour = str(d.get("hour") or "")
    hour = hour if TIME.match(hour) else ""
    who = ont.who(str(d.get("who") or "")) if str(d.get("who") or "").strip() else ""
    verdict = str(d.get("verdict") or "")
    have = {"amount_vnd": amount > 0, "days": bool(days), "hour": bool(hour), "who": bool(who), "verdict": verdict in VERDICTS}
    for need in kind.needs:
        if not have[need]:
            return None, f"missing_{need}"
    if amount and not amount_in(quote, amount):
        return None, "amount_not_in_quote"
    if people and not re.search(rf"(?<!\d){people}(?!\d)", quote):
        return None, "min_people_not_in_quote"
    if months and not all(1 <= m <= 12 and month_in(quote, m) for m in months):
        return None, "month_not_in_quote"
    if days and not all(day_in(quote, x) for x in days):
        return None, "day_not_in_quote"
    if hour and not hour_in(quote, hour):
        return None, "hour_not_in_quote"

    audience, unit = str(d.get("audience") or ""), str(d.get("unit") or "")
    tod = str(d.get("time_of_day") or UNKNOWN)
    detail = {"amount_vnd": amount or None, "audience": audience if audience in AUDIENCES else None,
              "unit": unit if unit in UNITS else None, "min_people": people or None, "months": months, "days": days,
              "hour": hour or None, "who": who or None, "verdict": verdict if verdict in VERDICTS else None}
    return {"kind": kind.id, "text": text, "quote": quote,
            "time_of_day": tod if ont.valid_context("time_of_day", tod) else UNKNOWN, "detail": detail}, None
