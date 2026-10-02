"""Which cluster goes on which day. Dynamic programming over subsets of clusters: exact, so the same input always gives
the same split. Past max_days / max_clusters it falls back to a greedy split and says so.
"""

from .places import windows_on
from .schedule import DayCtx, pin_window
from .traits import exposure, kind_group


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


def day_load(ids: list[str], places: dict, cfg, pace: str) -> int:
    """load_of plus what a real day also spends: the buffer after each stop and the meals."""
    return load_of(ids, places, cfg, pace) + len(ids) * cfg.buffer_min[pace] + cfg.meals_per_day * cfg.meal_min


def _can_start(p, ctx: DayCtx) -> bool:
    """Whether the place can be visited at all inside this day: open that weekday, long enough within the day's window,
    and at the time of day its feature needs (a restaurant that opens at 18:00 on a day that ends at 15:00, a
    live-music bar on a day that ends before dark). A sunrise place can pull a later day's start forward."""
    need = p.visit[ctx.cfg.visit_key[ctx.pace]]
    lo, hi = pin_window(p, ctx)
    floor = lo if 0 < lo < ctx.day.start and ctx.day.index > 0 else ctx.day.start
    w = windows_on(p.hours, ctx.day.weekday)
    for o, c in [(0, 1440)] if w is None else w:
        if max(floor, lo, o) <= min(hi, c - need, ctx.day.end - need):
            return True
    return False


def blocked(ids: list[str], ctx: DayCtx) -> int:
    """How many of the places cannot be visited at all inside this day."""
    return sum(not _can_start(ctx.places[i], ctx) for i in ids)


def isolate_constrained(clusters: list[list[str]], ctxs: list[DayCtx]) -> list[list[str]]:
    """A place that some days can host and others cannot leaves its cluster, so the day assignment can put it on the
    day it fits instead of dragging its neighbours there (or giving up on all of them)."""
    out = []
    for c in clusters:
        loose = [i for i in c if 0 < sum(not _can_start(ctxs[0].places[i], cx) for cx in ctxs) < len(ctxs)]
        rest = [i for i in c if i not in loose]
        out += ([rest] if rest else []) + [[i] for i in loose]
    return sorted(out, key=lambda c: c[0])


def day_cost(ids: list[str], ctx: DayCtx) -> float:
    cfg, w = ctx.cfg, ctx.cfg.weights
    target = cfg.per_day[ctx.pace]
    if not ids:
        return w["count"] * target
    closed = blocked(ids, ctx)
    tour = _tour(ids, ctx)
    over = max(0, day_load(ids, ctx.places, cfg, ctx.pace) + tour - (ctx.day.end - ctx.day.start))
    shorter = 0.001 * len(ids) * (1440 - (ctx.day.end - ctx.day.start))     # equal costs: the longer day takes more
    return (w["travel"] * tour + w["overflow"] * over + w["count"] * abs(len(ids) - target) + w["closed"] * closed
            + shorter + w.get("exposed", 0) * exposed_risk(ids, ctx) + w.get("repeat", 0) * repeats(ids, ctx)
            + w.get("pref_risk", 0) * pref_risk(ids, ctx))


def day_risk(ctx: DayCtx) -> float:
    """How likely the day is to go wrong for a place on it: its rain probability (0 when unknown) plus how much
    shorter than a full day it is (an arrival or departure day)."""
    full = ctx.cfg.day_end - ctx.cfg.day_start
    short = max(0.0, 1 - (ctx.day.end - ctx.day.start) / full) if full > 0 else 0.0
    return (ctx.rain or 0.0) + short


def exposed_risk(ids: list[str], ctx: DayCtx) -> float:
    """Weather-exposed places on the day, times its rain probability. No forecast -> 0."""
    return sum(exposure(ctx.places[i]) == "exposed" for i in ids) * (ctx.rain or 0.0)


def repeats(ids: list[str], ctx: DayCtx) -> int:
    """Places of a kind already on the day: 0 when every place is a different kind. Unknown kinds do not repeat."""
    kinds = [kind_group(ctx.places[i]) for i in ids]
    known = [k for k in kinds if k]
    return len(known) - len(set(known))


def pref_risk(ids: list[str], ctx: DayCtx) -> float:
    """How much of what the user wants most sits on a risky day."""
    prefs = ctx.prefs or {}
    return sum(prefs.get(i, 0.0) for i in ids) * day_risk(ctx)


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
