"""Order of the stops inside one day: every permutation up to exact_n stops, else nearest neighbour + 2-opt + or-opt.

Both are deterministic: ties keep the first order found, and the input ids are sorted before anything is tried.
"""

from dataclasses import replace
from itertools import permutations

from .model import DayResult
from .schedule import DayCtx, simulate


def order_day(ids: list[str], ctx: DayCtx, shrink: bool = True) -> DayResult:
    ctx = replace(ctx, allow_shrink=ctx.allow_shrink and shrink)
    ids = sorted(ids)
    if len(ids) <= 1:
        return simulate(ids, ctx)
    if len(ids) <= ctx.cfg.exact_n:
        best = None
        for perm in permutations(ids):
            r = simulate(list(perm), ctx)
            if best is None or r.key < best.key:
                best = r
        return replace(best, method="exact")
    return replace(_heuristic(ids, ctx), method="heuristic")


def _nearest_neighbour(ids: list[str], ctx: DayCtx) -> list[str]:
    left, order, here = list(ids), [], ctx.day.start_node
    while left:
        nxt = min(left, key=lambda x: (ctx.travel.leg(here, x)[0] if here else 0, x))
        order.append(nxt)
        left.remove(nxt)
        here = nxt
    return order


def _heuristic(ids: list[str], ctx: DayCtx) -> DayResult:
    order = _nearest_neighbour(ids, ctx)
    best = simulate(order, ctx)
    n = len(order)
    for _ in range(ctx.cfg.improve_passes):
        improved = False
        for i in range(n - 1):                      # 2-opt: reverse a stretch
            for j in range(i + 1, n):
                cand = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                r = simulate(cand, ctx)
                if r.key < best.key:
                    order, best, improved = cand, r, True
        for i in range(n):                          # or-opt: move one stop elsewhere
            for j in range(n):
                if i == j:
                    continue
                cand = order[:]
                cand.insert(j, cand.pop(i))
                r = simulate(cand, ctx)
                if r.key < best.key:
                    order, best, improved = cand, r, True
        if not improved:
            break
    return best
