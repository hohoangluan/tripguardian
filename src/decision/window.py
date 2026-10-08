"""The window of places shown per display group, and how it survives a new ranking (docs/PLACE_DECISION.md §9.4):
places that still match stay where they are, freed slots take the best new places, a mostly stale window is
replaced whole."""


def _change(old: list[str], new: list[str], replaced_all: bool) -> dict:
    o, n = set(old), set(new)
    return {"kept": len(o & n), "added": len(n - o), "removed": len(o - n), "replaced_all": replaced_all}


def merge(old: list[str], ranked: list[str], pinned: set[str], cfg) -> tuple[list[str], dict]:
    if not old:
        win = ranked[: cfg.page_size]
        return win, _change([], win, False)
    pos = {pid: i for i, pid in enumerate(ranked)}
    limit = int(cfg.keep_factor * len(old))
    keep = {p for p in old if p in pinned or pos.get(p, limit) < limit}
    size = min(len(old), len(ranked) + len(pinned - set(ranked)))
    replaced_all = len(keep) < cfg.replace_below * len(old)
    if replaced_all:  # mostly stale: only the user's own picks keep their slots
        keep = {p for p in old if p in pinned}
    fresh = iter([p for p in ranked if p not in keep])
    win = []
    for p in old:
        if p in keep:
            win.append(p)
        elif (nxt := next(fresh, None)) is not None:
            win.append(nxt)
    while len(win) < size and (nxt := next(fresh, None)) is not None:
        win.append(nxt)
    return win, _change(old, win, replaced_all)


def extend(window: list[str], ranked: list[str], cfg) -> list[str]:
    have = set(window)
    return window + [p for p in ranked if p not in have][: cfg.page_size]
