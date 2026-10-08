"""Decision Output + serving records -> a checked itinerary (docs/PLANNING.md, phase P3).

One path, no randomness: places -> one travel matrix -> clusters -> days -> stop order -> clock -> validate.
prepare() does once what every variant shares; schedule_trip() lays the trip out for one objective's weights.
"""

from dataclasses import asdict, dataclass, field, replace

import live

from . import places as pl
from .cluster import cluster_places, split_to_fit
from .conditions import build_cond, crowd_sensitive, crowd_tips, describe
from .days import assign_days, day_load, isolate_constrained
from .frame import trip_days
from .model import Item
from .route import order_day
from .schedule import DayCtx, pin_window
from .settings import Settings, fmt
from .settings import load as load_settings
from .traits import preference
from .travel import Travel, build_travel
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
    "pin_dropped": "Ngày {day}: không xếp kịp {name} vào đúng giờ đẹp nhất (hoàng hôn / bình minh / nhạc), vẫn ghé nơi này lúc khác trong ngày.",
    "near_duplicate": "{a} và {b} cùng một kiểu nơi: giữ cả hai cũng được, chỉ là chuyến đi kém đa dạng hơn.",
    "severe_weather": "Ngày {day}: dự báo thời tiết rất xấu ({what}); không xếp nơi ngoài trời vào ngày này.",
    "heavy_weather": "Ngày {day}: dự báo mưa lớn hoặc dông ({what}); nơi ngoài trời dễ hỏng, mỗi nơi có phương án thay.",
    "advisory": "Ngày {day}: có thông báo {kind} mức {severity}: {note} (nguồn: {source}).",
    "crowd_day": "Ngày {day}: {why}. Nơi vốn đông sẽ đông hơn, mình để thêm thời gian chờ.",
    "holiday_closure": "Ngày {day}: dịp {name} nhiều quán đóng cửa hoặc đổi giờ; gọi xác nhận trước khi đi.",
}
ADVISORY_KIND = {"storm": "bão / dông", "flood": "ngập lụt", "landslide": "sạt lở", "fire": "cháy", "road_closed": "đường bị chặn",
                 "other": "khác"}
SEVERITY_TEXT = {"watch": "theo dõi", "warning": "cảnh báo", "severe": "nghiêm trọng"}


MEAL_NAME = {"lunch": "trưa", "dinner": "tối"}
WAIT_TEXT = {"opening": "chờ mở cửa", "meal": "chờ khung giờ ăn", "pin": "chờ đúng giờ (hoàng hôn / bình minh / nhạc)"}


def _warn(code: str, **kw) -> dict:
    return {"code": code, "text": WARNING_TEXT[code].format(**kw)}


def _item(it: Item) -> dict:
    d = {"kind": it.kind, "start": fmt(it.start), "end": fmt(it.end), "place_id": it.place_id, "name": it.name,
         "from": it.from_id, "to": it.to_id, "mode": it.mode, "note": it.note}
    return {k: v for k, v in d.items() if v is not None}


@dataclass
class Trip:
    """Everything the variants of one trip share: places, points, one travel matrix, the days. Built once a turn."""
    decision: dict
    cfg: Settings
    pace: str
    by_place: dict                  # id -> Place
    unplaced: list
    by_id: dict                     # every serving record by id, for the backups
    points: dict                    # node -> Point | None
    travel: Travel
    days: list
    ctxs: list                      # one DayCtx a day, with the default weights
    warnings: list
    weather: dict | None
    lodging_ids: tuple = ()         # ids of the extra nodes added to the matrix as lodging candidates (P5)
    routes: dict = field(default_factory=dict)      # (day index, sorted ids) -> DayResult, shared by every variant


@dataclass(frozen=True)
class Schedule:
    """One way of laying the trip out: which places on which day, in which order, and what validate said."""
    per_day: list
    results: list
    ctxs: list
    violations: list
    warnings: list


def prepare(decision: dict, records: list[dict], cfg: Settings | None = None, live_cfg=None, geocode_fn=None,
            matrix_fn=None, sun_fn=None, weather: dict | None = None, extra_nodes: dict | None = None,
            signals: dict | None = None) -> Trip:
    """weather: {"YYYY-MM-DD": {"rain_prob": 0..1, "rain_mm", "gust_kmh", "storm", "source", "fetched_at"}} or None.
    signals: {"YYYY-MM-DD": {"holiday": name | None, "events": [...], "advisories": [...]}} or None (see
    conditions.fetch_live). With neither, no day has a DayCond and the plan is what it was before conditions."""
    cfg = cfg or load_settings()
    live_cfg = live_cfg or live.load_settings()
    geocode_fn = geocode_fn or (lambda text: live.geocode(text, live_cfg))
    matrix_fn = matrix_fn or live.travel_matrix
    sun_fn = sun_fn or live.sun_times
    by_id = {r["id"]: r for r in records}
    tc = decision["trip_context"]
    ctx = tc["context"]
    pace = (tc.get("pace") or {}).get("level") or "normal"
    mobility = ctx.get("mobility")
    warnings: list[dict] = []

    placed, unplaced = pl.build_places(decision, by_id, cfg)
    by_place = {p.id: p for p in placed}
    # Near duplicates (the same kind of place, PLACE_DECISION §9.1) the user kept anyway: say so, never refuse.
    seen: dict = {}
    for p in placed:
        if p.dup_group is not None and p.dup_group in seen:
            warnings.append(_warn("near_duplicate", a=seen[p.dup_group], b=p.name))
        seen.setdefault(p.dup_group, p.name)
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
    nodes.update(extra_nodes or {})
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
    soft = tc.get("soft_weights") or []
    prefs = {p.id: preference(p, soft) for p in placed}

    def rain_on(d) -> float | None:
        day = (weather or {}).get(d.date.isoformat()) if d.date else None
        return day.get("rain_prob") if day else None

    crowd_tol = (tc.get("pace") or {}).get("crowd_tolerance")
    ctxs = [DayCtx(d, by_place, travel, cfg, pace,
                   sun_fn(d.date, *centre, live_cfg.tz_offset_h) if d.date and centre else None, rain_on(d), prefs,
                   build_cond(d, weather, signals, cfg), crowd_tol)
            for d in days]
    warnings += condition_warnings(ctxs)
    return Trip(decision, cfg, pace, by_place, unplaced, by_id, points, travel, days, ctxs, warnings, weather,
               lodging_ids=tuple(extra_nodes or {}))


def condition_warnings(ctxs: list) -> list[dict]:
    """What each day's conditions mean for the user, in words. A day with nothing notable says nothing."""
    out = []
    for cx in ctxs:
        c, n = cx.cond, cx.day.index + 1
        if c is None:
            continue
        what = ", ".join(x for x in ("dông" if c.storm else "", f"mưa ~{c.rain_mm:.0f} mm" if c.rain_mm else "",
                                     f"gió giật ~{c.gust_kmh:.0f} km/h" if c.gust_kmh else "") if x)
        if c.weather != "none":
            out.append(_warn("severe_weather" if c.weather == "severe" else "heavy_weather", day=n, what=what))
        out += [_warn("advisory", day=n, kind=ADVISORY_KIND[a["kind"]], severity=SEVERITY_TEXT[a["severity"]],
                      note=a["note"] or "không ghi chú", source=a["source"]) for a in c.advisories]
        if c.crowd != "normal" and any(crowd_sensitive(p, c, cx.cfg) for p in cx.places.values()):
            out.append(_warn("crowd_day", day=n, why=", ".join(c.crowd_reasons)))
        if c.closure_risk:
            out.append(_warn("holiday_closure", day=n, name=c.closure_risk))
    return out


def pull_early(cx: DayCtx, day_ids, by_place: dict, travel) -> tuple[DayCtx, str | None]:
    """A sunrise place pulls a later day's start forward: (the day, the place that pulled it, or None). The scheduler
    and every later check of a laid-out day use this one rule, so a plan shown as valid passes the check at confirm."""
    early = [(pin_window(by_place[i], cx)[0], i) for i in day_ids
             if i in by_place and 0 < pin_window(by_place[i], cx)[0] < cx.day.start]
    if not early or cx.day.index == 0:
        return cx, None
    lo, pid = min(early)
    first = cx.day.start_node
    start = max(0, lo - (travel.leg(first, pid)[0] if first else 0))
    return replace(cx, day=replace(cx.day, start=start)), pid


def schedule_trip(trip: Trip, weights: dict | None = None) -> Schedule:
    """Lay the trip out with one objective's day-split weights merged over the defaults (None = the defaults)."""
    cfg = trip.cfg
    ctxs = trip.ctxs if not weights else [replace(cx, cfg=replace(cfg, weights={**cfg.weights, **weights}))
                                          for cx in trip.ctxs]
    warnings: list[dict] = []
    ids = sorted(trip.by_place)
    cap = int(cfg.fill_ratio * max(d.end - d.start for d in trip.days))
    clusters = cluster_places(ids, {p.id: p.area for p in trip.by_place.values()}, trip.travel, cfg)
    # a cluster is cut when it holds more places than a day is planned for, or more than a day can carry
    size = lambda c: cap + 1 if len(c) > cfg.per_day[trip.pace] else day_load(c, trip.by_place, cfg, trip.pace)
    clusters = split_to_fit(clusters, size, cap, trip.travel)
    per_day, flag = assign_days(isolate_constrained(clusters, ctxs), ctxs)
    if flag:
        warnings.append(_warn(flag))
    ctxs = list(ctxs)
    for k, (cx, day_ids) in enumerate(zip(ctxs, per_day)):
        ctxs[k], pid = pull_early(cx, day_ids, trip.by_place, trip.travel)
        if pid:
            warnings.append(_warn("early_start", day=cx.day.index + 1, start=fmt(ctxs[k].day.start),
                                  name=trip.by_place[pid].name))
    tc = trip.decision["trip_context"]
    hard, budget = tc.get("hard_filters") or [], tc["context"].get("budget_vnd")
    max_leg = (tc.get("pace") or {}).get("max_leg_min")
    results = []
    for k, (day_ids, cx) in enumerate(zip(per_day, ctxs)):
        key = (cx.day.index, cx.day.start_node, cx.day.end_node, tuple(sorted(day_ids)))
        if key not in trip.routes:      # the order inside a day does not depend on the day-split weights
            trip.routes[key] = order_day(day_ids, cx)
        r = trip.routes[key]
        if validate([cx], [r], hard, set(), budget, max_leg):
            cx, r, dropped = _unpin(cx, r, day_ids, hard, budget, max_leg)
            r = replace(r, unpinned=tuple(dropped))     # validate and every later re-check honour the same decision
            ctxs[k] = cx
            warnings += [_warn("pin_dropped", day=cx.day.index + 1, name=cx.places[i].name) for i in dropped]
        results.append(r)
    for cx, r in zip(ctxs, results):
        for note in r.notes:
            code, _, meal = note.partition(":")
            warnings.append(_warn(code, day=cx.day.index + 1, meal=MEAL_NAME.get(meal, meal)))
    anchors = {c["id"] for c in trip.decision["confirmed"] if c.get("role") == "anchor"}
    violations = validate(ctxs, results, hard, anchors, budget, max_leg)
    return Schedule(per_day, results, ctxs, violations, warnings)


def _unpin(cx: DayCtx, r, day_ids: list, hard: list, budget, max_leg):
    """A day that fails because places want the same time of day (two bars that both want 18:00, a sunset spot after
    an evening show): give up the time of day of the latest one first, until the day passes. The visit stays; only
    the "be there at sunset / for the music" wish is dropped, and the caller says so. Nothing helps: unchanged."""
    first = {it.place_id: it.start for it in r.items if it.kind == "visit"}
    pinned = sorted((i for i in day_ids if cx.places[i].pins), key=lambda i: -first.get(i, 0))
    tried, dropped = cx, []
    for pid in pinned:
        tried = replace(tried, places={**tried.places, pid: replace(tried.places[pid], pins=())})
        dropped.append(pid)
        out = order_day(day_ids, tried)
        if not validate([tried], [out], hard, set(), budget, max_leg):
            return tried, out, dropped
    return cx, r, []


def with_home(trip: Trip, home_id: str | None) -> Trip:
    """The same trip anchored at a different place to sleep (a lodging candidate, or None for the original base):
    same places, same travel matrix, same per-day sun / rain / preference — only where each day starts and ends
    changes, so the day-order cache (now keyed on the start and end node too) still pays off across candidates."""
    ctx = trip.decision["trip_context"]["context"]
    entry = ENTRY if trip.points.get(ENTRY) else None
    exit_ = EXIT if trip.points.get(EXIT) else None
    days = trip_days(ctx, trip.cfg, home_id, entry, exit_)
    ctxs = [replace(cx, day=d) for cx, d in zip(trip.ctxs, days)]
    return replace(trip, days=days, ctxs=ctxs)


def itinerary(days: list, results: list) -> list[dict]:
    return [{"day": d.index + 1, "date": d.date.isoformat() if d.date else None, "weekday": d.weekday,
             "window": [fmt(d.start), fmt(d.end)], "method": r.method,
             "items": [_item(i) for i in r.items]} for d, r in zip(days, results)]


def travel_load(days: list, results: list) -> list[dict]:
    return [{"day": d.index + 1, "travel_min": r.travel_min, "wait_min": r.wait_min,
             "longest_leg_min": max((i.end - i.start for i in r.items if i.kind == "travel"), default=0)}
            for d, r in zip(days, results)]


def flag_warnings(decision: dict) -> list[dict]:
    return [{"code": "flag", "text": f} for c in decision["confirmed"] for f in c.get("flags") or []]


def shared_output(trip: Trip) -> dict:
    """The parts of the Plan Output that do not depend on how the trip is laid out."""
    decision, travel = trip.decision, trip.travel
    conds = [cx.cond for cx in trip.ctxs]
    extra = {"day_conditions": [{"day": cx.day.index + 1, "date": cx.day.date.isoformat() if cx.day.date else None,
                                 **(describe(cx.cond) or {})} for cx in trip.ctxs],
             "crowd_tips": crowd_tips(list(trip.by_place.values()), conds, trip.cfg)} if any(conds) else {}
    return {**extra,
        "unplaced": [asdict(u) for u in trip.unplaced],
        "uncertainty": {"travel_source": travel.source, "rough_pairs": travel.rough_pairs,
                        "estimated": ["travel_minutes", "visit_minutes", "cost"]},
        "provenance": {"travel": {"source": travel.source, "fetched_at": travel.fetched_at},
                       "points": {n: {"text": pt.text, "source": pt.source, "fetched_at": pt.fetched_at}
                                  for n, pt in trip.points.items() if pt}},
        "reasons": decision.get("decision_log") or [],
        "tradeoffs": [{"kind": "relaxed", "place_id": c["id"], "features": c["relaxed"]}
                      for c in decision["confirmed"] if c.get("relaxed")]
                     + [{"kind": "unplaced", "place_id": u.id, "reason": u.reason} for u in trip.unplaced],
        "trip_context": decision["trip_context"],
    }


def build_plan(decision: dict, records: list[dict], cfg: Settings | None = None, live_cfg=None, geocode_fn=None,
               matrix_fn=None, sun_fn=None) -> dict:
    trip = prepare(decision, records, cfg, live_cfg, geocode_fn, matrix_fn, sun_fn)
    sched = schedule_trip(trip)
    days = [cx.day for cx in sched.ctxs]      # schedule_trip may pull a later day's start earlier (early_start)
    return {
        "ok": not sched.violations,
        "itinerary": itinerary(days, sched.results),
        "travel_load": travel_load(days, sched.results),
        "violations": [asdict(v) for v in sched.violations],
        "warnings": trip.warnings + sched.warnings + flag_warnings(decision),
        **shared_output(trip),
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
