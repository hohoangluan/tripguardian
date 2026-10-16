"""Order of the stops inside one day: every permutation up to exact_n stops, else nearest neighbour + 2-opt + or-opt.

Both are deterministic: ties keep the first order found, and the input ids are sorted before anything is tried.
"""

from dataclasses import replace
from itertools import permutations

from .model import DayResult
from .schedule import DayCtx, _SimulationCache, simulate



def order_day(ids: list[str], ctx: DayCtx, seed: list[str] | None = None) -> DayResult:
    """seed: an order to start the search from (the day layout's insertion order). With one, a day of more than
    realistic.seeded_exact_n stops is ordered by the local search from the better of the seed and nearest neighbour
    instead of trying every permutation (7 stops = 5,040 clocks), which the layout's fuller days made too slow. A day
    that local search leaves a near miss (_orderable: it only runs a little late) still gets every permutation up to
    exact_n, so only such a day pays for it."""
    ids = sorted(ids)
    if len(ids) <= 1:
        return simulate(ids, ctx)
    cache = _SimulationCache(ids, ctx)
    rc = ctx.cfg.realistic
    if seed is not None and sorted(seed) != ids:
        seed = None                 # not an order of these stops: no seed
    if seed is not None and rc["seeded_exact_n"] < len(ids):
        quick = replace(_heuristic(ids, ctx, cache, seed, rc["seeded_passes"]), method="heuristic")
        if len(ids) > ctx.cfg.exact_n or not quick.violations or not _orderable(quick, ids, ctx):
            return quick
    if len(ids) <= ctx.cfg.exact_n:
        best = None
        for perm in permutations(ids):
            r = simulate(list(perm), ctx, _cache=cache)
            if best is None or r.key < best.key:
                best = r
        return replace(best, method="exact")
    return replace(_heuristic(ids, ctx, cache, seed), method="heuristic")


def _orderable(r: DayResult, ids: list[str], ctx: DayCtx) -> bool:
    """Whether the day is a near miss that another order of the same stops may fit: it only runs late, and by no more
    than any order can save (its idle time and the road above the least any order needs: each stop reached by its
    nearest way in, the end by the nearest stop). A day that also misses a stop's hours or a meal, or runs later than
    that, is overloaded: the layout and the misfit loop handle it, and 720 or 5,040 more clocks would not (measured on
    the review's probe: no day the exhaustive search fits is left unfit; on the composer's edit trials no exhaustive
    run cleared an hours or meal miss)."""
    if not r.violations or any(v.kind != "day_window" for v in r.violations):
        return False
    late = sum(v.minutes for v in r.violations)
    leg = lambda a, b: ctx.travel.leg(a, b)[0] if a and b and a != b else 0
    start, end = ctx.day.start_node, ctx.day.end_node
    least = sum(min(leg(x, p) for x in [start, *ids] if x != p) for p in ids) + min(leg(p, end) for p in ids)
    idle = sum(i.end - i.start for i in r.items if i.kind in {"wait", "free"})
    return late <= max(0, r.travel_min - least) + idle


def _nearest_neighbour(ids: list[str], ctx: DayCtx) -> list[str]:
    left, order, here = list(ids), [], ctx.day.start_node
    while left:
        nxt = min(left, key=lambda x: (ctx.travel.leg(here, x)[0] if here else 0, x))
        order.append(nxt)
        left.remove(nxt)
        here = nxt
    return order


def _heuristic(ids: list[str], ctx: DayCtx, cache: _SimulationCache, seed: list[str] | None = None,
               passes: int | None = None) -> DayResult:
    order = _nearest_neighbour(ids, ctx)
    best = simulate(order, ctx, _cache=cache)
    if seed is not None and list(seed) != order:
        tried = simulate(list(seed), ctx, _cache=cache)
        if tried.key < best.key:
            order, best = list(seed), tried
    n = len(order)
    # From the layout's own order a day is near its best already: a few sweeps of the local search are enough.
    for _ in range(ctx.cfg.improve_passes if passes is None else min(ctx.cfg.improve_passes, passes)):
        improved = False
        for i in range(n - 1):                      # 2-opt: reverse a stretch
            for j in range(i + 1, n):
                cand = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                r = simulate(cand, ctx, _cache=cache)
                if r.key < best.key:
                    order, best, improved = cand, r, True
        for i in range(n):                          # or-opt: move one stop elsewhere
            for j in range(n):
                if i == j:
                    continue
                cand = order[:]
                cand.insert(j, cand.pop(i))
                r = simulate(cand, ctx, _cache=cache)
                if r.key < best.key:
                    order, best, improved = cand, r, True
        if not improved:
            break
    return best
