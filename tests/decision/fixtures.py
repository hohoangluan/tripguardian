"""Serving-record and Search Input builders for decision tests (shape: src/corpus/serving/record.py build())."""

from datetime import date

from corpus.ontology import load

from trip import SearchInput

ONT = load()
MONDAY = date(2026, 12, 14)
ALL_DAY = {d: [["07:00", "22:00"]] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}


def feat(value, n=3, status="VERIFIED", dist=None, by_context=None, rate=0.1, agreement=1.0):
    return {"value": value, "distribution": dist or {value: n}, "status": status,
            "reason": None if status == "VERIFIED" else "unmeasured_precision", "n": n, "mention_rate": rate,
            "confidence": {"independent_sources": n, "agreement": agreement, "freshness_days": 10,
                           "source_types": ["provider"]},
            "by_context": by_context or {}, "precision": None, "evidence": ["x:1"]}


def srec(fid, name=None, features=None, group="cafe", category="Quán cà phê", lat=11.94, lng=108.44, area="area-1",
         hours=ALL_DAY, hours_status="VERIFIED", usable=("experience", "meal", "backup"), voices=30,
         crowd_by_time=None, price=None, visit=(45, 75, 150), dup=None, entry_fee=None, rating_trend=None):
    rec = {"id": fid, "status": "VERIFIED", "status_reason": None,
           "identity": {"name": name or f"Nơi {fid}", "kind": "POI", "category": category, "category_group": group,
                        "lat": lat, "lng": lng, "address": "Đà Lạt", "area": area},
           "operation": {"hours": {"value": hours, "status": hours_status, "as_of": "2026-09-30"} if hours else None,
                         "price_per_person": {"value": price, "status": "VERIFIED", "as_of": "2026-09-30"} if price else None,
                         "entry_fee": entry_fee,
                         "visit_minutes": {"short": visit[0], "typical": visit[1], "long": visit[2],
                                           "source": "category_default", "n": 0, "kind": "estimate"},
                         "booking": None, "crowd_by_time": crowd_by_time},
           "experience": {}, "environment": {}, "service": {}, "effort": {}, "suitability": {},
           "effort_hint": {"value": "unknown", "kind": "estimate"}, "usable_as": list(usable),
           "provenance": {"as_of": "2026-09-30", "coverage": {}, "voices": voices, "rating_trend": rating_trend,
                          "inputs": []},
           "near_duplicate_group": dup}
    for f, v in (features or {}).items():
        rec[ONT.features[f].group][f] = feat(v) if isinstance(v, str) else v
    return rec


def si(**over) -> SearchInput:
    """A valid Search Input; keyword args replace top-level keys, context / pace / novelty are merged."""
    base = {"ontology_version": ONT.version,
            "context": {"start_date": MONDAY.isoformat(), "month": None, "days": 2, "base": None,
                        "mobility": "motorbike", "companions": [], "people": 2, "arrive_at": None, "leave_at": None,
                        "day_end": None, "budget_vnd": None, "experience": None},
            "hard_filters": [], "anchors": [], "soft_weights": [],
            "pace": {"level": "normal", "max_leg_min": None, "crowd_tolerance": None},
            "novelty": {"level": None, "visited": []}, "unknowns": [], "unmapped": []}
    for k, v in over.items():
        if k in ("context", "pace", "novelty"):
            base[k] = {**base[k], **v}
        else:
            base[k] = v
    return SearchInput.model_validate(base)


def hard(feature, value, op="ne", policy="exclude"):
    return {"feature": feature, "op": op, "value": value, "unknown_policy": policy}


def love(feature, value="present", weight=1, context=None):
    return {"feature": feature, "value": value, "context": context, "weight": weight, "source": "user"}
