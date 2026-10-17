"""Exact commands and common wishes read without the model (docs/PLACE_DECISION.md §18); any unconsumed intent remains
an LLM task. Only the general feedback acts (far, crowded, pricey) come from here: a taste ("view đẹp") is Trip's."""

import re

from trip import squash

from .guard import names_in

# words that do not change what the user asks for; any other word left over sends the message to the model
FILLER = frozenset("toi minh muon can tim kiem cho nhung cac va voi hon chut nhe nha a la thi quan noi dia diem nao nhieu "
                   "mot it hoi that rat thich uu tien thoi duoc".split())
# the model decides these: they name or reject a place, or move the trip
PLACE_VERBS = re.compile(r"\b(?:chon|them|bo|xoa|khoa|giu|loai|thay|da di|di roi|den roi|toi roi|cai|thu \d+)\b")

# wish -> (regex over squashed text, the actions it is). A message made only of these (and FILLER) is answered here.
CROWD = (r"yen tinh|im lang|it dong(?: nguoi)?|vang ve|khong (?:thich )?(?:(?:quan|cho|noi) )?(?:dong|dong nguoi|on ao)|"
         r"tranh dong|do dong|bot dong|dong qua|dong nguoi qua")
PRICE = r"re|re hon|gia re|binh dan|tiet kiem|khong dat|do dat|bot dat|dat qua|gia mem"
FAR = r"gan(?: trung tam)?|gan hon|do xa|bot xa|khong xa|xa qua|it di chuyen"
POINTS_AT = re.compile(r"\b(?:dau|tien|nay|do|kia|ay|thu|cuoi|tren|duoi|giua|tab|muc|trang|hang|vua roi|truoc|sau)\b")  # "quán đầu", "nơi này"
QUESTION = re.compile(r"\b(?:sao|nghi|gi|tai sao|vi sao|la gi|the nao|nhu nao|bao nhieu|o dau|co nen|nen khong|co the|giai thich|so sanh|hay hon|khac nhau|cam on|xin chao)\b")


def exact_command(text: str, aliases: dict[str, dict]) -> list[dict] | None:
    command, _, name = squash(text).partition(' ')
    operation = {'chon': 'select', 'them': 'select', 'bo': 'drop', 'khoa': 'lock'}.get(command)
    if not operation or not name:
        return None
    matches = {place['id'] for place in aliases.values() if squash(place['name']) == name}
    if len(matches) != 1:
        return None
    return [{'type': operation, 'place_id': next(iter(matches))}]


def common_wish(text: str, aliases: dict[str, dict]) -> tuple[list[dict], str] | None:
    """(actions, reply) when the whole message is a general wish the session profile already holds: quieter, cheaper,
    closer. None as soon as a word is left over, a place on screen is named, or the user rejects / picks."""
    t = squash(text)
    if not t or len(t) > 120 or PLACE_VERBS.search(t) or any(names_in(text, a["name"]) for a in aliases.values()):
        return None
    actions: list[dict] = []
    said: list[str] = []

    def take(pattern: str, make, reply: str) -> None:
        nonlocal t
        if re.search(rf"\b(?:{pattern})\b", t):
            t = re.sub(rf"\b(?:{pattern})\b", " ", t)
            actions.extend(make)
            said.append(reply)

    take(CROWD, [{"type": "feedback", "reason": "crowded"}], "ưu tiên nơi ít đông")
    take(PRICE, [{"type": "feedback", "reason": "pricey"}], "ưu tiên nơi giá mềm hơn")
    take(FAR, [{"type": "feedback", "reason": "far"}], "ưu tiên nơi gần hơn")
    if not actions or any(w not in FILLER for w in t.split()):
        return None
    return actions, "Mình sẽ " + ", ".join(said) + "."


def general_wish(text: str, aliases: dict[str, dict]) -> bool:
    """The message names no place on screen and picks or rejects none: it is a wish about the trip, which Trip
    Understanding reads. The Decision model has nothing to add, so it is not called."""
    t = squash(text)
    if ("?" in text or QUESTION.search(t) or POINTS_AT.search(t) or len(t.split()) < 2 or len(t) > 240
            or PLACE_VERBS.search(t)):
        return False  # a question, a greeting or a command for the model to answer
    return not any(names_in(text, a["name"]) for a in aliases.values())
