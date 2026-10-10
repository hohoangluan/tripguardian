"""Whether a trip rents its motorbike in the city (docs/P2_TRIP_UNDERSTANDING.md §Hậu cần)."""

from collections.abc import Mapping

from .state import Base, TripState

ARRIVES_WITHOUT_A_VEHICLE = ("bus", "plane")


def rents_bike(ctx) -> bool:
    """ctx: Search Input context, as a dict or as the Context object. A trip that comes in by coach or plane and rides a
    motorbike has to collect one in the city; one that drives in, or rides a car, does not."""
    get = ctx.get if isinstance(ctx, Mapping) else lambda key: getattr(ctx, key, None)
    return get("arrival_mode") in ARRIVES_WITHOUT_A_VEHICLE and get("mobility") == "motorbike"


def rental_params(arrival: str, entry: Base | None) -> dict:
    """Query of the /rentals lookup: the station / airport of `arrival`, or the entry point when it has a point."""
    params = {"mode": arrival}
    if entry is not None and entry.lat is not None and entry.lng is not None:
        params |= {"lat": entry.lat, "lng": entry.lng, "text": entry.text}
    return params


DECLINED_NOTE = ("Bạn không thuê xe nên lịch chỉ đi bộ quanh khu quanh chỗ ở: những nơi xa sẽ không tới được hoặc rất mất "
                 "thời gian. Không có taxi hay xe công nghệ trong lịch; thuê xe máy sẽ đi được xa hơn nhiều.")


def rental_hint(state: TripState) -> dict | None:
    """What the understanding panel shows about renting, or None when it has nothing to say. A trip that arrives by coach
    or plane and has not chosen a car: "suggest" (rental points near the station / airport; `params` are those of the
    /rentals lookup, measured from the entry point when it has a point), or "declined" when it chose to rent nothing
    (the note says how limited the plan is)."""
    arrival, mobility = state.arrival_mode.value, state.mobility.value
    if arrival not in ARRIVES_WITHOUT_A_VEHICLE or mobility == "car":
        return None
    if mobility == "walk":
        return {"status": "declined", "note": DECLINED_NOTE}
    return {"status": "suggest", "params": rental_params(arrival, state.entry_point.value)}
