"""Maps' structured review details ("Độ ồn\nYên tĩnh, dễ trò chuyện", "Đồ ăn: 5") -> observations by rule, no model.

Maps cuts long labels with "…"; a cut value is used only when it is the unambiguous start of one known label.
"Không rõ" (and "Tuỳ theo ngày/giờ") are labels too, meaning no observation, so "Không…" stays ambiguous.
"""

from ...ontology import UNKNOWN

ELLIPSIS = "…"
MIN_PREFIX = 4

NOISE = {"Rất yên tĩnh": "quiet", "Yên tĩnh, dễ trò chuyện": "quiet", "Ồn ào ở mức vừa phải": "moderate",
         "Ồn ào, nhưng bạn vẫn trò chuyện được": "moderate", "Rất ồn, khó nghe": "loud"}
WAIT = {"Không cần đợi": "none", "Không cần chờ": "none", "Tới 10 phút": "short", "10 – 30 phút": "short",
        "10 đến 30 phút": "short", "30 – 60 phút": "long", "30 đến 60 phút": "long", "1 giờ trở lên": "long",
        "Hơn 1 giờ": "long"}
PARKING = {"Nhiều điểm đỗ xe": "easy", "Hơi khó tìm điểm đỗ xe": "hard", "Khó tìm điểm đỗ xe": "hard"}
PRICE_INFO = {"Giá tốt": "good", "Giá cả phải chăng": "good", "Quá đắt": "poor"}
BOOKING = {"Không cần đặt chỗ trước": "no", "Nên đặt chỗ trước": "yes", "Yêu cầu đặt chỗ trước": "yes",
           "Chỉ khách vãng lai": "no"}
TICKET = {"Có": "yes", "Không": "no"}
DAY_TYPE = {"Ngày trong tuần": "weekday", "Cuối tuần": "weekend", "Ngày nghỉ lễ": "holiday"}
NO_VALUE = ("Không rõ", "Tuỳ theo ngày/giờ")

TABLES = {"Độ ồn": ("noise", NOISE), "Thời gian đợi": ("wait_time", WAIT), "Thời gian chờ": ("wait_time", WAIT),
          "Điểm đỗ xe": ("parking", PARKING), "Thông tin đánh giá về mức giá": ("value_for_money", PRICE_INFO),
          "Đặt chỗ": ("booking_needed", BOOKING), "Nên đặt vé trước": ("booking_needed", TICKET)}
STARS = {"Đồ ăn": "food_quality", "Dịch vụ": "service_quality"}  # "Bầu không khí" has no clear feature
# questions Maps asks with a free-text answer: matched lower-case and whole, never by prefix
KIDS = {**dict.fromkeys(("có", "ok", "yes", "đúng", "rất thân thiện", "thân thiện", "rất tốt", "tốt", "có thể",
                          "phù hợp"), "suitable"), **dict.fromkeys(("không", "no", "ko", "không có"), "unsuitable")}
WHEELCHAIR = {**dict.fromkeys(("có", "yes", "đúng", "ok", "thoải mái"), "suitable"),
              **dict.fromkeys(("không", "không có", "no", "ko", "không có lối đi cho xe lăn"), "unsuitable")}
VEGETARIAN = {**dict.fromkeys(("có", "yes", "đúng", "có món chay", "nhà hàng chay", "thuần chay"), "yes"),
              **dict.fromkeys(("không", "no", "ko", "không có", "không có món chay"), "no")}
ANSWERS = {"Độ thân thiện với trẻ em": ("kids", KIDS), "Tình trạng có lối đi cho xe lăn": ("wheelchair", WHEELCHAIR),
           "Các món chay": ("vegetarian_options", VEGETARIAN)}


def split(line: str) -> tuple[str, str]:
    if "\n" in line:
        key, value = line.split("\n", 1)
    else:
        key, _, value = line.partition(":")
    return key.strip().rstrip(ELLIPSIS).strip(), value.strip()


def lookup(table: dict[str, str], raw: str) -> str | None:
    value = raw.rstrip(ELLIPSIS).strip()
    if not raw.endswith(ELLIPSIS):
        return table.get(value)
    if len(value) < MIN_PREFIX:
        return None
    labels = {**table, **dict.fromkeys(NO_VALUE)}
    hits = {v for label, v in labels.items() if label.startswith(value)}
    return hits.pop() if len(hits) == 1 else None


def star_value(raw: str) -> str | None:
    digit = raw.rstrip(ELLIPSIS).strip()
    if len(digit) != 1 or digit not in "12345":
        return None
    n = int(digit)
    return "good" if n >= 4 else "mixed" if n == 3 else "poor"


def details_pairs(review: dict) -> list[tuple[str, str, str]]:
    out = []
    for line in review.get("details") or []:
        key, raw = split(line)
        if key in TABLES:
            feature, table = TABLES[key]
            value = lookup(table, raw)
        elif key in STARS:
            feature, value = STARS[key], star_value(raw)
        elif key in ANSWERS:
            feature, table = ANSWERS[key]
            value = table.get(raw.rstrip(ELLIPSIS).strip().lower())
        else:
            continue
        if value:
            out.append((feature, value, line))
    return out


def day_type(review: dict) -> str:
    for line in review.get("details") or []:
        key, raw = split(line)
        if key == "Đã đến vào":
            return lookup(DAY_TYPE, raw) or UNKNOWN
    return UNKNOWN
