"""repair_day (docs/P4_PLANNING.md §Guardrail "Không xáo lịch âm thầm"): the order of one day right after a
user act touched its membership, penalized for reshuffling a stop that was already there. Reuses simulate()'s own
notion of a valid day (DayResult.key: fewer violations first) -- the diff penalty only breaks ties among orders that
are already equally good, it never trades validity away to stay close to the old order.
"""

from dataclasses import replace
from itertools import permutations

from .model import DayResult
from .schedule import DayCtx, simulate
from .session import ActionError
from .settings import Settings


class RepairError(ActionError):
    """A locked place would have to leave its day; refuse so the caller can ask the user first."""


def _diff(order: tuple[str, ...], prev: tuple[str, ...]) -> int:
    """Positions where two stops that both existed before now disagree on their relative order; 0 when every old
    stop keeps its old sequence (a brand-new stop may land anywhere at no penalty)."""
    common_prev = [i for i in prev if i in order]
    common_new = [i for i in order if i in prev]
    return sum(a != b for a, b in zip(common_prev, common_new))


def _key(r: DayResult, prev: tuple[str, ...], weight: float) -> tuple:
    """Fewer violations first, then fewer missed meals, then end time -- with the diff penalty folded into the end
    time itself so it is a real, comparable cost, not a 4th tuple slot that Python's tuple comparison would only
    ever reach on an exact end-time tie (it short-circuits at the first unequal element)."""
    violations, meals, end = r.key
    return (violations, meals, end + weight * _diff(r.order, prev))


def _seed_order(ids: list[str], ctx: DayCtx, prev: tuple[str, ...]) -> list[str]:
    """Keep the stops that were already in the day in their old order; walk the new ones on by nearest neighbour
    from the last kept stop (or the day's start when none were kept)."""
    kept = [i for i in prev if i in ids]
    rest = [i for i in ids if i not in prev]
    if not rest:
        return kept
    left, here, tail = rest[:], (kept[-1] if kept else ctx.day.start_node), []
    while left:
        nxt = min(left, key=lambda x: (ctx.travel.leg(here, x)[0] if here else 0, x))
        tail.append(nxt)
        left.remove(nxt)
        here = nxt
    return kept + tail


def repair_day(ids: list[str], ctx: DayCtx, prev_order: tuple[str, ...] | None, locked: set[str],
               cfg: Settings) -> DayResult:
    """ids: the day's new membership. prev_order: its order right before the act (None for a day repair_day has
    never touched, which costs no penalty -- the same as a fresh route.order_day)."""
    ids = sorted(ids)
    prev = prev_order or ()
    missing_locked = (set(prev) & locked) - set(ids)
    if missing_locked:
        raise RepairError(f"locked place(s) {sorted(missing_locked)} cannot leave the day")
    weight = cfg.repair_diff_weight
    if len(ids) <= 1:
        return simulate(ids, ctx)
    if len(ids) <= cfg.exact_n:
        best = None
        for perm in permutations(ids):
            r = simulate(list(perm), ctx)
            k = _key(r, prev, weight)
            if best is None or k < best[0]:
                best = (k, r)
        return replace(best[1], method="exact")
    order = _seed_order(ids, ctx, prev)
    best = simulate(order, ctx)
    n = len(order)
    for _ in range(cfg.improve_passes):
        improved = False
        for i in range(n - 1):
            for j in range(i + 1, n):
                cand = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                r = simulate(cand, ctx)
                if _key(r, prev, weight) < _key(best, prev, weight):
                    order, best, improved = cand, r, True
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                cand = order[:]
                cand.insert(j, cand.pop(i))
                r = simulate(cand, ctx)
                if _key(r, prev, weight) < _key(best, prev, weight):
                    order, best, improved = cand, r, True
        if not improved:
            break
    return replace(best, method="heuristic")
