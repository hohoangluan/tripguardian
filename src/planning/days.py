"""Which cluster goes on which day. Dynamic programming over subsets of clusters: exact, so the same input always gives
the same split. Past max_days / max_clusters it falls back to a greedy split and says so.
"""

from .places import windows_on
from .schedule import DayCtx


def _tour(ids: list[str], ctx: DayCtx) -> int:
    """Nearest-neighbour path minutes from the day's start through ids to its end: a cheap stand-in for route.py."""
    travel, here, total, left = ctx.travel, ctx.day.start_node, 0, sorted(ids)
    while left:
        nxt = min(left, key=lambda x: (travel.leg(here, x)[0] if here else 0, x))
        total += travel.leg(here, nxt)[0] if here else 0
        here = nxt
        left.remove(nxt)
    if here and ctx.day.end_node:
        total += travel.leg(here, ctx.day.end_node)[0]
    return total


def load_of(ids: list[str], places: dict, cfg, pace: str) -> int:
    """Minutes a set of places asks of a day before travel between clusters: visits plus moving inside the cluster."""
    return sum(places[i].visit[cfg.visit_key[pace]] + cfg.intra_leg_min for i in ids)


def blocked(ids: list[str], ctx: DayCtx) -> int:
    """How many of the places cannot be visited at all inside this day: closed that weekday, or not open long enough
    within the day's window (a restaurant that opens at 18:00 on a day that ends at 15:00)."""
    n = 0
    for i in ids:
        p = ctx.places[i]
        w = windows_on(p.hours, ctx.day.weekday)
        need = p.visit[ctx.cfg.visit_key[ctx.pace]]
        if w is not None and not any(min(c, ctx.day.end) - max(o, ctx.day.start) >= need for o, c in w):
            n += 1
    return n


def day_cost(ids: list[str], ctx: DayCtx) -> float:
    cfg, w = ctx.cfg, ctx.cfg.weights
    target = cfg.per_day[ctx.pace]
    if not ids:
        return w["count"] * target
    closed = blocked(ids, ctx)
    tour = _tour(ids, ctx)
    over = max(0, load_of(ids, ctx.places, cfg, ctx.pace) + tour - (ctx.day.end - ctx.day.start))
    return w["travel"] * tour + w["overflow"] * over + w["count"] * abs(len(ids) - target) + w["closed"] * closed


def assign_days(clusters: list[list[str]], ctxs: list[DayCtx]) -> tuple[list[list[str]], str | None]:
    """-> (place ids of each day, flag). flag is "days_fallback" when the exact search was not used."""
    cfg, n, d_count = ctxs[0].cfg, len(clusters), len(ctxs)
    if n == 0:
        return [[] for _ in ctxs], None
    if d_count > cfg.max_days or n > cfg.max_clusters:
        return _greedy(clusters, ctxs), "days_fallback"

    def members(mask: int) -> list[str]:
        return [i for k in range(n) if mask >> k & 1 for i in clusters[k]]

    inf = float("inf")
    dp = [[inf] * (1 << n) for _ in range(d_count + 1)]
    back = [[0] * (1 << n) for _ in range(d_count + 1)]
    dp[0][0] = 0.0
    cost: dict = {}
    for d in range(1, d_count + 1):
        for mask in range(1 << n):
            sub = mask
            while True:
                prev = dp[d - 1][mask ^ sub]
                if prev < inf:
                    if (d, sub) not in cost:
                        cost[(d, sub)] = day_cost(members(sub), ctxs[d - 1])
                    c = prev + cost[(d, sub)]
                    if c < dp[d][mask]:
                        dp[d][mask], back[d][mask] = c, sub
                if sub == 0:
                    break
                sub = (sub - 1) & mask
    out, mask = [[] for _ in ctxs], (1 << n) - 1
    for d in range(d_count, 0, -1):
        sub = back[d][mask]
        out[d - 1] = members(sub)
        mask ^= sub
    return out, None


def _greedy(clusters: list[list[str]], ctxs: list[DayCtx]) -> list[list[str]]:
    """Biggest cluster first, onto the day where the fewest of its places are blocked, then the least load so far
    (ties: the earlier day)."""
    cx = ctxs[0]
    size = lambda c: load_of(c, cx.places, cx.cfg, cx.pace)
    out = [[] for _ in ctxs]
    for c in sorted(clusters, key=lambda c: (-size(c), c[0])):
        d = min(range(len(ctxs)), key=lambda k: (blocked(c, ctxs[k]), load_of(out[k], cx.places, cx.cfg, cx.pace), k))
        out[d] += c
    return out
