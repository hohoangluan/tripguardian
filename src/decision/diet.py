"""What a diner's diet means for eating places (docs/PLACE_DECISION.md §8.1). Evidence only: the served
`vegetarian_options` / `vegan_options` value, and what the place says it is in its own name and Google category. A
place that says it is a grill, a seafood place or the like is never marked "Hợp nhất" for a vegetarian or a seafood
allergy and is listed after the others; a place with no evidence stays unknown, never "matches"."""

import re
from dataclasses import dataclass

import numpy as np

from trip import squash

VEG_FEATURES = ("vegetarian_options", "vegan_options")
DEDICATED = re.compile(r"(?<!\w)chay(?!\w)")  # raw text: "chạy" is another word
MEAT = re.compile(r"(?<!\w)(?:nướng|bbq|thịt|hải sản|seafood|steak|bò|gà|heo|lợn|vịt|dê|ếch|ốc|tôm|cua|cá|sườn)(?!\w)")
SEAFOOD = re.compile(r"(?<!\w)(?:hải sản|seafood|tôm|cua|cá|ốc)(?!\w)")
ALLERGY = re.compile(r"\b(?:di ung|ung|kieng|khong an duoc)\b")
SEAFOOD_WORD = re.compile(r"\b(?:hai san|seafood|tom|cua|oc)\b|\bca\b(?! phe)")
TABS = ("meal", "snack")  # the tabs of places to eat at


@dataclass(frozen=True)
class Diet:
    vegetarian: bool = False  # a requirement, hard or soft, for vegetarian / vegan food
    seafood_free: bool = False  # a seafood allergy or aversion the user told

    def __bool__(self) -> bool:
        return self.vegetarian or self.seafood_free


def wanted(si, profile, unmapped=()) -> Diet:
    veg = any(r.feature in VEG_FEATURES and r.value == "yes" and r.op == "eq" for r in si.hard_filters)
    veg = veg or any(w.feature in VEG_FEATURES and w.value == "yes" and w.weight > 0 for w in si.soft_weights)
    veg = veg or any(x.feature in VEG_FEATURES and x.value == "yes" and x.weight > 0 for x in profile.soft)
    notes = [squash(n) for n in (*si.unmapped, *unmapped)]
    seafood = any(ALLERGY.search(n) and SEAFOOD_WORD.search(n) for n in notes)
    return Diet(veg, seafood)


def tiers(region, ids, diet: Diet) -> dict[str, int]:
    """0 a place that calls itself vegetarian; 1 nothing against the diet; 2 vegetarian wanted but not verified (soft only:
    a hard requirement keeps those out of the list); 3 the place says it serves what the diet excludes. Places outside
    the eating tabs are not asked."""
    if not diet:
        return {}
    rows = [region.index[p] for p in ids if p in region.index]
    places = region.places
    names, cats = places["name"].to_list(), places["category"].to_list()
    yes = np.zeros(len(region.ids), dtype=bool)
    if diet.vegetarian:
        for f in VEG_FEATURES:
            col = region.feature(f)
            yes |= col.exists & col.firm & col.eq("yes")
    out = {}
    for i in rows:
        text = f"{names[i] or ''} {cats[i] or ''}".casefold()
        dedicated = bool(DEDICATED.search(text))
        verified = bool(yes[i]) if diet.vegetarian else True
        if diet.vegetarian and dedicated:
            tier = 0
        elif not dedicated and ((diet.vegetarian and MEAT.search(text)) or (diet.seafood_free and SEAFOOD.search(text))):
            tier = 3
        else:
            tier = 1 if verified else 2
        out[region.ids[i]] = tier
    return out


def note(tier: int, diet: Diet) -> str | None:
    if tier == 3:
        return ("Quán tự giới thiệu là nơi món mặn: món chay có thể ít" if diet.vegetarian
                else "Quán tự giới thiệu là nơi hải sản: bạn đã nói dị ứng hải sản")
    if tier == 2:
        return "Chưa xác minh được món chay ở đây"
    return None
