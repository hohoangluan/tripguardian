"""Category groups of Maps places (config/category_defaults.yaml), shared by crawl, observe and aggregate.

A Maps category goes to the first group whose `match` words it contains (lower case); no match -> the last group.
"""

from functools import cache

import yaml

from .crawl.common.files import ROOT

PATH = ROOT / "config" / "category_defaults.yaml"


@cache
def defaults() -> dict:
    return yaml.safe_load(PATH.read_text(encoding="utf-8"))


def group(category: str | None) -> dict:
    c = (category or "").casefold()
    groups = defaults()["groups"]
    return next((g for g in groups if any(m in c for m in g["match"])), groups[-1])
