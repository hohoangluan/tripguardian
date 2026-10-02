"""Decision Output + serving records -> a checked itinerary (docs/specs/PLANNING_SPEC.md, phase P3).

One path, no randomness: places -> one travel matrix -> clusters -> days -> stop order -> clock -> validate.
This phase builds one plan around the user's base; variants, robustness, backups and lodging come later.
"""

from dataclasses import asdict, replace

import live

from . import places as pl
from .cluster import cluster_places, split_to_fit
from .days import assign_days, day_load, isolate_constrained
from .frame import trip_days
from .model import Item
from .route import order_day
from .schedule import DayCtx, pin_window
from .settings import Settings, fmt
from .settings import load as load_settings
from .travel import build_travel
from .validate import validate

HOME, ENTRY, EXIT = "@home", "@entry", "@exit"

WARNING_TEXT = {
    "days_assumed": "Chưa biết số ngày: tạm xếp {n} ngày.",
    "dates_unknown": "Chưa biết ngày đi: không kiểm giờ mở cửa theo thứ và không ghim giờ hoàng hôn / bình minh.",
    "entry_exit_unknown": "Chưa biết điểm vào / ra thành phố: ngày đầu và ngày cuối chỉ cắt theo giờ đến / giờ rời, kém chắc hơn.",
    "base_unknown": "Chưa biết nơi ở: mỗi ngày bắt đầu và kết thúc ở địa điểm đầu / cuối.",
    "travel_rough": "Thời gian di chuyển là ước lượng thô (không có OSRM), không dùng để kết luận độ vững.",
    "travel_pairs_rough": "{n} chặng không có đường trong OSRM, dùng ước lượng thô.",
    "days_fallback": "Quá nhiều ngày hoặc cụm để tìm chính xác: chia ngày theo cách tham lam.",
    "hours_unknown": "{name}: chưa có giờ mở cửa, không kiểm.",
    "meal_missed": "Ngày {day}: quá khung giờ {meal}, chưa xếp bữa.",
    "hours_vary": "{name}: giờ mở cửa khác nhau theo thứ, chưa biết ngày đi nên dùng khung giờ chung các ngày mở.",
    "early_start": "Ngày {day}: bắt đầu sớm lúc {start} để kịp {name}.",
}


MEAL_NAME = {"lunch": "trưa", "dinner": "tối"}
WAIT_TEXT = {"opening": "chờ mở cửa", "meal": "chờ khung giờ ăn", "pin": "chờ đúng giờ (hoàng hôn / bình minh / nhạc)"}


def _warn(code: str, **kw) -> dict:
    return {"code": code, "text": WARNING_TEXT[code].format(**kw)}


def _item(it: Item) -> dict:
    d = {"kind": it.kind, "start": fmt(it.start), "end": fmt(it.end), "place_id": it.place_id, "name": it.name,
         "from": it.from_id, "to": it.to_id, "mode": it.mode, "note": it.note}
    return {k: v for k, v in d.items() if v is not None}


def build_plan(decision: dict, records: list[dict], cfg: Settings | None = None, live_cfg=None, geocode_fn=None,
               matrix_fn=None, sun_fn=None) -> dict:
    cfg = cfg or load_settings()
    live_cfg = live_cfg or live.load_settings()
    geocode_fn = geocode_fn or (lambda text: live.geocode(text, live_cfg))
    matrix_fn = matrix_fn or live.travel_matrix
    sun_fn = sun_fn or live.sun_times
    by_id = {r["id"]: r for r in records}
    tc = decision["trip_context"]
    ctx, pace_spec = tc["context"], tc.get("pace") or {}
    pace = pace_spec.get("level") or "normal"
    mobility = ctx.get("mobility")
    warnings: list[dict] = []

    placed, unplaced = pl.build_places(decision, by_id, cfg)
    by_place = {p.id: p for p in placed}
    for p in placed:
        if p.hours is None:
            warnings.append(_warn("hours_unknown", name=p.name))
        elif not (ctx.get("start_date") and ctx.get("days")) and pl.hours_vary(p.hours):
            warnings.append(_warn("hours_vary", name=p.name))

    points, why = {}, {}
    for node, base in ((HOME, ctx.get("base")), (ENTRY, ctx.get("entry_point")), (EXIT, ctx.get("exit_point"))):
        points[node], why[node] = pl.resolve_point(base, by_id, geocode_fn)
    home = HOME if points[HOME] else ENTRY if points[ENTRY] else None
    entry = ENTRY if points[ENTRY] else None
    exit_ = EXIT if points[EXIT] else None
    if home is None:
        warnings.append(_warn("base_unknown"))
    if entry is None or exit_ is None:
        warnings.append(_warn("entry_exit_unknown"))

    nodes = {p.id: (p.lat, p.lng) for p in placed}
    nodes.update({n: (pt.lat, pt.lng) for n, pt in points.items() if pt})
    travel = build_travel(nodes, mobility, cfg, live_cfg, matrix_fn)
    if travel.source == "rough":
        warnings.append(_warn("travel_rough"))
    elif travel.rough_pairs:
        warnings.append(_warn("travel_pairs_rough", n=travel.rough_pairs))

    days = trip_days(ctx, cfg, home, entry, exit_)
    if not ctx.get("days"):
        warnings.append(_warn("days_assumed", n=len(days)))
    if not (ctx.get("start_date") and ctx.get("days")):
        warnings.append(_warn("dates_unknown"))
    centre = (sum(p.lat for p in placed) / len(placed), sum(p.lng for p in placed) / len(placed)) if placed else None
    ctxs = [DayCtx(d, by_place, travel, cfg, pace,
                   sun_fn(d.date, *centre, live_cfg.tz_offset_h) if d.date and centre else None) for d in days]

    ids = sorted(by_place)
    cap = int(cfg.fill_ratio * max(d.end - d.start for d in days))
    clusters = cluster_places(ids, {p.id: p.area for p in placed}, travel, cfg)
    # a cluster is cut when it holds more places than a day is planned for, or more than a day can carry
    size = lambda c: cap + 1 if len(c) > cfg.per_day[pace] else day_load(c, by_place, cfg, pace)
    clusters = split_to_fit(clusters, size, cap, travel)
    per_day, flag = assign_days(isolate_constrained(clusters, ctxs), ctxs)
    if flag:
        warnings.append(_warn(flag))
    for k, (cx, day_ids) in enumerate(zip(ctxs, per_day)):      # a sunrise place pulls a later day's start forward
        early = [(pin_window(by_place[i], cx)[0], i) for i in day_ids if 0 < pin_window(by_place[i], cx)[0] < cx.day.start]
        if early and cx.day.index > 0:
            lo, pid = min(early)
            first = cx.day.start_node
            start = max(0, lo - (travel.leg(first, pid)[0] if first else 0))
            ctxs[k] = replace(cx, day=replace(cx.day, start=start))
            days[k] = ctxs[k].day
            warnings.append(_warn("early_start", day=cx.day.index + 1, start=fmt(start), name=by_place[pid].name))
    results = [order_day(day_ids, cx) for day_ids, cx in zip(per_day, ctxs)]
    for cx, r in zip(ctxs, results):
        for note in r.notes:
            code, _, meal = note.partition(":")
            warnings.append(_warn(code, day=cx.day.index + 1, meal=MEAL_NAME.get(meal, meal)))

    anchors = {c["id"] for c in decision["confirmed"] if c.get("role") == "anchor"}
    violations = validate(ctxs, results, tc.get("hard_filters") or [], anchors, ctx.get("budget_vnd"),
                          pace_spec.get("max_leg_min"))
    return {
        "ok": not violations,
        "itinerary": [{"day": d.index + 1, "date": d.date.isoformat() if d.date else None, "weekday": d.weekday,
                       "window": [fmt(d.start), fmt(d.end)], "method": r.method,
                       "items": [_item(i) for i in r.items]} for d, r in zip(days, results)],
        "travel_load": [{"day": d.index + 1, "travel_min": r.travel_min, "wait_min": r.wait_min,
                         "longest_leg_min": max((i.end - i.start for i in r.items if i.kind == "travel"), default=0)}
                        for d, r in zip(days, results)],
        "violations": [asdict(v) for v in violations],
        "warnings": warnings + [{"code": "flag", "text": f} for c in decision["confirmed"] for f in c.get("flags") or []],
        "unplaced": [asdict(u) for u in unplaced],
        "uncertainty": {"travel_source": travel.source, "rough_pairs": travel.rough_pairs,
                        "estimated": ["travel_minutes", "visit_minutes", "cost"]},
        "provenance": {"travel": {"source": travel.source, "fetched_at": travel.fetched_at},
                       "points": {n: {"text": pt.text, "source": pt.source, "fetched_at": pt.fetched_at}
                                  for n, pt in points.items() if pt}},
        "reasons": decision.get("decision_log") or [],
        "tradeoffs": [{"kind": "relaxed", "place_id": c["id"], "features": c["relaxed"]}
                      for c in decision["confirmed"] if c.get("relaxed")]
                     + [{"kind": "unplaced", "place_id": u.id, "reason": u.reason} for u in unplaced],
        "trip_context": tc,
    }


def render_text(plan: dict) -> str:
    """The itinerary as plain lines, for the command line."""
    names = {i["place_id"]: i["name"] for d in plan["itinerary"] for i in d["items"] if i["kind"] == "visit"}
    out = []
    for d in plan["itinerary"]:
        head = f'Ngày {d["day"]}' + (f' ({d["date"]})' if d["date"] else "") + f' · {d["window"][0]}-{d["window"][1]}'
        out.append(head)
        for i in d["items"]:
            span = f'  {i["start"]}-{i["end"]}  '
            if i["kind"] == "visit":
                out.append(span + i["name"])
            elif i["kind"] == "travel":
                out.append(span + f'di chuyển ({i["mode"]}) tới {names.get(i["to"], i["to"])}')
            elif i["kind"] == "meal_free":
                out.append(span + f'ăn {MEAL_NAME.get(i["name"], i["name"])} (tự chọn)')
            else:
                out.append(span + (WAIT_TEXT.get(i.get("note"), "chờ") if i["kind"] == "wait"
                                   else {"buffer": "đệm", "rest": "nghỉ"}[i["kind"]]))
    for w in plan["warnings"]:
        out.append("! " + w["text"])
    for v in plan["violations"]:
        out.append(f'X {v["kind"]} ngày {(v["day"] + 1) if v["day"] is not None else "-"}: {v["detail"]}'
                   + (" (physical)" if v["physical"] else ""))
    out.append("Hợp lệ." if plan["ok"] else "KHÔNG hợp lệ.")
    return "\n".join(out)
