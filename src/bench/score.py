"""Field verdicts of one run against its hidden trip, and the per-style summary (docs/plans/BENCH.md §Chấm điểm)."""

from statistics import mean

from .hidden import HiddenTrip
from .users import budget_bucket

VERDICTS = ("correct", "wrong", "missing", "invented", "ok_unknown", "inferred", "unreachable", "n/a")
CHIP_SIGNALS = {"elderly", "kids"}          # the only body signals a chip raises (who:parents, who:kids)


def verdict(truth, got, *, mark: bool = False, unreachable: bool = False, same=None) -> str:
    same = same or (lambda a, b: a == b)
    if truth is None:
        return "ok_unknown" if got is None else "inferred" if mark else "invented"
    if got is not None and same(truth, got):
        return "correct"
    if got is None:
        return "unreachable" if unreachable else "missing"
    return "wrong"


def _marks(understanding: dict | None) -> dict[str, bool]:
    if not understanding:
        return {}
    out = {r["target"]: r["mark"] for r in understanding.get("trip", [])}
    for k in ("purpose", "pace", "crowd_tolerance", "novelty", "budget_vnd"):
        if understanding.get(k):
            out[k] = understanding[k]["mark"]
    return out


def score(t: HiddenTrip, style: str, si: dict, understanding: dict | None, derived_soft: set[str],
          base_card: bool, chip_loves: set[str]) -> list[dict]:
    """One row per scored field. derived_soft: soft keys the system wrote as a side effect (inferred / another
    card's chip). base_card: the base card was shown. chip_loves: love keys a chip can express."""
    tapper = style == "tapper"
    ctx = si["context"]
    mk = _marks(understanding)
    rows = []

    def add(field, truth, got, **kw):
        rows.append({"field": field, "truth": "" if truth is None else truth, "got": "" if got is None else got,
                     "verdict": verdict(truth, got, mark=mk.get(field.split(":")[0], False), **kw)})

    add("days", t.days, ctx["days"], unreachable=tapper and not 1 <= t.days <= 5)
    truth_date = (t.dates.start_date.isoformat() if t.dates.start_date else f"month:{t.dates.month}" if t.dates.month
                  else None)
    got_date = ctx["start_date"] or (f"month:{ctx['month']}" if ctx["month"] else None)
    rows.append({"field": "dates", "truth": truth_date or "", "got": got_date or "",
                 "verdict": verdict(truth_date, got_date, mark=mk.get("start_date", mk.get("month", False)),
                                    unreachable=tapper and t.dates.kind == "month")})
    add("companions", ",".join(sorted(t.companions)), ",".join(sorted(ctx["companions"])) or None)
    add("people", t.people, ctx["people"], unreachable=tapper)
    add("mobility", t.mobility, ctx["mobility"])
    add("base", "present" if t.base else None, "present" if ctx["base"] else None, unreachable=tapper and not base_card)
    if understanding is None:
        rows.append({"field": "purpose", "truth": t.purpose or "", "got": "", "verdict": "n/a"})
    else:
        add("purpose", t.purpose, (understanding.get("purpose") or {}).get("value"))
    add("pace", t.pace, si["pace"]["level"])
    add("crowd_tolerance", t.crowd_tolerance, si["pace"]["crowd_tolerance"])
    add("novelty", t.novelty, si["novelty"]["level"])
    add("budget_vnd", t.budget_vnd, ctx["budget_vnd"], same=lambda a, b: budget_bucket(a) == budget_bucket(b))

    soft = {f"{w['feature']}={w['value']}": w for w in si["soft_weights"] if not w["context"]}
    for key in t.loves:
        w = soft.get(key)
        add(f"love:{key}", 1, w["weight"] if w else None, unreachable=tapper and key not in chip_loves)
    for key in t.avoids:
        w = soft.get(key)
        add(f"avoid:{key}", -1, w["weight"] if w else None, unreachable=tapper)
    for key, w in sorted(soft.items()):
        if key in t.loves or key in t.avoids or w["weight"] == 0:
            continue
        derived = w["source"] != "user" or key in derived_soft
        rows.append({"field": f"extra:{key}", "truth": "", "got": w["weight"],
                     "verdict": "inferred" if derived else "invented"})

    got_hard = {(h["feature"], h["op"], h["value"]) for h in si["hard_filters"]}
    reach = bool(CHIP_SIGNALS & set(t.signals))
    for h in t.hard:
        key = (h.feature, h.op, h.value)
        effort = h.feature != "vegetarian_options"
        add(f"hard:{h.feature}", "present", "present" if key in got_hard else None,
            unreachable=tapper and not (effort and reach))
    for f, op, v in sorted(got_hard - {(h.feature, h.op, h.value) for h in t.hard}):
        rows.append({"field": f"hard_extra:{f}", "truth": "", "got": f"{f} {op} {v}", "verdict": "invented"})

    got_anchor = {a["place_id"]: a["priority"] for a in si["anchors"]}
    for a in t.anchors:
        add(f"anchor:{a.place_id}", a.priority, got_anchor.get(a.place_id), unreachable=tapper)
    for pid in sorted(set(got_anchor) - {a.place_id for a in t.anchors}):
        rows.append({"field": f"anchor_extra:{pid}", "truth": "", "got": got_anchor[pid], "verdict": "invented"})
    return rows


def counts(rows: list[dict]) -> dict:
    n = {v: sum(r["verdict"] == v for r in rows) for v in VERDICTS}
    hard = [r for r in rows if r["field"].startswith("hard:")]
    return {"fields_correct": n["correct"], "fields_wrong": n["wrong"], "fields_missing": n["missing"],
            "fields_invented": n["invented"], "fields_inferred": n["inferred"], "fields_unreachable": n["unreachable"],
            "safety_missed": sum(r["verdict"] == "missing" for r in hard),
            "safety_unreachable": sum(r["verdict"] == "unreachable" for r in hard)}


NUMERIC = ("turns_to_suggestion", "cards_asked", "typed_turns", "fields_correct", "fields_wrong", "fields_missing",
           "fields_invented", "fields_inferred", "fields_unreachable", "unsure_skip_rate", "corrections",
           "safety_missed", "safety_unreachable", "hard_violations", "unknown_hours_share", "warnings", "reached_plan",
           "agent_fallbacks", "model_calls", "unmapped_chips", "ms_total")


def pct(xs: list[float], q: float):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * q))]


def summary(runs: list[dict], typed_ms: dict[str, list[int]]) -> list[dict]:
    out = []
    for style in dict.fromkeys(r["style"] for r in runs):
        rows = [r for r in runs if r["style"] == style and r["status"] == "ok"]
        row = {"style": style, "n": len(rows), "skipped": sum(r["style"] == style and r["status"] != "ok" for r in runs)}
        for k in NUMERIC:
            vals = [r[k] for r in rows if r[k] != ""]
            row[f"mean_{k}"] = round(mean(vals), 3) if vals else ""
        c, w, m = (sum(r[k] for r in rows) for k in ("fields_correct", "fields_wrong", "fields_missing"))
        row["accuracy"] = round(c / (c + w + m), 3) if c + w + m else ""
        for k in ("fields_invented", "safety_missed", "hard_violations", "fields_unreachable", "safety_unreachable"):
            row[f"total_{k}"] = sum(r[k] for r in rows)
        row["reached_plan_rate"] = round(mean(r["reached_plan"] for r in rows), 3) if rows else ""
        ms = typed_ms.get(style, [])
        for name, q in (("p50", .5), ("p90", .9), ("p95", .95)):
            row[f"latency_{name}_ms"] = pct(ms, q) if len(ms) >= 30 else ""
        out.append(row)
    return out
