"""Helpers shared by tests/trip (a module, not a package: tests/trip has no __init__)."""


def rec(i, name, feats, hours=None, status="signal", needs_review=False):
    """One data/intel/places record; feats: {feature: (top_value, n) or (top_value, n, by_context)}."""
    return {"place_fid": f"0x{i:x}:0x1", "place_name": name,
            "identity": {"category": "Quán cà phê", "lat": 11.94, "lng": 108.45},
            "operation": {"hours": hours},
            "features": {f: {"n": v[1], "top_value": v[0], "status": status, "needs_review": needs_review,
                             "by_context": v[2] if len(v) > 2 else {}} for f, v in feats.items()}}


MONDAY_CLOSED = {"mon": [], "tue": [["07:00", "22:00"]], "wed": [["07:00", "22:00"]], "thu": [["07:00", "22:00"]],
                 "fri": [["07:00", "22:00"]], "sat": [["07:00", "22:00"]], "sun": [["07:00", "22:00"]]}
