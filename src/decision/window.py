"""The page of places shown per tab (docs/PLACE_DECISION.md §9.4): a tab is its ranking cut into pages of page_size,
best first; the user picks the page. A new ranking keeps the page number, and says how much of the page changed."""


def pages(n: int, cfg) -> int:
    return max(1, -(-n // cfg.page_size))


def window(ranked: list[str], page: int, cfg) -> tuple[list[str], int]:
    """(ids of the page, the page actually shown): a page past the end shows the last one."""
    p = min(max(0, page), pages(len(ranked), cfg) - 1)
    return ranked[p * cfg.page_size:(p + 1) * cfg.page_size], p


def change(old: list[str], new: list[str], cfg) -> dict:
    """A tab never shown before has nothing to compare with: no change, so it is not marked "mới"."""
    if not old:
        return {"kept": 0, "added": 0, "removed": 0, "replaced_all": False}
    o, n = set(old), set(new)
    kept = len(o & n)
    return {"kept": kept, "added": len(n - o), "removed": len(o - n),
            "replaced_all": bool(old) and kept < cfg.replace_below * len(old)}
