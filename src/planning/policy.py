"""Fallback when the agent fails (docs/P4_PLANNING.md §Guardrail: "Agent lỗi, timeout hoặc JSON hỏng ->
policy.py từ khóa làm lượt đó"). Mirrors src/decision/policy.py in shape, not in import."""

from trip import contains

from .guard import names_in

DROP_KEYWORDS = (("visited", ("di roi", "den roi", "toi roi", "da di")),
                 ("pricey", ("dat qua", "mac qua", "gia cao", "dat do")),
                 ("crowded", ("dong qua", "dong nguoi", "it nguoi", "vang hon")),
                 ("far", ("xa qua", "xa", "gan hon")),
                 ("dislike", ("khong thich", "chan")))
PACE_KEYWORDS = (("slow", ("cham lai", "thong tha", "it nho")), ("packed", ("nhanh len", "nhieu noi hon", "day hon")))
DONE = "Mình đã ghi nhận, lịch đã cập nhật."
NONE = "Mình chưa hiểu ý bạn. Bạn bấm trên thẻ hoặc gõ lại rõ hơn giúp mình nhé."


def policy(text: str, aliases: dict[str, dict]) -> tuple[list[dict], str]:
    reason = next((r for r, keys in DROP_KEYWORDS if any(contains(text, k) for k in keys)), None)
    place = next((a for a in aliases.values() if a["kind"] == "place" and names_in(text, a["name"])), None)
    if place and reason:
        return [{"type": "drop_place", "place": place["id"], "reason": reason}], DONE
    level = next((lv for lv, keys in PACE_KEYWORDS if any(contains(text, k) for k in keys)), None)
    if level:
        return [{"type": "set_pace", "level": level}], DONE
    return [], NONE
