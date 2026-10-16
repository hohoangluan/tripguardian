"""What an eating place is for (a main meal, breakfast, a snack, dinner at a market) and which time of day a place
known for several is visited for. Read from the served record only; nothing is guessed."""

import re
from functools import lru_cache

from .places import parse_hours

DAWN_FIRST = ("cloud_hunting",)

# Role -> the meal slots it may take, in the order it prefers them. A place with no role fits any slot.
ROLE_SLOTS = {"breakfast": ("breakfast", "lunch"), "main": ("lunch", "dinner"), "night_meal": ("dinner",)}


def takes_meal_slot(place) -> bool:
    """An eating place that fills one of the day's meal slots; a snack stop (dessert, cafe) never does."""
    usable = place.rec.get("usable_as") or ()
    flexible = "meal" in usable and "experience" in usable and (not place.activity_explicit or place.activity != "eating")
    return place.kind == "meal" and place.meal_kind != "light" and not flexible


@lru_cache(maxsize=64)
def _pattern(dishes: tuple) -> re.Pattern | None:
    """One compiled whole-word alternation per dish list: building a regex per dish per place cost ~1 s for the
    hundreds of places a suggestion pool reads."""
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(d) for d in dishes) + r")(?!\w)") if dishes else None


def _contains(text: str, dishes) -> bool:
    pattern = _pattern(tuple(dishes))
    return bool(pattern and pattern.search(text.casefold()))


def _text(rec: dict) -> str:
    """The served name and dishes, shared with suggestion matching."""
    dishes = " ".join(d.get("name") or "" for d in (rec.get("menu") or {}).get("dishes") or [])
    return f"{rec['identity'].get('name') or ''} {dishes}".casefold()


def _open_evening(rec: dict) -> bool:
    hours = (rec.get("operation") or {}).get("hours")
    if not hours:
        return False
    return any(o <= 18 * 60 < c for spans in parse_hours(hours["value"]).values() for o, c in spans)


def meal_kind(rec: dict, cfg) -> str | None:
    """main | breakfast | light | night_meal | None (not an eating place)."""
    group = rec["identity"].get("category_group")
    if group == "market":
        return "night_meal" if _open_evening(rec) else None     # no evening hours known: no role, never guessed
    if group in cfg.realistic["light_groups"]:
        return "light"
    if "meal" not in (rec.get("usable_as") or []):
        return None
    name = rec['identity'].get('name') or ''
    breakfast = cfg.realistic["breakfast_dishes"]
    # A shop selling rice rolls is a breakfast venue, not a bakery named by a partial phrase.
    if _contains(name, breakfast):
        return "breakfast"
    if _contains(name, cfg.realistic.get('light_dishes', ())):
        return "light"
    breakfast_sections = ('bữa sáng', 'breakfast', 'điểm tâm', 'ăn sáng')
    other_sections = ('lẩu', 'nướng', 'đồ uống', 'thức uống', 'nước uống', 'giải khát', 'tráng miệng',
                      'dessert', 'drinks', 'cà phê', 'coffee', 'bia', 'rượu', 'sinh tố', 'nước ép')
    for dish in (rec.get('menu') or {}).get('dishes') or []:
        section = dish.get('section') or ''
        if _contains(section, breakfast_sections):
            return "breakfast"
        if not _contains(section, other_sections) and _contains(dish.get('name') or '', breakfast):
            return "breakfast"
    return "main"


def pin_order(pins: tuple[str, ...], wants: set[str]) -> tuple[str, ...]:
    """The timed features in the order the plan tries them: the ones the user asked for only; else dawn first (a
    cloud-hunting hill is a dawn place even when it also has a sunset view)."""
    if wants & set(pins):
        return tuple(f for f in pins if f in wants)
    return tuple(sorted(pins, key=lambda f: (f not in DAWN_FIRST, pins.index(f))))
