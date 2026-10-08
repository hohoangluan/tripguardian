"""Backups (docs/PLANNING.md ⓗ, docs/ARCHITECTURE.md §13).

A sensitive visit: weather-exposed on a rainy day · opening hours UNCERTAIN / OUTDATED · ending close to closing time
· far from where its day starts · busy on a peak day · a meal place when shops close for Tết · covered by a warning notice. Its replacements come only from the Decision's backup_pool: close by (rough minutes,
since backups are not in the travel matrix), the same kind, through the hard filters, and not sensitive for the same
reason. None found -> said so, nothing invented. For a delay, each day names the stop to drop first.
"""

from corpus.serving import check

from . import places as pl
from .conditions import advisory_hits, crowd_sensitive, hazard, warned
from .schedule import DayCtx, intervals_for
from .traits import exposure, kind_group
from .travel import km, rough_minutes

REASON_TEXT = {"rain": "ngoài trời vào ngày dự báo mưa", "hours_uncertain": "giờ mở cửa chưa chắc",
               "near_close": "sát giờ đóng cửa", "far": "xa điểm xuất phát của ngày",
               "crowd": "rất đông khách vào ngày này, phải chờ lâu", "holiday_closure": "dịp này nhiều quán đóng cửa hoặc đổi giờ",
               "advisory": "nằm trong vùng có thông báo cảnh báo"}
SHAKY = ("UNCERTAIN", "OUTDATED")


def sensitive(it, cx: DayCtx) -> list[str]:
    """Why one visit item is sensitive, in REASON_TEXT order; [] = it is not."""
    cfg, p = cx.cfg, cx.places[it.place_id]
    out = []
    if cx.wet is not None and cx.wet >= cfg.rain_high and exposure(p) == "exposed":
        out.append("rain")
    if p.hours_status in SHAKY:
        out.append("hours_uncertain")
    if p.hours is not None and any(o <= it.start and it.end <= c and c - it.end < cfg.near_close_min
                                   for o, c in intervals_for(p, cx)):
        out.append("near_close")
    start = cx.day.start_node
    if start and cx.travel.leg(start, p.id)[0] > cfg.far_leg_min:
        out.append("far")
    if cx.cond and cx.cond.crowd == "peak" and crowd_sensitive(p, cx.cond, cfg):
        out.append("crowd")
    if cx.cond and cx.cond.closure_risk and p.kind == "meal":
        out.append("holiday_closure")
    if warned(p, cx.cond):
        out.append("advisory")
    return out


def _fits(b, s, reasons: list[str], cx: DayCtx, hard_filters: list) -> bool:
    if b.kind != s.kind or hazard(b, cx.cond):
        return False
    if "crowd" in reasons and crowd_sensitive(b, cx.cond, cx.cfg):
        return False
    if "advisory" in reasons and advisory_hits(b, cx.cond):
        return False
    if any(hf["op"] == "ne" and check(b.rec, hf["feature"], hf["value"]) == "fail" for hf in hard_filters):
        return False
    if "rain" in reasons and exposure(b) != "sheltered":
        return False
    if ({"hours_uncertain", "holiday_closure"} & set(reasons)) and (b.hours is None or b.hours_status in SHAKY):
        return False
    return pl.windows_on(b.hours, cx.day.weekday) != []        # not closed that day


def backups(ctxs: list[DayCtx], results: list, decision: dict, by_id: dict) -> dict:
    cfg = ctxs[0].cfg
    tc = decision["trip_context"]
    mobility, hard = tc["context"].get("mobility"), tc.get("hard_filters") or []
    confirmed = {c["id"] for c in decision["confirmed"]}
    pool = [b for b in decision.get("backup_pool") or [] if b["id"] not in confirmed]
    entry = {b["id"]: b for b in pool}
    cands, _ = pl.build_places({"confirmed": [{"id": b["id"], "name": b.get("name"), "role": "selected"}
                                              for b in pool]}, by_id, cfg)
    out, on_delay = [], []
    for cx, r in zip(ctxs, results):
        for it in r.items:
            if it.kind != "visit":
                continue
            reasons = sensitive(it, cx)
            if not reasons:
                continue
            s = cx.places[it.place_id]
            alts = []
            for b in cands:
                minutes = rough_minutes(km((s.lat, s.lng), (b.lat, b.lng)), mobility, cfg)
                mine = entry[b.id].get("for") == s.id
                same_kind = mine or (kind_group(b) is not None and kind_group(b) == kind_group(s))
                if minutes <= cfg.backup_radius_min and same_kind and _fits(b, s, reasons, cx, hard):
                    alts.append((not mine, minutes, b.id, b))
            alts.sort(key=lambda a: a[:3])
            out.append({"day": cx.day.index + 1, "place_id": s.id, "name": s.name, "reasons": reasons,
                        "text": ", ".join(REASON_TEXT[x] for x in reasons),
                        "alternatives": [{"id": b.id, "name": b.name, "minutes_rough": m, "for_this": not other,
                                          "reason": entry[b.id].get("reason")}
                                         for other, m, _, b in alts[: cfg.backups_per_place]],
                        "none_text": None if alts else "Không có phương án thay."})
        droppable = [i for i in r.order if cx.places[i].role == "selected"]
        if len(r.order) >= 2 and droppable:
            start, prefs = cx.day.start_node, cx.prefs or {}
            pid = min(droppable, key=lambda i: (prefs.get(i, 0.0), -(cx.travel.leg(start, i)[0] if start else 0), i))
            on_delay.append({"day": cx.day.index + 1, "place_id": pid, "name": cx.places[pid].name})
    return {"places": out, "on_delay": on_delay}
