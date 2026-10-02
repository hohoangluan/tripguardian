"""Planning objectives (docs/ARCHITECTURE.md §10): which ones a trip calls for, and how a laid-out trip scores on each.

Every objective is a rule: its day-split weights (config objective_weights) and a score where lower is better, ties
broken by total travel. No objective changes what validate checks.
"""

from .days import exposed_risk, pref_risk, repeats
from .settings import Settings
from .traits import exposure

LABEL = {"least_travel": "Ít di chuyển", "low_cost": "Chi phí thấp", "weather_robust": "Vững trước thời tiết",
         "diverse": "Đa dạng trải nghiệm", "preference_fit": "Hợp sở thích"}


def choose(trip_context: dict, rains: list, prefs: dict, cfg: Settings) -> list[str]:
    """At most max_variants objectives, in objective_order, among those the trip calls for. rains: rain probability
    of each day (None = no forecast); prefs: place id -> preference."""
    ctx = trip_context["context"]
    pace = (trip_context.get("pace") or {}).get("level") or "normal"
    called = {
        "least_travel": True,
        "weather_robust": any(r is not None and r >= cfg.rain_high for r in rains),
        "preference_fit": any(v > 0 for v in prefs.values()),
        "low_cost": ctx.get("budget_vnd") is not None,
        "diverse": pace != "slow",
    }
    return [o for o in cfg.objective_order if called[o]][: cfg.max_variants]


def metrics(ctxs: list, results: list) -> dict:
    """What every objective is scored on, measured on the finished days."""
    m = {"travel_min": 0, "cost_vnd": 0, "cost_unknown": 0, "rain_exposed": 0.0, "exposure_unknown": 0,
         "repeats": 0, "pref_risk": 0.0}
    for cx, r in zip(ctxs, results):
        ids = list(r.order)
        m["travel_min"] += r.travel_min
        for i in ids:
            p = cx.places[i]
            if p.cost_vnd is None:
                m["cost_unknown"] += 1
            else:
                m["cost_vnd"] += p.cost_vnd
            m["exposure_unknown"] += exposure(p) is None
        m["rain_exposed"] += exposed_risk(ids, cx)
        m["repeats"] += repeats(ids, cx)
        m["pref_risk"] += pref_risk(ids, cx)
    m["rain_exposed"] = round(m["rain_exposed"], 3)
    m["pref_risk"] = round(m["pref_risk"], 3)
    return m


def score(objective: str, m: dict) -> tuple:
    """Lower is better. Cost is per person over known prices; lodging joins it in P5."""
    main = {"least_travel": m["travel_min"], "low_cost": m["cost_vnd"], "weather_robust": m["rain_exposed"],
            "diverse": m["repeats"], "preference_fit": m["pref_risk"]}[objective]
    return main, m["travel_min"]


def add_lodging_cost(m: dict, price_vnd: int | None, nights: int) -> dict:
    """metrics() with a lodging candidate's cost merged into cost_vnd / cost_unknown over the whole stay."""
    out = dict(m)
    if price_vnd is None:
        out["cost_unknown"] += 1
    else:
        out["cost_vnd"] += price_vnd * nights
    return out
