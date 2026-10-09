"""Relative dates ("mai", "thứ 4 tuần sau", "cuối tuần này", "3 ngày nữa") resolved against today.

Calendar arithmetic is code, not the agent: a small model gets weekdays wrong. Folding merges words the dates depend
on ("mốt" / "một", "tháng sau" / "tháng sáu", "thứ" / "thử"), so those are checked on the accented text.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta

DAY_NUMBER = {"mot": 1, "hai": 2, "ba": 3, "bon": 4, "nam": 5, "sau": 6, "bay": 7}
WEEKDAY = {"2": 0, "hai": 0, "3": 1, "ba": 1, "4": 2, "tu": 2, "5": 3, "nam": 3, "6": 4, "sau": 4, "7": 5, "bay": 5,
           "cn": 6, "chu nhat": 6}
WEEKDAY_VI = ("thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật")
# which week a weekday or a weekend falls in: 0 = the coming one, 1 = next week, 2 = the week after
WEEK = r"(?:\s+(?:cua\s+)?(tuan\s+sau\s+nua|tuan\s+sau|tuan\s+toi|tuan\s+nay|nay))?"
DAY = r"(?:thu\s*(2|3|4|5|6|7|hai|ba|tu|nam|sau|bay)|(chu\s+nhat|cn))"
# "lần thứ 2", "người thứ 3": an ordinal, not a weekday
ORDINAL = re.compile(r"\b(lan|nguoi|cai|con|chuyen|dua|hang)\s*$")
# "mai" alone is a date only where a day fits: at the start of a clause or after a travel verb or pronoun
MAI = re.compile(r"(?:^|[.,;!?]\s*|\b(?:di|len|toi|minh|em|anh|chi|khoi hanh|xuat phat|bat dau|tu)\s+)(mai)\b"
                 r"(?!\s+(?:mot|sau|kia))")


@dataclass(frozen=True)
class RelativeDate:
    field: str  # "start_date" or "month"
    value: date | int
    span: tuple[int, int]


def weekday_vi(d: date) -> str:
    return WEEKDAY_VI[d.weekday()]


def _weeks(word: str | None) -> int:
    if not word or word in ("nay", "tuan nay"):
        return 0
    return 2 if word.endswith("nua") else 1


def _weekday(today: date, idx: int, weeks: int) -> date:
    """The coming occurrence (today counts) when weeks is 0; otherwise that weekday in the week `weeks` ahead."""
    if weeks == 0:
        return today + timedelta(days=(idx - today.weekday()) % 7)
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=weeks)
    return monday + timedelta(days=idx)


def relative_dates(low: str, tone: str, today: date) -> list[RelativeDate]:
    """low: folded text; tone: the same text lowercased with its accents (same length)."""
    out: list[RelativeDate] = []

    def add(field: str, value, span: tuple[int, int]) -> None:
        if not any(a < span[1] and span[0] < b for *_, (a, b) in ((r.field, r.span) for r in out)):
            out.append(RelativeDate(field, value, span))

    # "tuần sau thứ 4" and "thứ 4 tuần sau"
    for m in re.finditer(r"\b(tuan\s+sau\s+nua|tuan\s+sau|tuan\s+toi|tuan\s+nay)\s+(?:vao\s+)?" + DAY + r"\b", low):
        if tone[m.start(2) if m[2] else m.start(3):].startswith(("thứ", "chủ", "cn")):
            add("start_date", _weekday(today, WEEKDAY[re.sub(r"\s+", " ", m[2] or m[3])], _weeks(m[1])), m.span())
    for m in re.finditer(r"\b" + DAY + r"\b" + WEEK, low):
        if not tone[m.start():].startswith(("thứ", "chủ", "cn")) or ORDINAL.search(low[:m.start()]):
            continue
        add("start_date", _weekday(today, WEEKDAY[re.sub(r"\s+", " ", m[1] or m[2])], _weeks(m[3])), m.span())
    for m in re.finditer(r"\bcuoi\s+tuan" + WEEK, low):
        weeks = _weeks(m[1])
        start = today if weeks == 0 and today.weekday() == 6 else _weekday(today, 5, weeks)
        add("start_date", start, m.span())
    for m in re.finditer(r"\bhom\s+nay\b", low):
        add("start_date", today, m.span())
    for m in re.finditer(r"\b(?:ngay|sang|trua|chieu|toi)\s+mai\b", low):
        if tone[m.end() - 3:m.end()] == "mai":
            add("start_date", today + timedelta(days=1), m.span())
    for m in MAI.finditer(low):
        if tone[m.start(1):m.end(1)] == "mai":
            add("start_date", today + timedelta(days=1), m.span(1))
    for m in re.finditer(r"(?<!mai )\b(ngày kia|mốt)\b", tone):
        add("start_date", today + timedelta(days=2), m.span())
    for m in re.finditer(r"\b(\d{1,2}|mot|hai|ba|bon|nam|sau|bay)\s+(ngay|tuan)\s+(?:nua|toi nua)\b", low):
        n = int(m[1]) if m[1].isdigit() else DAY_NUMBER[m[1]]
        add("start_date", today + timedelta(days=n * (7 if m[2] == "tuan" else 1)), m.span())
    for m in re.finditer(r"\btháng\s+(này|sau|tới)\b", tone):
        month = today.month if m[1] == "này" else today.month % 12 + 1
        add("month", month, m.span())
    return out
