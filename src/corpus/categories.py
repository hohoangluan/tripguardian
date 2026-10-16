"""Category groups of Maps places (config/category_defaults.yaml), shared by crawl, observe and aggregate.

A Maps category goes to the group whose `match` phrase it contains as whole words, the longest phrase winning ("quán
bia sân vườn" is a bar, not a garden; "chèo thuyền" holds no "chè"); a tie goes to the group listed first. A category
no phrase matches is read again from the place's name when there is one ("Dịch vụ ô tô riêng" named "Vườn Hồng ...");
still nothing -> the last group.
"""

import re
import unicodedata
from functools import cache

import yaml

from .crawl.common.files import ROOT

PATH = ROOT / "config" / "category_defaults.yaml"


@cache
def defaults() -> dict:
    return yaml.safe_load(PATH.read_text(encoding="utf-8"))


def _words(text: str | None) -> tuple[str, ...]:
    t = unicodedata.normalize("NFC", text or "").casefold()  # Maps sends some categories as NFD
    return tuple(re.findall(r"\w+", t))


@cache
def _phrases() -> list[tuple[int, tuple[str, ...]]]:
    """(group index, phrase words) for every match phrase."""
    return [(i, _words(m)) for i, g in enumerate(defaults()["groups"]) for m in g["match"]]


def _best(text: str | None) -> dict | None:
    words = _words(text)
    if not words:
        return None
    best = None  # (phrase length, -group index)
    for i, p in _phrases():
        n = len(p)
        if any(words[k:k + n] == p for k in range(len(words) - n + 1)) and (best is None or (n, -i) > best):
            best = (n, -i)
    return defaults()["groups"][-best[1]] if best else None


def group(category: str | None, name: str | None = None) -> dict:
    return _best(category) or _best(name) or defaults()["groups"][-1]
