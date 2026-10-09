"""Saved data from before two changes to the trip fields.

mobility="ride" (Grab, taxi) no longer exists. It is not mapped to another vehicle: unknown is not a choice, so the quiz
asks again. arrive_at / leave_at (the hours the first day opens and the last day closes) are now checkin_at / checkout_at,
the hours the user wants; a coach's or flight's own times stay in `inbound` / `outbound`, whose `arrive_at` is a Transit's.
"""

from typing import Any

_UNKNOWN = {"value": None, "source": "default", "confidence": "low", "status": "unknown", "evidence": []}


def _is_ride_chip(item: Any) -> bool:
    return isinstance(item, dict) and any(
        isinstance(d, dict) and d.get("field") == "mobility" and d.get("value") == "ride" for d in item.get("drafts") or ())


def drop_ride(data: Any) -> Any:
    """A copy of saved JSON data without mobility="ride": a TripState field becomes unknown, a Context value None, and
    a quiz chip that would set it is removed. Everything else is returned as it was."""
    if isinstance(data, dict):
        out = {}
        for key, value in data.items():
            if key == "mobility" and value == "ride":
                out[key] = None
            elif key == "mobility" and isinstance(value, dict) and value.get("value") == "ride":
                out[key] = dict(_UNKNOWN)
            else:
                out[key] = drop_ride(value)
        return out
    if isinstance(data, list):
        return [drop_ride(item) for item in data if not _is_ride_chip(item)]
    return data


_RENAMED = {"arrive_at": "checkin_at", "leave_at": "checkout_at"}


def rename_clock_fields(data: Any) -> Any:
    """A copy of saved JSON data with arrive_at / leave_at renamed, except inside a Transit (it has depart_at)."""
    if isinstance(data, dict):
        keep = "depart_at" in data
        return {(_RENAMED.get(k, k) if not keep else k): rename_clock_fields(v) for k, v in data.items()}
    if isinstance(data, list):
        return [rename_clock_fields(item) for item in data]
    return data


def upgrade(data: Any) -> Any:
    """Saved JSON data of an older version, as the current models read it."""
    return rename_clock_fields(drop_ride(data))
