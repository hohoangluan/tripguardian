"""How many nights the trip sleeps in the city: the one place that answers it for Decision and Planning."""

from collections.abc import Mapping


def nights(ctx) -> int:
    """ctx: Search Input context, as a dict or as the Context object. The user's own number when the trip has one
    ("3 ngày 3 đêm" -> 3, "1 ngày 0 đêm" -> 0); a trip that only gave days sleeps the nights between them, days - 1."""
    get = ctx.get if isinstance(ctx, Mapping) else lambda key: getattr(ctx, key, None)
    stated = get("nights")
    if stated is not None:
        return max(int(stated), 0)
    return max((get("days") or 1) - 1, 0)
