"""Relative dates ("mai", "thứ 4 tuần sau", "cuối tuần này", "3 ngày nữa") resolved against today.

Calendar arithmetic is code, not the agent: a small model gets weekdays wrong. Folding merges words the dates depend
on ("mốt" / "một", "tháng sau" / "tháng sáu", "thứ" / "thử"), so those are checked on the accented text.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta

from .text import fold, squash

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

    for m in re.finditer(r"\b(tet duong lich|le\s+30/4)\b", low):
        day, month = (1, 1) if m[1] == "tet duong lich" else (30, 4)
        add("start_date", day_month(day, month, today), m.span())
    # "tuần sau thứ 4" and "thứ 4 tuần sau"
    for m in re.finditer(r"\b(tuan\s+sau\s+nua|tuan\s+sau|tuan\s+toi|tuan\s+nay)\s+(?:vao\s+)?" + DAY + r"\b", low):
        if tone[m.start(2) if m[2] else m.start(3):].startswith(("thứ", "chủ", "cn")):
            add("start_date", _weekday(today, WEEKDAY[re.sub(r"\s+", " ", m[2] or m[3])], _weeks(m[1])), m.span())
    for m in re.finditer(r"\b" + DAY + r"\b" + WEEK, low):
        if not tone[m.start():].startswith(("thứ", "chủ", "cn")) or ORDINAL.search(low[:m.start()]):
            continue
        add("start_date", _weekday(today, WEEKDAY[re.sub(r"\s+", " ", m[1] or m[2])], _weeks(m[3])), m.span())
    for m in re.finditer(r"\bcuoi\s+tuan(?:\s+(?:cua\s+)?(sau\s+nua|sau|toi|nay))?\b", low):
        weeks = _weeks(m[1])
        start = today if weeks == 0 and today.weekday() == 6 else _weekday(today, 5, weeks)
        add("start_date", start, m.span())
    for m in re.finditer(r"\bhom\s+nay\b", low):
        if m.start() == 0 or re.search(r"\b(di|len|toi|khoi hanh|xuat phat)\b", low[:m.start()]):
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
    # English: "leaving in a week" ("a" may already be dropped as filler)
    for m in re.finditer(r"\bin\s+(?:(a|one|\d{1,2})\s+)?(day|week)s?\b", low):
        n = int(m[1]) if m[1] and m[1].isdigit() else 1
        add("start_date", today + timedelta(days=n * (7 if m[2] == "week" else 1)), m.span())
    for m in re.finditer(r"\btháng\s+(này|sau|tới)\b", tone):
        month = today.month if m[1] == "này" else today.month % 12 + 1
        add("month", month, m.span())
    return out


# filler the user adds around a date ("ừm mai nhé"): dropped before the whole-expression check
FILLER = {"um", "nhe", "nha", "di", "a", "ah", "thi", "sao", "ne", "vay"}
# how a weekday is written after folding, per Monday=0 .. Sunday=6 (WEEKDAY_VI order)
WEEKDAY_WORD = {0: r"thu\s*(?:2|hai)", 1: r"thu\s*(?:3|ba)", 2: r"thu\s*(?:4|tu)", 3: r"thu\s*(?:5|nam)",
                4: r"thu\s*(?:6|sau)", 5: r"thu\s*(?:7|bay)", 6: r"chu\s+nhat|cn"}


DAY_MONTH = re.compile(r"(?:(?:mung|ngay) )?(\d{1,2})(?:\s*[/\-.]\s*|\s+thang\s+)(\d{1,2})"
                       r"(?:(?:\s*[/\-.]\s*|\s+(?:nam\s+)?)(\d{4}))?")
# A calendar date written out inside a folded message: "17/10", "17/10/2026", "ngày 17 tháng 10 năm 2026".
# Not the end of a range ("10 đến 20/10" is read by RANGE) and not part of a longer number.
FULL_DATE = re.compile(r"(?<![\d/])(?:(?:mung|ngay)\s+)?(\d{1,2})(?:\s*/\s*|\s+thang\s+)(\d{1,2})"
                       r"(?:(?:\s*/\s*|\s+(?:nam\s+)?)(\d{4}))?(?![\d/])(?!\s*(?:ngay|n)\b)")
# "17-20/10", "17 đến 20 tháng 10": the days of one month
RANGE = re.compile(r"(?<![\d/])(\d{1,2})\s*(?:-|–|den|toi)\s*(\d{1,2})(?:\s*/\s*|\s+thang\s+)(\d{1,2})"
                   r"(?:(?:\s*/\s*|\s+(?:nam\s+)?)(\d{4}))?(?![\d/])")
# what joins a start and an end date: "từ 17/10 đến 20/10", "đi 17/10 về 20/10"
UNTIL = re.compile(r"\b(den|toi|ve|cho den)\b|[-–]")


def day_month(day: int, month: int, today: date, year: int | None = None) -> date:
    """A day and month: with no year, the next time it comes (the year after when it has passed). ValueError for 30/2."""
    d = date(year or today.year, month, day)
    if year is None and d < today:
        d = date(d.year + 1, month, day)
    return d


def exact_date(expression: str, today: date) -> date | None:
    """The date of the whole expression, or None unless it is exactly one known pattern. A part of a longer phrase
    ("hai mươi mốt ngày nữa" holds "mốt") is not the date: the caller then asks the model to count instead."""
    words = [w.strip(".") for w in re.split(r"[\s,;!?]+", expression.strip())]  # "15.10" keeps its dot
    core = " ".join(w for w in words if w and fold(w) not in FILLER)
    if not core:
        return None
    low = fold(core)
    if day_month_text := DAY_MONTH.fullmatch(low):  # "15/10", "ngày 15 tháng 10" (the next one), "15/10/2026"
        try:
            return day_month(int(day_month_text[1]), int(day_month_text[2]), today,
                             int(day_month_text[3]) if day_month_text[3] else None)
        except ValueError:  # 30/2 is not a date
            return None
    matches = relative_dates(low, core.lower(), today)
    if len(matches) != 1 or matches[0].field != "start_date" or matches[0].span != (0, len(low)):
        return None
    return matches[0].value


def weekday_named(idx: int, text: str) -> bool:
    """The user's text names weekday idx (Monday=0) in a form the code knows: "thứ 5", "thứ năm", "chủ nhật", "cn"."""
    return re.search(r"\b(?:" + WEEKDAY_WORD[idx] + r")\b", squash(text)) is not None
