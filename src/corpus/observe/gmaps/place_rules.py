"""Maps place-level data -> evidence by rule, no model.

attributes   owner / Google declared ("Phù hợp cho trẻ em") -> observations of one authoritative source
popular_times  relative busyness per weekday and hour (100 = the place's own peak), Sunday first
price        Maps' price range per person, as reported by visitors
"""

import re

RULES_VERSION = "place_rules@v2"
AUTHOR = "gmaps:attributes"  # one source, whatever the number of attributes

ATTRIBUTES = {
    "Phù hợp cho trẻ em": ("kids", "suitable"),
    "Có Phù hợp với trẻ em": ("kids", "suitable"),
    "Có hoạt động phù hợp với trẻ em": ("kids", "suitable"),
    "Phù hợp khi đi theo nhóm": ("groups", "suitable"),
    "Có chỗ ngồi ngoài trời": ("outdoor_seating", "present"),
    "Phù hợp để làm việc trên máy tính xách tay": ("laptop_friendly", "present"),
    # the entrance decides access; wheelchair toilets / seats / parking alone do not. Left out on purpose: a kids
    # menu (says nothing about stairs or safety) and the bare label "Lối vào cho xe lăn" (not from the About panel)
    "Không có lối vào cho xe lăn": ("wheelchair", "unsuitable"),
    "Có lối vào dành riêng cho xe lăn": ("wheelchair", "suitable"),
}
DAYS = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")
_HOUR = re.compile(r"là (\d+)% lúc (\d+) giờ")
_ABOVE = re.compile(r"Khoảng giá, Trên ([\d.]+)\s*₫/người(?:, (\d+) người đã báo cáo)?")
_RANGE = re.compile(r"Khoảng giá, ([\d.]+)-([\d.]+)\s*₫/người(?:, (\d+) người đã báo cáo)?")
LEVELS = {"Giá rẻ": "cheap", "Giá vừa phải": "moderate", "Giá đắt": "expensive", "Giá rất đắt": "very_expensive"}


def attribute_pairs(attributes: list[str] | None) -> list[tuple[str, str, str]]:
    return [(*ATTRIBUTES[a], a) for a in attributes or [] if a in ATTRIBUTES]


def parse_popular_times(raw: list[list[str]] | None) -> dict | None:
    out = {}
    for name, lines in zip(DAYS, raw or []):
        hours = {int(h): int(p) for line in lines for p, h in _HOUR.findall(line)}
        if any(hours.values()):  # all zero: closed that day
            out[name] = hours
    return out or None


def parse_price(raw: str | None) -> dict | None:
    if not raw:
        return None
    if raw in LEVELS:
        return {"level": LEVELS[raw]}
    vnd = lambda s: int(s.replace(".", ""))  # noqa: E731
    m = _ABOVE.search(raw)
    if m:
        return {"min_vnd": vnd(m.group(1)), "max_vnd": None, "per": "person",
                "reports": int(m.group(2)) if m.group(2) else None}
    m = _RANGE.search(raw)
    if not m:
        return None
    return {"min_vnd": vnd(m.group(1)), "max_vnd": vnd(m.group(2)), "per": "person",
            "reports": int(m.group(3)) if m.group(3) else None}
