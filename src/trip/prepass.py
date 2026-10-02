"""Deterministic first read of a user message (docs/plans/TRIP_UNDERSTANDING_SPEC.md §5).

Numbers, dates, who, transport, health hints, money and keyword features. Runs before the agent, so the screen reacts at
once and a failed agent call still records something. Every proposal quotes the user's own words.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from .text import fold


@dataclass(frozen=True)
class Proposal:
    field: str
    op: str
    value: object
    quote: str
    inferred: bool = False


@dataclass(frozen=True)
class Prepass:
    proposals: tuple[Proposal, ...]
    ambiguous: tuple[tuple[str, tuple[str, ...]], ...]  # (quote, soft keys it may mean)


# "một ngày" (one day of it) and "từ ngày" (from) are not trip lengths; "bay / sau ngày 12" (fly / after) is
# excluded by the no-digit-after rule in prepass()
NUMBER = {"hai": 2, "ba": 3, "bon": 4, "nam": 5, "sau": 6, "bay": 7}
# a negation up to four words before a match ("không đi với bố mẹ", "không thích chỗ có view")
NEGATION = re.compile(r"\b(khong|chang|ko|tranh|ghet|ngai|so)\s+(\w+\s+){0,4}$")

COMPANIONS = [
    (r"\b(bo me|ba me|ba ma|cha me|ong ba|phu huynh|nguoi lon tuoi)\b", "parents"),
    (r"\b(nguoi yeu|ban gai|ban trai|vo chong|hai vo chong|cap doi|honeymoon|trang mat)\b", "partner"),
    (r"\b(ban be|nhom ban|hoi ban|dong nghiep|team)\b", "friends"),
    (r"\b(con nho|tre nho|tre em|em be|be nho|cac be)\b", "kids"),
    (r"\b(mot minh|solo)\b", "solo"),
]
SIGNALS = [
    (r"\b(dau goi|dau lung|moi goi|moi chan|thoai hoa|kho di lai|di lai kho|chan yeu|yeu chan)\b", "knee"),
    (r"\b(nguoi gia|lon tuoi|cao tuoi)\b", "elderly"),
    (r"\bxe lan\b", "wheelchair"),
    (r"\b(co bau|mang thai|dang bau|bau bi)\b", "pregnant"),
    (r"\bsay (xe|deo)\b", "motion_sick"),
    (r"\bso (do cao|cao)\b", "height"),
    (r"\b(an chay|chay truong|thuan chay)\b", "vegetarian"),
]
MOBILITY = [
    (r"\b(xe may|xe so|xe tay ga)\b", "motorbike"),
    (r"\b(o to|oto|xe hoi|xe rieng|tu lai|xe 4 cho|xe 7 cho)\b", "car"),
    (r"\b(grab|taxi|xe cong nghe|xanh sm|goi xe)\b", "ride"),
]
PACE = [
    (r"\b(thong tha|nhe nhang|di it|khong voi|cham rai)\b", "slow"),
    (r"\b(di nhieu|cang nhieu cang tot|kham pha het|full lich)\b", "packed"),
]
NOVELTY = [
    (r"\b(thu moi|cai moi|muon khac|chua di bao gio)\b", "new"),
    (r"\b(cho quen|nhu lan truoc)\b", "familiar"),
]
HARD = [
    (r"\b(tranh doc|khong leo|ngai leo|ngai bac thang|khong bac thang|it bac thang)\b", "steep_or_stairs"),
    (r"\b(khong di bo xa|ngai di bo|it di bo|khong di bo nhieu)\b", "long_walk"),
]
# Minimal lexicon until the span lexicon exists (docs/TRIP_UNDERSTANDING.md §5.2): one key = a clear wish,
# several = a subjective word to clarify.
LEXICON = [
    (r"\b(chill|thu gian|thu thai)\b", ("long_stay_chill=present", "noise=quiet", "crowd=low", "scenic_view=present",
                                       "cozy_decor=present")),
    (r"\b(yen tinh|tinh lang)\b", ("noise=quiet",)),
    (r"\b(vang ve|it nguoi|khong dong|tranh dong)\b", ("crowd=low",)),
    (r"\b(view|canh dep|ngam canh)\b", ("scenic_view=present",)),
    (r"\b(san may|bien may)\b", ("cloud_hunting=present",)),
    (r"\b(hoang hon|binh minh)\b", ("sunset_view=present",)),
    (r"\b(chup anh|chup hinh|song ao|check in|checkin)\b", ("photo_spot=present",)),
    (r"\b(thien nhien|rung thong|thac nuoc|con thac|ngam thac|suoi nuoc|con suoi)\b", ("nature=present",)),
    (r"\b(vuon hoa|doi hoa|ngam hoa|mua hoa)\b", ("flower_garden=present",)),
    (r"\b(kien truc|di tich|co kinh)\b", ("heritage_architecture=present",)),
    (r"\bvan hoa\b", ("heritage_architecture=present", "cultural_show=present")),
    (r"\b(cafe|ca phe|coffee)\b", ("cozy_decor=present", "long_stay_chill=present", "drink_quality=good",
                                   "scenic_view=present")),
    (r"\b(dac san|mon dia phuong)\b", ("local_specialty_food=present",)),
    (r"\b(an ngon|do an ngon)\b", ("food_quality=good",)),
    (r"\b(am thuc|an uong)\b", ("local_specialty_food=present", "food_quality=good")),
    (r"\b(nhac song|acoustic)\b", ("live_music=present",)),
    (r"\b(mao hiem|zipline|mang truot|canyoning|cam giac manh)\b", ("adventure_activity=present",)),
    (r"\b(leo nui|trekking|trek)\b", ("hiking=present",)),
    (r"\b(hai dau|vuon dau|hai trai cay)\b", ("pick_your_own=present",)),
    (r"\b(cam trai|glamping|ngu leu)\b", ("camping=present",)),
    (r"\b(workshop|tu tay lam)\b", ("hands_on_workshop=present",)),
    (r"\b(thu cung|vuon thu|so thu)\b", ("animals=present",)),
    (r"\b(gia re|binh dan|dang tien|gia hop ly)\b", ("value_for_money=good",)),
    (r"\b(laptop|ngoi lam viec)\b", ("laptop_friendly=present",)),
    (r"\b(rong rai|thoang dang)\b", ("spacious=present",)),
]


def _next_date(day: int, month: int, today: date) -> date | None:
    for year in (today.year, today.year + 1):
        try:
            d = date(year, month, day)
        except ValueError:
            return None
        if d >= today:
            return d
    return None


def prepass(text: str, today: date) -> Prepass:
    raw = unicodedata.normalize("NFC", text)
    low = fold(raw)
    out: list[Proposal] = []
    taken: list[tuple[int, int]] = []

    def add(field, value, m, op="set", inferred=False, group=0):
        out.append(Proposal(field, op, value, raw[m.start(group):m.end(group)], inferred))

    # a range first, so "12-14/12" is not also read as two single dates
    for m in re.finditer(r"\b(\d{1,2})\s*(?:-|–|den)\s*(\d{1,2})\s*/\s*(\d{1,2})\b", low):
        d1, d2, mo = map(int, m.groups())
        start = _next_date(d1, mo, today)
        if start and d2 >= d1:
            add("start_date", start, m)
            add("days", d2 - d1 + 1, m)
            taken.append(m.span())
    for m in re.finditer(r"(?<![\d/])(\d{1,2})\s*/\s*(\d{1,2})\b(?!\s*(?:ngay|n)\b)", low):
        if any(a <= m.start() < b for a, b in taken):
            continue
        start = _next_date(int(m[1]), int(m[2]), today)
        if start:
            add("start_date", start, m)
    for m in re.finditer(r"\bthang\s*(\d{1,2})\b", low):
        if 1 <= int(m[1]) <= 12:
            add("month", int(m[1]), m)
    if not any(p.field == "days" for p in out):
        m = re.search(r"\b(\d)\s*n\s*(\d)\s*d\b", low)
        if m:
            add("days", int(m[1]), m)
        else:
            for m in re.finditer(r"(?<!/)\b(\d{1,2})\s*(?:ngay|n)\b|\b(hai|ba|bon|nam|sau|bay)\s+ngay\b(?!\s*\d)", low):
                n = int(m[1]) if m[1] else NUMBER[m[2]]
                if 1 <= n <= 7:
                    add("days", n, m)
                    break
    for m in re.finditer(r"\b(\d{1,2})\s*(?:nguoi|ng)\b", low):
        add("people", int(m[1]), m)
        break
    for m in re.finditer(r"\b(\d+(?:[.,]\d+)?)\s*(k|nghin|ngan|tr|trieu|cu)\b", low):
        n = float(m[1].replace(",", "."))
        add("budget_vnd", int(n * (1000 if m[2] in ("k", "nghin", "ngan") else 1_000_000)), m)
        break
    def negated(m) -> bool:
        return bool(NEGATION.search(low[max(0, m.start() - 32):m.start()]))

    for pattern, who in COMPANIONS:
        for m in re.finditer(pattern, low):
            if negated(m):
                continue
            add("companions", who, m, op="add")
            if who == "parents":
                add("signal", "elderly", m, op="add", inferred=True)
            if who == "kids":
                add("signal", "kids", m, op="add", inferred=True)
    for pattern, kind in SIGNALS:
        for m in re.finditer(pattern, low):
            if negated(m):
                continue
            add("signal", kind, m, op="add")
    for table, field in ((MOBILITY, "mobility"), (PACE, "pace"), (NOVELTY, "novelty")):
        for pattern, value in table:
            m = next((m for m in re.finditer(pattern, low) if not negated(m)), None)
            if m:
                add(field, value, m)
                break
    for pattern, feature in HARD:
        for m in re.finditer(pattern, low):
            add("hard", {"feature": feature, "op": "ne", "value": "present"}, m, op="add")
    ambiguous: list[tuple[str, tuple[str, ...]]] = []
    for pattern, keys in LEXICON:
        for m in re.finditer(pattern, low):
            if negated(m):
                continue
            if len(keys) == 1:
                add("soft", (keys[0], "love"), m, op="add")
            else:
                ambiguous.append((raw[m.start():m.end()], keys))
    seen, unique = set(), []
    for p in out:
        key = (p.field, p.op, repr(p.value))
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return Prepass(tuple(unique), tuple(dict.fromkeys(ambiguous)))
