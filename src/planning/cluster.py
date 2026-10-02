"""Clusters of places that are close in real travel time: the unit a day is built from.

Area of the serving record first (complete-link inside it), then a cross-area merge for clusters that touch. A
cluster too big for a day is split in two around its farthest pair, repeatedly, so a day is never one lump.
"""

from .travel import Travel


def distance(a: str, b: str, travel: Travel) -> int:
    return max(travel.leg(a, b)[0], travel.leg(b, a)[0])


def _link(clusters: list[list[str]], travel: Travel, limit: int) -> list[list[str]]:
    """Merge the closest pair (complete-link: the farthest members decide) while that stays within limit."""
    cs = [sorted(c) for c in clusters]
    while True:
        best = None
        for x in range(len(cs)):
            for y in range(x + 1, len(cs)):
                d = max(distance(a, b, travel) for a in cs[x] for b in cs[y])
                if d <= limit and (best is None or d < best[0]):
                    best = (d, x, y)
        if best is None:
            return cs
        _, x, y = best
        cs[x] = sorted(cs[x] + cs[y])
        del cs[y]


def cluster_places(ids: list[str], area_of: dict, travel: Travel, cfg) -> list[list[str]]:
    groups: dict = {}
    for i in sorted(ids):
        groups.setdefault(area_of.get(i) or "", []).append(i)
    clusters: list[list[str]] = []
    for key in sorted(groups):
        clusters += _link([[i] for i in groups[key]], travel, cfg.cluster_max_min)
    clusters = _link(clusters, travel, cfg.cluster_merge_min)
    return sorted(clusters, key=lambda c: c[0])


def split_to_fit(clusters: list[list[str]], load_of, cap: int, travel: Travel) -> list[list[str]]:
    """load_of(ids) -> minutes. Split every cluster whose load exceeds cap around its farthest pair."""
    def split(c: list[str]) -> list[list[str]]:
        if len(c) < 2 or load_of(c) <= cap:
            return [c]
        _, a, b = max(((distance(x, y, travel), x, y) for x in c for y in c if x < y), key=lambda t: (t[0], t[1], t[2]))
        ga = [x for x in c if distance(x, a, travel) <= distance(x, b, travel)]
        gb = [x for x in c if x not in ga]
        if not gb:
            return [c]
        return split(sorted(ga)) + split(sorted(gb))

    out = [part for c in clusters for part in split(c)]
    return sorted(out, key=lambda c: c[0])
