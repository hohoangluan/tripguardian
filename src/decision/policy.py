"""Fallback when the agent fails (docs/ARCHITECTURE.md §18.4): keywords + names on screen -> the same actions."""

from trip import contains

from .guard import names_in

KEYWORDS = (("visited", ("di roi", "den roi", "toi roi", "da di")),
            ("pricey", ("dat qua", "mac qua", "gia cao", "dat do")),
            ("crowded", ("dong qua", "dong nguoi", "it nguoi", "vang hon")),
            ("far", ("xa qua", "xa", "gan hon")),
            ("dislike", ("khong thich", "chan")))
DONE = "Mình đã ghi nhận, danh sách đã cập nhật."
NONE = "Mình chưa hiểu ý bạn. Bạn bấm Bỏ qua hoặc Thêm trên thẻ giúp mình nhé."


def policy(text: str, aliases: dict[str, dict]) -> tuple[list[dict], str]:
    reason = next((r for r, keys in KEYWORDS if any(contains(text, k) for k in keys)), None)
    place = next((a for a in aliases.values() if names_in(text, a["name"])), None)
    if place and reason:
        return [{"type": "drop", "place_id": place["id"], "reason": reason}], DONE
    if reason in ("far", "crowded", "pricey"):
        return [{"type": "feedback", "reason": reason}], DONE
    return [], NONE
