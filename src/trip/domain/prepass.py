"""Deterministic first read of a user message (docs/TRIP_UNDERSTANDING.md §4).

Only high-precision slots are proposed as facts: numbers, dates, people, money and explicit body/health
hints plus effort hard filters. Anything needing conversational context (who goes, transport, pace,
novelty, kinds of place) is a suggestion for the agent, never a fact: the agent reads the user's words
(negations, corrections, removals) and decides via record_fact. Runs before the agent, so the screen
reacts at once and a failed agent call still records something. Every proposal quotes the user's own words.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from .dates import FULL_DATE, RANGE, UNTIL, relative_dates
from .state import MAX_TRIP_DAYS
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
    suggestions: tuple[Proposal, ...] = ()  # agent-only hints: read, never applied to the state


# "một ngày" (one day of it) and "từ ngày" (from) are not trip lengths; "bay / sau ngày 12" (fly / after) is
# excluded by the no-digit-after rule in prepass()
NUMBER = {"hai": 2, "ba": 3, "bon": 4, "nam": 5, "sau": 6, "bay": 7}
# a negation up to four words before a match ("không đi với bố mẹ", "không thích chỗ có view")
# "k" is the common shorthand for "không"
NEGATION = re.compile(r"\b(khong|chang|k|ko|tranh|ghet|ngai|so)\s+(\w+\s+){0,4}$")

COMPANIONS = [
    (r"\b(bo me|ba me|ba ma|cha me|ong ba|phu huynh|nguoi lon tuoi)\b", "parents"),
    (r"\b(nguoi yeu|ban gai|ban trai|vo chong|hai vo chong|cap doi|honeymoon|trang mat)\b", "partner"),
    (r"\b(ban be|nhom ban|hoi ban)\b", "friends"),
    (r"\b(dong nghiep|team building|team|cong ty)\b", "coworkers"),
    (r"\b(con nho|tre nho|tre em|em be|be nho|cac be)\b", "kids"),
    (r"\b(so sinh|xe day|con moi sinh)\b", "baby"),
    (r"\b(thu cung|con cho|con meo|cun cung|pet)\b", "pet"),
    (r"\b(mot minh|solo)\b", "solo"),
]
SIGNALS = [
    (r"\b(dau goi|dau lung|moi goi|moi chan|thoai hoa|kho di lai|di lai kho|chan yeu|yeu chan)\b", "knee"),
    (r"\b(nguoi gia|lon tuoi|cao tuoi)\b", "elderly"),
    (r"\bxe lan\b", "wheelchair"),
    (r"\b(co bau|mang thai|dang bau|bau bi)\b", "pregnant"),
    (r"\bsay (xe|deo)\b", "motion_sick"),
    (r"\bso (do cao|cao)\b", "height"),
    (r"\b(an chay|chay truong)\b", "vegetarian"),
    (r"\b(thuan chay|vegan)\b", "vegan"),
]
MOBILITY = [
    (r"\b(xe may|xe so|xe tay ga)\b", "motorbike"),
    (r"\b(o to|oto|xe hoi|xe rieng|tu lai|xe 4 cho|xe 7 cho)\b", "car"),
]
# How the user gets TO the city, said outright; only a coach or a plane names the way in by itself
ARRIVAL = [
    (r"\b(xe khach|nha xe|limousine|giuong nam)\b", "bus"),
    (r"\b(may bay|chuyen bay|ve may bay|bay vao|bay len|bay toi)\b", "plane"),
]
# a car the traveller drives: how they come ("ô tô tự lái") and, only as a guess, how they get around the city
SELF_CAR = re.compile(r"\b(o to|oto|xe hoi)\b.{0,12}\btu lai\b|\btu lai\b.{0,12}\b(o to|oto|xe hoi)\b|\blai (o to|oto|xe hoi)\b")
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
# What a budget amount covers, read in its own clause (right after it first, then right before it); first match wins.
WHO_N = r"(?:moi|mot|1|/|tren|dau)\s*(?:nguoi|ng)\b"
DAY_N = r"(?:moi|mot|1|/|tren)\s*(?:ngay|hom)\b"
BUDGET_SCOPE = [
    (rf"{WHO_N}\s*(?:moi|mot|1|/|tren)?\s*(?:ngay|hom)\b|{DAY_N}\s*{WHO_N}", "per_person_day"),
    (WHO_N, "per_person"),
    (DAY_N, "per_day"),
    (r"\b(?:tong|ca chuyen|toan bo|tat ca|ca nhom|ca hai|ca 2|cho (?:\d+|hai|ba|bon|nam|sau) (?:nguoi|ng)|cho ca)\b",
     "trip_total"),
]
MONTH_PART = {"dau": "early", "giua": "mid", "cuoi": "late"}
# Kinds of place said outright ("thích cà phê", "ăn uống"): Place Decision's display groups (config/decision.yaml) + meal.
GROUPS = [
    (r"\b(cafe|ca phe|caphe|coffee)\b", "chill"),
    (r"\b(an uong|am thuc|quan an|dac san|an ngon|do an|mon an|an vat|nha hang)\b", "meal"),
    (r"\b(thien nhien|rung thong|thac nuoc|cam trai|glamping|vuon hoa|doi hoa)\b", "nature"),
    (r"\b(tham quan|bao tang|di tich|nha tho|kien truc)\b", "sights"),
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


def _on(day: int, month: int, year: str | None, today: date) -> date | None:
    """A written day and month: in the year the user wrote, else the next time it comes."""
    if not year:
        return _next_date(day, month, today)
    try:
        return date(int(year), month, day)
    except ValueError:
        return None


COUNT = r"\d{1,2}|hai|ba|bon|nam|sau|bay|tam|chin|muoi"
COUNT_WORD = {**NUMBER, "tam": 8, "chin": 9, "muoi": 10}
FRIEND_GROUP = r"nhom|ca nhom|ca doan|doan|tui tui|tui minh|bon minh|chung minh"
# a head count said in the traveller's words: "nhóm mình 6 đứa", "nhà mình 5 người", "hai đứa mình", "6 bạn"
_PARTY_SUBJECT = re.compile(
    r"\b(?:" + FRIEND_GROUP + r"|gia dinh|nha|chung toi|bon toi|tui toi)(?:\s+(?:minh|toi|tui|em|ta))?\s+(" + COUNT + r")\s*"
    r"(?:dua|nguoi|ng|ban|thanh vien|anh chi em)\b(?!\s+(?:nho|con|be|tre)\b)")
_PARTY_SELF = re.compile(r"\b(" + COUNT + r")\s*dua\s+(?:minh|toi|tui|em)\b")
_COUPLES = re.compile(r"\b(?:(" + COUNT + r")\s+)?vo chong\b")
_KIDS = re.compile(r"\b(" + COUNT + r")\s*(?:con|be|chau|nhoc|em be|tre|dua nho|dua con|dua be)\b")
_ELDER = re.compile(r"\b(?:bo me|ba me|ong ba|ba ngoai|ong ngoai|ba noi|ong noi)\b")


def _count(word: str) -> int:
    return int(word) if word.isdigit() else COUNT_WORD[word]


def party_size(low: str) -> tuple[int, int, int, bool] | None:
    """The head count the words state: (people, start, end, guessed) over the folded text, or None.

    Said outright ("nhóm mình 6 đứa", "5 người", "hai đứa mình") it is the user's own number. A household sum
    ("vợ chồng + 2 bé" = 4) is only a guess the card asks to confirm: nobody said the total, and "2 con" may be grown up."""
    if m := _PARTY_SUBJECT.search(low) or _PARTY_SELF.search(low):
        n = _count(m[1])
        if 1 <= n <= 20:
            return n, m.start(), m.end(), False
    if m := re.search(r"\b(\d{1,2})\s*(?:nguoi|ng)\b", low):
        return int(m[1]), m.start(), m.end(), False
    couple = _COUPLES.search(low)
    if couple is None:
        return None
    kids = [k for k in _KIDS.finditer(low) if not NEGATION.search(low[max(0, k.start() - 32):k.start()])]
    elders = _ELDER.findall(low)
    if not kids and not elders:
        return None
    total = 2 * (_count(couple[1]) if couple[1] else 1) + sum(_count(k[1]) for k in kids)
    total += sum(2 if w in ("bo me", "ba me", "ong ba") else 1 for w in elders)
    spans = [couple.span()] + [k.span() for k in kids] + [x.span() for x in _ELDER.finditer(low)]
    return (total, min(a for a, _ in spans), max(b for _, b in spans), True) if 2 <= total <= 20 else None


def prepass(text: str, today: date) -> Prepass:
    raw = unicodedata.normalize("NFC", text)
    low = fold(raw)
    out: list[Proposal] = []
    taken: list[tuple[int, int]] = []

    def add(field, value, m, op="set", inferred=False, group=0):
        out.append(Proposal(field, op, value, raw[m.start(group):m.end(group)], inferred))

    for resolved in relative_dates(low, raw.lower(), today):
        a, b = resolved.span
        out.append(Proposal(resolved.field, "set", resolved.value, raw[a:b]))

    # a range first, so "12-14/12" is not also read as two single dates. Its length is written only when the user
    # gave no length of their own ("3 ngày 2 đêm, từ 17 đến 20/10": the 3 days they said win)
    span_days: tuple[int, int, int] | None = None  # (days, quote start, quote end)
    for m in RANGE.finditer(low):
        d1, d2 = int(m[1]), int(m[2])
        start = _on(d1, int(m[3]), m[4], today)
        if start and d2 >= d1:
            add("start_date", start, m)
            span_days = (d2 - d1 + 1, m.start(), m.end())
            taken.append(m.span())
            break
    singles = [(m, d) for m in FULL_DATE.finditer(low) if not any(a <= m.start() < b for a, b in taken)
               and (d := _on(int(m[1]), int(m[2]), m[3], today))]
    if singles and span_days is None:
        (m, start), *rest = singles
        add("start_date", start, m)
        if rest and UNTIL.search(low[m.end():rest[0][0].start()]):  # "từ 17/10 đến 20/10"
            n = (rest[0][1] - start).days + 1
            if 1 <= n <= MAX_TRIP_DAYS:
                span_days = (n, m.start(), rest[0][0].end())
    for m in re.finditer(r"\b(?:(dau|giua|cuoi)\s+)?thang\s*(\d{1,2})\b", low):
        if 1 <= int(m[2]) <= 12:
            add("month", int(m[2]), m)
            if m[1]:  # "cuối tháng 10" is more than "tháng 10"
                add("month_part", MONTH_PART[m[1]], m)
    def duration_negated(m) -> bool:
        return bool(NEGATION.search(low[max(0, m.start() - 32):m.start()]))

    if not any(p.field == "days" for p in out):
        m = re.search(r"\b(\d{1,2})\s*n\s*(\d{1,2})\s*d\b", low)
        if m:
            if not duration_negated(m) and 1 <= int(m[1]) <= MAX_TRIP_DAYS and 0 <= int(m[2]) <= MAX_TRIP_DAYS:
                add("days", int(m[1]), m)
                add("nights", int(m[2]), m)
        else:
            for m in re.finditer(r"(?<!/)\b(\d{1,2})\s*(?:ngay|n)\b|\b(hai|ba|bon|nam|sau|bay)\s+ngay\b(?!\s*\d)", low):
                n = int(m[1]) if m[1] else NUMBER[m[2]]
                if not duration_negated(m) and 1 <= n <= MAX_TRIP_DAYS:
                    add("days", n, m)
                    break
            if not any(p.field == "days" for p in out):
                for m in re.finditer(r"\b(\d{1,2}|mot|hai)\s+(?:tuan|weeks?)\b", low):
                    before = low[max(0, m.start() - 40):m.start()]
                    relative = re.search(r"\bsau(?:\s+(?:khoang|tam|chung|hon|gan))*\s*$", before) or re.match(
                        r"\s+nua\b", low[m.end():])
                    if relative or duration_negated(m) or re.search(r"\b(?:moi|tren|ngan sach)\s*$|/\s*$|\b(?:trieu|tr|nghin|ngan|k)\s*$", before):
                        continue
                    n = int(m[1]) if m[1].isdigit() else {"mot": 1, "hai": 2}[m[1]]
                    if 1 <= n * 7 <= MAX_TRIP_DAYS:
                        add("days", n * 7, m)
                        break
    for m in re.finditer(r"\b(\d{1,2})\s*dem\b|\b(hai|ba|bon|nam|sau|bay)\s+dem\b", low):
        if not any(p.field == "nights" for p in out):
            n = int(m[1]) if m[1] else NUMBER[m[2]]
            if not duration_negated(m) and 0 <= n <= MAX_TRIP_DAYS:
                add("nights", n, m)
                if not any(p.field == "days" for p in out) and n < MAX_TRIP_DAYS:
                    add("days", n + 1, m, inferred=True)
    if span_days and not any(p.field == "days" for p in out):
        n, a, b = span_days
        out.append(Proposal("days", "set", n, raw[a:b]))
    if not any(p.field == "days" for p in out):
        m = re.search(r"\b(di|ve|choi)\s+(ve\s+)?trong\s+ngay\b|\bday trip\b", low)
        if m:  # a day trip: one day, no night in the city
            add("days", 1, m)
            add("nights", 0, m)
    if (party := party_size(low)) is not None:
        n, a, b, guessed = party
        out.append(Proposal("people", "set", n, raw[a:b], guessed))
    for m in re.finditer(r"\b(\d+(?:[.,]\d+)?)\s*(k|nghin|ngan|tr|trieu|cu)\b", low):
        n = float(m[1].replace(",", "."))
        add("budget_vnd", int(n * (1000 if m[2] in ("k", "nghin", "ngan") else 1_000_000)), m)
        after = re.split(r"[.,;!?\n]", low[m.end():m.end() + 40])[0]
        before = re.split(r"[.,;!?\n]", low[max(0, m.start() - 25):m.start()])[-1]
        hits = []  # (start, end, scope) in the text
        for part, at in ((after, m.end()), (before, m.start() - len(before))):
            for pattern, sc in BUDGET_SCOPE:
                if sm := re.search(pattern, part):
                    hits.append((at + sm.start(), at + sm.end(), sc))
                    break
        if hits:
            a, b, sc = hits[0]
            if {h[2] for h in hits} == {"per_person", "per_day"}:  # "mỗi người 1 triệu một ngày"
                a, b, sc = min(h[0] for h in hits), max(h[1] for h in hits), "per_person_day"
            out.append(Proposal("budget_scope", "set", sc, raw[a:b]))
        break
    def negated(m) -> bool:
        return bool(NEGATION.search(low[max(0, m.start() - 32):m.start()]))

    suggest: list[Proposal] = []

    def propose(field, value, m, op="set", inferred=False, group=0):
        suggest.append(Proposal(field, op, value, raw[m.start(group):m.end(group)], inferred))

    for pattern, who in COMPANIONS:
        for m in re.finditer(pattern, low):
            if negated(m):
                continue
            # who goes needs conversational context (negations, corrections): a suggestion only
            propose("companions", who, m, op="add")
    # Short companion words must retain their marks, as in guard.names_group.
    short = {"partner": ("bồ", "vợ", "chồng", "ny"), "parents": ("mẹ", "bố", "ông", "bà"), "kids": ("bé",)}
    ambiguous_family = bool(re.search(r"\b\d+\s+mẹ\s+con\b", raw.lower()))
    for who, words in short.items():
        if ambiguous_family:
            continue
        for word in words:
            for m in re.finditer(r"\b" + word + r"\b", raw.lower()):
                if not negated(m):
                    propose("companions", who, m, op="add")
    for m in re.finditer(r"\b(?:" + FRIEND_GROUP + r")(?:\s+(?:minh|toi|tui|em|ta))?\s+(?:" + COUNT + r")\s*(?:dua|ban)\b(?!\s+(?:nho|con|be|tre)\b)", low):
        if not negated(m):
            propose("companions", "friends", m, op="add")
    for m in re.finditer(r"\bnhom\s+\d+\s+cap doi\b", low):
        if not negated(m):
            propose("companions", "friends", m, op="add")
    for pattern, way in ARRIVAL:
        m = next((m for m in re.finditer(pattern, low) if not negated(m)), None)
        if m:
            add("arrival_mode", way, m)
            break
    else:
        if m := SELF_CAR.search(low):
            if not negated(m):
                add("arrival_mode", "self", m)
                add("mobility", "car", m, inferred=True)
                add("driver", "self", m, inferred=True)
    for m in re.finditer(r"\b(di ung|ung)\s+(?:voi\s+)?(hai san|tom|cua|ca|lac|dau phong|sua|trung|gluten)\b", low):
        if not negated(m):  # no place feature checks an allergen: kept as a note the user is reminded of, never a filter
            add("unmapped", f"dị ứng {raw[m.start(2):m.end(2)].lower()}", m, op="add")
    for pattern, kind in SIGNALS:
        for m in re.finditer(pattern, low):
            if negated(m):
                continue
            if kind in {"vegetarian", "vegan"} and re.search(r"\b(thich|muon thu|thu)\s+(?:\w+\s+){0,2}$", low[max(0, m.start() - 30):m.start()]):
                continue
            add("signal", kind, m, op="add")
    for table, field in ((MOBILITY, "mobility"), (PACE, "pace"), (NOVELTY, "novelty")):
        for pattern, value in table:
            m = next((m for m in re.finditer(pattern, low) if not negated(m)), None)
            if m:
                propose(field, value, m)
                break
    for pattern, group in GROUPS:
        m = next((m for m in re.finditer(pattern, low) if not negated(m)), None)
        if m:
            propose("liked_groups", group, m, op="add")
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
    seen_s, unique_s = set(), []
    for p in suggest:
        key = (p.field, p.op, repr(p.value))
        if key not in seen_s:
            seen_s.add(key)
            unique_s.append(p)
    return Prepass(tuple(unique), tuple(dict.fromkeys(ambiguous)), tuple(unique_s))
