"""Logistics helpers (docs/TRIP_UNDERSTANDING.md §Hậu cần): the road or airport a trip enters the city by, the route of a
coach or flight, and how a chosen coach / flight sets the day's window and the city's entry / exit.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

from ..infrastructure.settings import Settings
from .state import Base, Evidence, Transit, TripState, Update, apply, settle

CITY = (11.9404, 108.4583)  # Đà Lạt centre (Chợ Đà Lạt), the same point Place Decision measures from
AIRPORT = Base(text="Sân bay Liên Khương", lat=11.7502, lng=108.3672)
BUS_STATION = Base(text="Bến xe Liên tỉnh Đà Lạt", lat=11.9276, lng=108.4446)
MODE_LABEL = {"self": "Tự đi (xe máy, ô tô)", "bus": "Xe khách", "plane": "Máy bay"}


def bearing(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Initial bearing from a to b in degrees, 0 = north, clockwise."""
    la1, la2, dl = math.radians(a[0]), math.radians(b[0]), math.radians(b[1] - a[1])
    y = math.sin(dl) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def entry_road(origin: Base, cfg: Settings) -> Base | None:
    """Driving in: the pass the origin's direction comes in by (config/trip.yaml entry_roads); None without a point."""
    if origin.lat is None or origin.lng is None:
        return None
    deg = bearing(CITY, (origin.lat, origin.lng))
    for r in cfg.entry_roads:
        lo, hi = r["from_deg"], r["to_deg"]
        if (lo <= deg < hi) if lo < hi else (deg >= lo or deg < hi):
            return Base(text=r["text"])
    return None


def nearest_airport(origin: Base, cfg: Settings) -> dict | None:
    if origin.lat is None or origin.lng is None or not cfg.airports:
        return None
    return min(cfg.airports, key=lambda a: (a["lat"] - origin.lat) ** 2 + ((a["lng"] - origin.lng) * math.cos(math.radians(origin.lat))) ** 2)


def last_day(state: TripState) -> date | None:
    start, days = state.start_date.value, state.days.value
    return start + timedelta(days=days - 1) if start and days else None


def route(state: TripState, cfg: Settings) -> tuple[str, str] | None:
    """(from, to) of the trip in: IATA codes for a flight, province names for a coach (its card also carries the
    origin's point, which src/live/buses prefers). None when unknown."""
    origin = state.origin.value
    if origin is None:
        return None
    if state.arrival_mode.value == "plane":
        a = nearest_airport(origin, cfg)
        return (a["iata"], "DLI") if a else None
    if state.arrival_mode.value == "bus":
        return (origin.province or origin.text, "Lâm Đồng")
    return None


def clock_after(t: str, minutes: int) -> str:
    """HH:MM of the ISO time t, minutes later (earlier when negative)."""
    x = datetime.fromisoformat(t) + timedelta(minutes=minutes)
    return f"{x:%H:%M}"


def pick_transit(state: TripState, way: str, t: Transit, cfg: Settings, turn: int) -> TripState:
    """The user chose a coach / flight: it is stored, and the city's entry / exit follow from it. The day's window
    follows too, when the Search Input is compiled (compile.day_window): arrival + buffer, departure − buffer."""
    ev = Evidence(turn=turn, tool=f"transit:{way}")

    def put(field, value):
        return Update(field=field, value=value, source="user", confidence="high", evidence=ev)

    state = apply(state, put(way, t))
    if way == "inbound":
        state = apply(state, put("entry_point", Base(text=t.to_point)))
    else:
        state = apply(state, put("exit_point", Base(text=t.from_point)))
    return settle(state)
