"""Decision Output + serving records -> a checked itinerary (docs/PLANNING.md, phase P3).

One path, no randomness: places -> one travel matrix -> days (layout.py) -> stop order -> clock -> validate.
prepare() does once what every variant shares; schedule_trip() lays the trip out for one objective's weights.
"""

from dataclasses import asdict, dataclass, field, replace

import live
from trip import RECOMMENDED_TRIP_DAYS

from . import places as pl
from .conditions import build_cond, crowd_sensitive, crowd_tips, describe
from .frame import end_said, start_said, trip_days
from .layout import DAWN_REST, allowed, assign, capacity, must_places, pull_early
from .model import Day, Item
from .roles import ROLE_SLOTS, pin_order, takes_meal_slot
from .route import order_day, _nearest_neighbour
from .schedule import DayCtx, _SimulationCache, dawn_swapped, day_meals, pin_window, simulate
from .settings import Settings, fmt, to_min
from .settings import load as load_settings
from .traits import preference
from .travel import Travel, build_travel
from .validate import validate
from .timefit import describe as time_description
from .recommendations import recommend
from .cache import day_key, fingerprint, put

HOME = "@home"

WARNING_TEXT = {
    "days_assumed": "Chưa biết số ngày: tạm xếp {n} ngày.",
    "dates_unknown": "Chưa biết ngày đi: không kiểm giờ mở cửa theo thứ và không ghim giờ hoàng hôn / bình minh.",
    "base_unknown": "Chưa biết nơi ở: mỗi ngày bắt đầu và kết thúc ở địa điểm đầu / cuối.",
    "travel_rough": "Thời gian di chuyển là ước lượng thô (không có OSRM), không dùng để kết luận độ vững.",
    "travel_pairs_rough": "{n} chặng không có đường trong OSRM, dùng ước lượng thô.",
    "days_fallback": "Quá nhiều ngày hoặc cụm để tìm chính xác: chia ngày theo cách tham lam.",
    "hours_unknown": "{name}: chưa có giờ mở cửa, không kiểm.",
    "meal_missed": "Ngày {day}: quá khung giờ {meal}, chưa xếp bữa.",
    "hours_vary": "{name}: giờ mở cửa khác nhau theo thứ, chưa biết ngày đi nên dùng khung giờ chung các ngày mở.",
    "early_start": "Ngày {day}: bắt đầu sớm lúc {start} để kịp {name}.",
    "event_location_unknown": "Ngày {day}: chưa biết {label} ở đâu, lịch không tính đường tới đó.",
    "dawn_swapped": "Ngày {day}: bạn bắt đầu lúc {start} nên {name} xếp vào giờ hoàng hôn thay cho bình minh.",
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


MEAL_NAME = {"breakfast": "sáng", "lunch": "trưa", "dinner": "tối"}
WAIT_TEXT = {"opening": "chờ mở cửa", "meal": "chờ khung giờ ăn", "pin": "chờ đúng giờ (hoàng hôn / bình minh / nhạc)",
             "preferred_time": "nghỉ trước khung giờ ưu tiên"}


def _warn(code: str, **kw) -> dict:
    return {"code": code, "text": WARNING_TEXT[code].format(**kw)}



def pin_warnings(ctxs, results) -> list[dict]:
    """Render only pins actually released in the visible itinerary, including after edits."""
    labels = {"hours": "giờ mở cửa", "day_window": "khung ngày", "departure": "giờ rời đi",
              "meal_window": "khung bữa ăn", "meal_missing": "bữa ăn bắt buộc", "busy": "lịch cố định"}
    out = []
    for cx, result in zip(ctxs, results):
        conflicts = dict(result.pin_conflicts)
        for pid in result.unpinned:
            reasons = conflicts.get(pid, ())
            reason = next(iter(reasons), None)
            warning = _warn("pin_dropped", day=cx.day.index + 1, name=cx.places[pid].name)
            warning.update(day=cx.day.index + 1, place_id=pid, reason=reason, physical_conflicts=list(reasons))
            if reason:
                warning["text"] += " Giữ cửa sổ này sẽ vi phạm " + labels[reason] + "."
            out.append(warning)
    return out

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
    routes: dict = field(default_factory=dict)      # day, pace, conditions and place signature -> DayResult
    chunk_assignments: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Schedule:
    """One way of laying the trip out: which places on which day, in which order, and what validate said."""
    per_day: list
    results: list
    ctxs: list
    violations: list
    warnings: list
    leftover: tuple = ()            # selected places no day has room for (layout capacity); the user decides


# What a day the layout overfilled trips over: the place at fault leaves the day (schedule_trip). A day over the
# user's driving cap is not one of them: that cap has a price the user weighs (spec section 4), so it is reported.
# The limits a time-of-day wish may yield to (spec section 5): never pace, road minutes or another soft wish.
PIN_PHYSICAL = frozenset({"hours", "day_window", "departure", "meal_window", "meal_missing", "busy"})

MISFIT = {"day_window", "departure", "hours", "busy", "meal_window", "meal_missing", "timed", "visit_duration",
          "long_leg"}


def breakfast_estimate(p, cfg: Settings):
    """A category-only eating fallback is not evidence for a 90-minute breakfast: a breakfast place takes the
    configured breakfast length, framed or not (one duration per place, ruling S8). A sourced visit and the user's
    duration take precedence over every default."""
    if p.meal_kind != "breakfast" or p.visit.get("source") == "user" or \
            p.visit.get("original_source", p.visit.get("source")) != "category_default":
        return p
    breakfast = cfg.meal_durations.get("breakfast", cfg.meal_min)
    return replace(p, visit={**p.visit, "short": breakfast, "typical": breakfast, "long": breakfast,
                             "source": "planning_default", "original_source": "category_default"})


def prepare(decision: dict, records: list[dict], cfg: Settings | None = None, live_cfg=None, geocode_fn=None,
            matrix_fn=None, sun_fn=None, weather: dict | None = None, extra_nodes: dict | None = None,
            signals: dict | None = None) -> Trip:
    """weather: {"YYYY-MM-DD": {"rain_prob": 0..1, "rain_mm", "gust_kmh", "storm", "source", "fetched_at"}} or None.
    signals: {"YYYY-MM-DD": {"holiday": name | None, "events": [...], "advisories": [...]}} or None (see
    conditions.fetch_live). With neither, no day has a DayCond and the plan is what it was before conditions."""
    cfg = cfg or load_settings()
    if (decision["trip_context"]["context"].get("days") or cfg.default_days) > cfg.chunk_days:
        cfg = replace(cfg, exact_n=min(cfg.exact_n, cfg.long_trip_exact_n))
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
    if (ctx.get("days") or cfg.default_days) > RECOMMENDED_TRIP_DAYS:
        warnings.append({"code": "long_trip_scope", "text":
                         f"Khuyến nghị tối đa {RECOMMENDED_TRIP_DAYS} ngày. Chuyến dài hơn vẫn được phép, "
                         "nhưng khả năng xử lý chưa được kiểm chứng và việc xếp, sửa lịch có thể lâu hơn."})

    placed, unplaced = pl.build_places(decision, by_id, cfg)
    frame = ctx.get("frame") or {}
    said = frame.get("visit") or {}             # how long the user said a kind of place takes beats the estimate
    if said:
        placed = [replace(p, visit={**p.visit, "short": m, "typical": m, "long": m, "source": "user"})
                  if (m := said.get(p.rec["identity"].get("category_group"))) else p for p in placed]
    placed = [breakfast_estimate(p, cfg) for p in placed]
    # A place known for several times of day (sunset and cloud hunting) is visited for the one the user asked for.
    wants = {w["feature"] for w in tc.get("soft_weights") or [] if w.get("weight", 0) > 0 and w.get("value") == "present"}
    placed = [replace(p, pins=pin_order(p.pins, wants)) for p in placed]
    if frame and "live_music" not in wants:
        # A venue offering music does not mean a sightseeing visit attends it. Full frames keep evening music for
        # nightlife/bar/market visits; explicit timing preferences and the place's opening hours remain in force.
        placed = [replace(p, pins=tuple(f for f in p.pins if f != "live_music"))
                  if p.activity not in {"nightlife", "drinking"} and
                  p.rec["identity"].get("category_group") not in {"bar", "market"} else p for p in placed]
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

    # Every day starts and ends where the user sleeps; where the trip enters or leaves the city does not move that.
    points = {}
    points[HOME], _ = pl.resolve_point(ctx.get("base"), by_id, geocode_fn)
    home = HOME if points[HOME] else None
    if home is None:
        warnings.append(_warn("base_unknown"))
    # Where the trip enters and leaves the city opens day one and closes the last day (spec section 4).
    for node, key, moment in (("@entry", "entry_point", "arrive"), ("@exit", "exit_point", "leave")):
        if frame.get(moment) and ctx.get(key):
            points[node], _ = pl.resolve_point(ctx[key], by_id, geocode_fn)
    entry = "@entry" if points.get("@entry") else None
    exit_ = "@exit" if points.get("@exit") else None

    nodes = {p.id: (p.lat, p.lng) for p in placed}
    for candidate in decision.get("backup_pool") or []:
        ident = (by_id.get(candidate["id"]) or {}).get("identity") or {}
        if ident.get("lat") is not None and ident.get("lng") is not None:
            nodes[candidate["id"]] = (ident["lat"], ident["lng"])
    nodes.update({n: (pt.lat, pt.lng) for n, pt in points.items() if pt})
    nodes.update(extra_nodes or {})
    travel = build_travel(nodes, mobility, cfg, live_cfg, matrix_fn)
    if travel.source == "rough":
        warnings.append(_warn("travel_rough"))
    elif travel.rough_pairs:
        warnings.append(_warn("travel_pairs_rough", n=travel.rough_pairs))

    sources = tc.get("sources") or {}
    days = trip_days(ctx, cfg, home, entry, exit_, sources)
    # The road from the arrival point and to the departure point is a leg of the day now, so the day only keeps the
    # time at the airport / station: Trip's end (departure - buffer - its fixed road) gives way to the departure itself
    # less the buffer, the road being a leg now. An end the user said stays theirs, never past the departure.
    # A day Trip left free (no time left in it) keeps no window: nothing here may open one. The departure still binds
    # every leave day, free or not, with or without a known exit point: it is physical and never relaxed.
    leave_at = (frame.get("leave") or {}).get("at")
    if days and leave_at and leave_at[:10] == (days[-1].date.isoformat() if days[-1].date else None):
        last = days[-1]
        depart = to_min(leave_at[11:]) - cfg.realistic["leave_buffer_min"]
        end = last.end
        if last.intensity != "free":
            end = depart if exit_ and not end_said(ctx, sources, len(days) - 1, len(days)) else min(end, depart)
        days[-1] = replace(last, end=end, depart_by=depart)
    if entry and days and days[0].intensity != "free" \
            and frame["arrive"]["at"][:10] == (days[0].date.isoformat() if days[0].date else None) \
            and not start_said(ctx, sources, 0, len(days)):
        landed = to_min(frame["arrive"]["at"][11:])     # never before the arrival, never later than the frame says
        days[0] = replace(days[0], start=max(landed, min(days[0].start, landed + cfg.realistic["arrive_buffer_min"])))
    # A fixed-time block away from the lodging needs a place the plan knows; without one no road is invented (RULE §3).
    warnings += [_warn("event_location_unknown", day=d.index + 1, label=label) for d in days
                 for _, _, _, label, where in d.busy if where not in (None, "lodging") and where not in travel.index
                 and not remote(where, cfg)]
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
    checkin = to_min(ctx.get("checkin_at") or cfg.realistic["checkin_default"])     # bags wait at the lodging before it
    cfg = replace(cfg, realistic={**cfg.realistic, "drive_day_min": frame.get("drive_day_min")})
    ctxs = [DayCtx(d, by_place, travel, cfg, pace,
                   sun_fn(d.date, *centre, live_cfg.tz_offset_h) if d.date and centre else None, rain_on(d), prefs,
                   build_cond(d, weather, signals, cfg), crowd_tol, ctx.get("purpose"), tuple(tc.get("time_preferences") or ()),
                   mobility=mobility, require_meals=True, home=home,
                   meal_skip=frozenset(_skips(frame)), rest=_rest(frame),
                   compact_estimates=bool(frame),
                   drop_bags=d.index == 0 and d.start_node == "@entry" and d.start < checkin)
            for d in days]
    warnings += condition_warnings(ctxs)
    return Trip(decision, cfg, pace, by_place, unplaced, by_id, points, travel, days, ctxs, warnings, weather,
               lodging_ids=tuple(extra_nodes or {}), chunk_assignments=dict(decision.get("chunk_assignments") or {}))


def remote(where: str | None, cfg: Settings) -> bool:
    """A block done from wherever the person is (an online meeting, a call): it has no place to go to."""
    return bool(where) and where.strip().casefold() in {w.casefold() for w in cfg.realistic["remote_where"]}


def _skips(frame: dict) -> set[str]:
    meals = frame.get("meals") or {}
    return set(meals.get("skip") or ()) | ({"breakfast"} if meals.get("breakfast_at_lodging") else set())


def _rest(frame: dict) -> tuple[int, int] | None:
    rest = frame.get("rest")
    return (rest["every_min"], rest["rest_min"]) if rest else None


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


def schedule_trip(trip: Trip, weights: dict | None = None, *, kept=None, allow_shrink: bool | None = None) -> Schedule:
    """Lay the trip out with one objective's weights merged over the defaults (None = the defaults). The places go to
    days by layout.assign (each day's free minutes); a place no day has room for is reported in `leftover`, never
    dropped silently and never squeezed past a day's end."""
    cfg = trip.cfg
    if kept is not None:
        kept = set(kept)
        if not kept <= set(trip.by_place):
            raise ValueError("kept contains places outside the prepared selection")
        trip = replace(trip, by_place={pid: p for pid, p in trip.by_place.items() if pid in kept})
    if allow_shrink is not None:
        trip = replace(trip, ctxs=[replace(cx, allow_shrink=allow_shrink) for cx in trip.ctxs])
    soft = trip.decision["trip_context"].get("soft_weights") or []
    prefs = {pid: preference(p, soft) for pid, p in trip.by_place.items()}
    ctxs = [replace(cx, places=trip.by_place, prefs=prefs,
                    cfg=replace(cfg, weights={**cfg.weights, **(weights or {})})) for cx in trip.ctxs]
    warnings: list[dict] = []
    ids = sorted(trip.by_place)
    leftover: list = []

    def split(day_ids, day_ctxs):
        per_day, left = assign(trip, day_ctxs, day_ids)
        leftover.extend(left)
        return per_day, None

    if len(ctxs) <= cfg.chunk_days:
        per_day, _ = split(ids, ctxs)
    else:
        mapping = trip.chunk_assignments
        missing = [pid for pid in ids if type(mapping.get(pid)) is not int
                   or not 0 <= mapping[pid] < (len(ctxs) + cfg.chunk_days - 1) // cfg.chunk_days]
        if missing:
            # Legacy output: one coarse allocation, never a routing trial against every week.
            coarse, _ = split(missing, [replace(cx, cfg=cfg) for cx in ctxs])
            mapping.update({pid: k // cfg.chunk_days for k, group in enumerate(coarse) for pid in group})
        per_day = []
        for start in range(0, len(ctxs), cfg.chunk_days):
            week_ids = [pid for pid in ids if mapping.get(pid) == start // cfg.chunk_days]
            group, _ = split(week_ids, ctxs[start:start + cfg.chunk_days])
            per_day.extend(group)
    tc = trip.decision["trip_context"]
    hard, budget = tc.get("hard_filters") or [], tc["context"].get("budget_vnd")
    max_leg = (tc.get("pace") or {}).get("max_leg_min")
    anchors = must_places(trip)
    base = list(ctxs)                   # each day before a dawn pull

    def lay(k: int, day_ids: list, overfull: bool | str = False) -> tuple:
        """(the day, its result, the place that pulled it to dawn or None) for these places on day k; the same day with
        the same places is laid out once a trip (the composer tries many subsets). A day that runs past its end sheds a
        place before it gives up its one time of day (the misfit loop below); overfull: give it up all the same. Places
        that want the same hour give theirs up first, as before (_unpin)."""
        memo = fingerprint(("lay", day_key(base[k], day_ids), tuple(day_ids), hard, budget, max_leg, overfull))
        if memo not in trip.routes:
            put(trip.routes, memo, _lay(k, day_ids, overfull), cfg.cache_entries)
        cx, r, pid = trip.routes[memo]
        # The memo may come from another call over the same day and places (a composer subset): only the day and the
        # day's own places (their pins as given up) are its; everything else is this call's.
        return replace(base[k], day=cx.day, places={**base[k].places, **{i: cx.places[i] for i in day_ids}}), r, pid

    hosted: dict = {}

    def hosts(j: int, p) -> bool:
        """Day j can hold the place's time of day: alone on the day, at its shortest, with the meals at their shortest,
        the clock keeps it in its window without breaking a physical limit. A dawn pin moves the day's start."""
        if any(cfg.pins[f]["anchor"] == "sunrise" for f in p.pins):
            return True
        key = (j, p.id, p.pins)
        if key not in hosted:
            if pin_window(replace(p, pins=()), base[j]) == pin_window(p, base[j]):
                hosted[key] = True
            else:
                one = replace(p, visit={**p.visit, **dict.fromkeys(("short", "typical", "long"), p.visit["short"])})
                cx = replace(base[j], places={p.id: one}, cfg=replace(cfg, meal_durations={
                    n: min(m, cfg.realistic["meal_min"]) for n, m in cfg.meal_durations.items()}))
                r = simulate([p.id], cx, shrink=False)
                # A pin the clock cannot start inside its window shows as `timed` alone: not hosted either.
                hosted[key] = not {v.kind for v in validate([cx], [r], [], set(), None, None)} & (PIN_PHYSICAL | {"timed"})
        return hosted[key]

    def _lay(k: int, day_ids: list, overfull: bool | str) -> tuple:
        cx, pid = pull_early(base[k], day_ids, trip.by_place, trip.travel)
        # A time of day no day of the trip reaches (an evening market on trips whose days all end at 17:00) is given
        # up from the start: the frame itself is the physical limit, and the user is told.
        outside = tuple(i for i in day_ids if cx.places[i].pins and not hosts(k, cx.places[i])
                        and not any(hosts(j, cx.places[i]) for j in range(len(base))))
        if outside:
            cx = replace(cx, places={**cx.places, **{i: replace(cx.places[i], pins=()) for i in outside}})
        cx, r, pid = _lay_held(k, cx, pid, day_ids, overfull)
        if outside:
            r = replace(r, unpinned=tuple(dict.fromkeys((*outside, *r.unpinned))),
                        pin_conflicts=tuple((i, ("day_window",)) for i in outside) + r.pin_conflicts)
        return cx, r, pid

    def _lay_held(k: int, cx, pid, day_ids: list, overfull: bool | str) -> tuple:
        route_ctx = _route_ctx(cx)
        route_seed = tuple(sorted(day_ids)) if len(day_ids) <= route_ctx.cfg.exact_n else tuple(day_ids)
        key = fingerprint((day_key(route_ctx, day_ids), route_seed))
        if key not in trip.routes:      # the order inside a day does not depend on the day-split weights
            put(trip.routes, key, order_day(day_ids, route_ctx, seed=day_ids), cfg.cache_entries)
        r = trip.routes[key]
        wrong = {v.kind for v in validate([cx], [r], hard, set(), budget, max_leg)}
        # Spec section 5: a time of day is soft with a high weight. It yields only for a physical constraint that no
        # order fixes (order_day tried them with the pin held) and no other day fixes: the misfit loop first moves a
        # stop to another day and calls back with overfull only when that fails. Never for pace or road minutes.
        # The clock's own findings count too: a pin it found no feasible start for shows in validate as `timed` alone.
        blocked = tuple(sorted((wrong | {v.kind for v in r.violations}) & PIN_PHYSICAL)) if overfull else ()
        if blocked:
            tried, out, dropped = _unpin(cx, r, day_ids, hard, budget, max_leg, seed=day_ids, routes=trip.routes,
                                         reasons=blocked, keep_dawn=overfull if isinstance(overfull, str) else None)
            if dropped:
                # A dawn pin given up gives the day its start back (and no midday rest): only a pin still held pulls.
                back, pid = pull_early(replace(base[k], places=tried.places), day_ids, tried.places, trip.travel)
                if back.day != tried.day:
                    tried = replace(tried, day=back.day)
                    out = order_day(day_ids, _route_ctx(tried), seed=day_ids)
                # validate and every later re-check honour it; the user is told which physical limit forced it
                cx, r = tried, replace(out, unpinned=tuple(dropped), pin_conflicts=tuple((i, blocked) for i in dropped))
        if cx.compact_estimates and len(day_ids) > 1:
            # A clock's earlier finish can hide more driving behind a shorter estimate or a timed wait. Compare
            # road minutes directly among the NN order and road-saving 2-opt moves; validate every fixed edge.
            def road(order):
                nodes = [cx.day.start_node, *order, cx.day.end_node]
                return sum(cx.travel.leg(a, b)[0] for a, b in zip(nodes, nodes[1:]) if a and b and a != b)

            orders = {tuple(_nearest_neighbour(sorted(day_ids), cx))}
            visits = [it for it in r.items if it.kind == "visit"]

            def at_pin(it, anchors):
                p = cx.places[it.place_id]
                lo, hi = pin_window(p, cx)
                return lo <= it.start <= hi and any(cfg.pins[f]["anchor"] in anchors for f in p.pins)

            first = [visits[0].place_id] if visits and at_pin(visits[0], {"sunrise"}) else []
            last = [visits[-1].place_id] if visits and at_pin(visits[-1], {"sunset", "clock"}) else []
            middle = sorted(set(day_ids) - set(first) - set(last))
            middle_ctx = replace(cx, day=replace(cx.day, start_node=first[0])) if first else cx
            orders.add(tuple(first + _nearest_neighbour(middle, middle_ctx) + [p for p in last if p not in first]))
            orders.update(r.order[:i] + r.order[i:j + 1][::-1] + r.order[j + 1:]
                          for i in range(len(r.order) - 1) for j in range(i + 1, len(r.order)))
            road_cache = _SimulationCache(day_ids, cx)
            for cost, nearby in sorted((road(order), order) for order in orders):
                if cost >= road(r.order):
                    break
                candidate = simulate(list(nearby), cx, _cache=road_cache)
                candidate = replace(candidate, method="heuristic", pin_conflicts=r.pin_conflicts,
                                    unpinned=tuple(dict.fromkeys((*r.unpinned, *candidate.unpinned))))
                # Round-4 Finding 2 (time-penalty guard) deferred: restoring it fails §11 #9 on family_12_in_3 day 2.
                if candidate.travel_min < r.travel_min and not validate([cx], [candidate], hard, set(), budget, max_leg):
                    r = candidate
        return cx, r, pid

    def late(cx, r) -> int:
        """Minutes the day runs past its end or its departure (0 = in time)."""
        return sum(v.minutes for v in validate([cx], [r], hard, set(), budget, max_leg)
                   if v.kind in {"day_window", "departure"})

    def misfit(cx, r, kinds=MISFIT) -> tuple[int, int]:
        """How badly the finished day does not fit, judged by the validator (including meals_needed).
        A potential meal slot is not a missing meal when the finished day cannot hold its minimum length."""
        vs = [v for v in validate([cx], [r], hard, set(), budget, max_leg) if kinds is None or v.kind in kinds]
        return len(vs), sum(v.minutes for v in vs)

    days = [lay(k, day_ids) for k, day_ids in enumerate(per_day)]
    # A day the layout overfilled (the clock disagrees with its estimate) sheds a place, the one at fault first, else
    # the last; the place then tries another day, else it is left over (layout capacity, spec section 6).
    may = allowed(trip, base)

    def within(cx, r) -> bool:
        """A day kept light on purpose (Trip's `light`, a dawn day's afternoon) holds no more than its capacity says,
        whatever slack its clock shows; a free day holds nothing (layout.capacity)."""
        if cx.day.intensity != "light" and DAWN_REST not in cx.day.busy:
            return True
        return sum(i.end - i.start for i in r.items if i.kind in {"visit", "travel"}) <= capacity(cx)

    def meal_room(k, pid) -> bool:
        """Moving a flexible visit cannot create a meal slot when this role already occupies all of them."""
        p = trip.by_place[pid]
        if not takes_meal_slot(p):
            return True
        slots = set(ROLE_SLOTS.get(p.meal_kind, tuple(cfg.meal_windows))) & set(day_meals(base[k]))
        occupied = sum(takes_meal_slot(trip.by_place[q]) and trip.by_place[q].meal_kind == p.meal_kind
                       for q in per_day[k])
        return occupied < len(slots)

    def rehome(pid, k) -> bool:
        """Move a stop day k sheds to the day with the most slack that takes it without breaking anything, so a
        day that cannot hold all its stops at their times of day and pace moves a stop before it gives up either."""
        need = trip.by_place[pid].visit["short"]
        slack = sorted(((cx.day.end - cx.day.start - sum(i.end - i.start for i in r.items if i.kind not in {"wait", "free"}),
                         -j) for j, (cx, r, _) in enumerate(days) if j != k), reverse=True)
        for room, j in slack[:3]:
            j = -j
            if room < need or pid in per_day[j] or not may(j, pid) or not meal_room(j, pid) or \
                    base[j].day.intensity == "free":
                continue
            got = lay(j, [*per_day[j], pid])
            if misfit(*got[:2], None) <= misfit(*days[j][:2], None) and within(*got[:2]):
                per_day[j], days[j] = [*per_day[j], pid], got
                return True
        return False

    spilled: list = []
    for k in range(len(per_day)):
        while (bad := misfit(*days[k][:2])) > (0, 0):
            at_fault = [v.place_id for v in validate([days[k][0]], [days[k][1]], hard, set(), budget, max_leg)
                        if v.kind in MISFIT]
            order = [*at_fault, *reversed(days[k][1].order)]
            tries = [p for p in dict.fromkeys(order) if p in per_day[k] and p not in anchors]
            trials, shed = [], None
            for pid in tries:
                ids_k = [i for i in per_day[k] if i != pid]
                got = lay(k, ids_k)
                if misfit(*got[:2]) < bad:
                    if rehome(pid, k):          # another day takes it: nothing is lost
                        per_day[k], days[k] = ids_k, got
                        break
                    shed = shed or (pid, ids_k, got)
                trials.append((late(*got[:2]), pid, ids_k, got))
            else:
                got = lay(k, per_day[k], overfull=True)       # no other day takes a stop: a time of day goes instead
                if misfit(*got[:2]) < bad:
                    days[k] = got
                    continue
                if shed is not None:            # it keeps its time of day; the stop it sheds may still find a day
                    pid, per_day[k], days[k] = shed
                    spilled.append(pid)
                    continue
                # Still past its end (or the departure): the stop whose leaving brings the end in most goes, even when
                # that costs something else (a meal it then misses is said), until the day ends in time.
                over, pid, ids_k, got = min(trials, default=(0, None, None, None), key=lambda x: x[0])
                if not late(*days[k][:2]) or pid is None or over >= late(*days[k][:2]):
                    break
                per_day[k], days[k] = ids_k, got
                spilled.append(pid)
    # Before a place is left over, the real clock gets a say where the estimate saw no room: a day with slack for the
    # place's shortest visit tries it, and keeps it when nothing that did not fit before comes of it.
    def relocate_for(pid) -> bool:
        """Let a constrained leftover take a flexible stop's stretch when that stop fits another day.
        The layout's minute estimate is conservative; both changed days must pass the real clock and validator."""
        if not takes_meal_slot(trip.by_place[pid]):
            return False
        for k, (cx, r, _) in enumerate(days):
            if not may(k, pid) or not meal_room(k, pid) or base[k].day.intensity == "free":
                continue
            if misfit(*lay(k, [pid])[:2], None) != (0, 0):
                continue
            for moving in list(per_day[k]):
                if moving in anchors or takes_meal_slot(trip.by_place[moving]):
                    continue
                ids_k = [p for p in per_day[k] if p != moving] + [pid]
                got = lay(k, ids_k)
                if misfit(*got[:2], None) > misfit(cx, r, None) or not within(*got[:2]):
                    continue
                for j, (other_cx, other_r, _) in enumerate(days):
                    if j == k or base[j].day.intensity == "free" or not may(j, moving):
                        continue
                    ids_j = [*per_day[j], moving]
                    other = lay(j, ids_j)
                    if misfit(*other[:2], None) <= misfit(other_cx, other_r, None) and within(*other[:2]):
                        per_day[k], days[k], per_day[j], days[j] = ids_k, got, ids_j, other
                        return True
        return False

    for pid in [*sorted(set(leftover)), *spilled]:
        leftover = [p for p in leftover if p != pid]
        need = trip.by_place[pid].visit["short"]
        slack = sorted(((cx.day.end - cx.day.start - sum(i.end - i.start for i in r.items if i.kind not in {"wait", "free"}),
                         -k) for k, (cx, r, _) in enumerate(days)), reverse=True)
        for room, k in slack[:3]:
            k = -k
            recover = sum(max(0, i.end - i.start - trip.by_place[i.place_id].visit["short"])
                          for i in days[k][1].items if i.kind == "visit") if base[k].allow_shrink else 0
            if room + recover < need or pid in per_day[k] or not may(k, pid) or not meal_room(k, pid) or base[k].day.intensity == "free":
                continue
            got = lay(k, [*per_day[k], pid])
            if misfit(*got[:2], None) > misfit(*days[k][:2], None):
                # A place left over is a limit of the frame itself: a time of day yields to it (spec section 5).
                # A dawn time of day restructures the whole day (early start, midday rest): never traded for a stop.
                if any(trip.by_place[i].pins for i in [*per_day[k], pid]):
                    got = lay(k, [*per_day[k], pid], overfull=pid)   # its own dawn may go, not another's
            if misfit(*got[:2], None) <= misfit(*days[k][:2], None) and within(*got[:2]):  # breaks nothing, eats no meal
                per_day[k], days[k] = [*per_day[k], pid], got
                break
        else:
            if not relocate_for(pid):
                leftover.append(pid)
    ctxs = [cx for cx, _, _ in days]
    results = [r for _, r, _ in days]
    for k, (cx, r, pid) in enumerate(days):
        n = cx.day.index + 1
        if pid:
            warnings.append(_warn("early_start", day=n, start=fmt(cx.day.start), name=trip.by_place[pid].name))
        warnings += [_warn("dawn_swapped", day=n, start=fmt(cx.day.start), name=trip.by_place[i].name)
                     for i in per_day[k] if i in trip.by_place and dawn_swapped(trip.by_place[i], cx)]
    warnings.extend(pin_warnings(ctxs, results))
    for cx, r in zip(ctxs, results):
        for note in r.notes:
            code, _, meal = note.partition(":")
            warnings.append(_warn(code, day=cx.day.index + 1, meal=MEAL_NAME.get(meal, meal)))
    violations = validate(ctxs, results, hard, anchors, budget, max_leg)
    return Schedule(per_day, results, ctxs, violations, warnings, tuple(sorted(set(leftover))))


def _route_ctx(cx: DayCtx) -> DayCtx:
    """Bound full-frame subset and pin trials to section 6's local search instead of repeated 7! clocks."""
    return replace(cx, cfg=replace(cx.cfg, exact_n=min(cx.cfg.exact_n,
                   cx.cfg.realistic["seeded_exact_n"]))) if cx.compact_estimates else cx


def simulate_order(order: list, cx: DayCtx, hard: list, budget, max_leg):
    """The user's own order of a day (a reorder), kept as given. A time of day that order cannot keep without breaking
    a physical limit is given up (one place first, the latest; then cumulatively) and the result says which limit
    (spec section 5); otherwise every time of day is held."""
    r = simulate(list(order), cx)
    wrong = {v.kind for v in validate([cx], [r], hard, set(), budget, max_leg)} & PIN_PHYSICAL
    if not wrong:
        return r
    reasons = tuple(sorted(wrong))
    first = {it.place_id: it.start for it in r.items if it.kind == "visit"}
    pinned = [i for i in sorted(order, key=lambda i: -first.get(i, 0)) if cx.places[i].pins
              and pin_window(replace(cx.places[i], pins=()), cx) != pin_window(cx.places[i], cx)]
    trials = [[i] for i in pinned] + [pinned[:n] for n in range(2, len(pinned) + 1)]
    for ids in trials:
        tried = replace(cx, places={**cx.places, **{i: replace(cx.places[i], pins=()) for i in ids}})
        out = simulate(list(order), tried)
        if not {v.kind for v in validate([tried], [out], hard, set(), budget, max_leg)} & PIN_PHYSICAL:
            return replace(out, unpinned=tuple(ids), pin_conflicts=tuple((i, reasons) for i in ids))
    return r


def _unpin(cx: DayCtx, r, day_ids: list, hard: list, budget, max_leg, seed: list | None = None, *, routes=None,
           reasons=(), keep_dawn: str | None = None):
    """A day that fails because places want the same time of day (two bars that both want 18:00, a sunset spot after
    an evening show): give up the time of day of the latest one first, until the day passes. The visit stays; only
    the "be there at sunset / for the music" wish is dropped, and the caller says so. Nothing helps: unchanged."""
    first = {it.place_id: it.start for it in r.items if it.kind == "visit"}
    # keep_dawn: placing that left-over place may cost only evening / sunset wishes, never another stop's dawn.
    pinned = sorted((i for i in day_ids if cx.places[i].pins and not (
        keep_dawn is not None and i != keep_dawn and any(cx.cfg.pins[f]["anchor"] == "sunrise" for f in cx.places[i].pins))), key=lambda i: -first.get(i, 0))
    tried, dropped = cx, []
    route_seed = list(r.order) if seed is not None else None
    for pid in pinned:
        unpinned = replace(tried.places[pid], pins=())
        if pin_window(unpinned, tried) == pin_window(tried.places[pid], tried):
            continue                    # opening hours already made this pin ineffective; its clock cannot change
        tried = replace(tried, places={**tried.places, pid: unpinned})
        dropped.append(pid)
        route_ctx = _route_ctx(tried)
        key_seed = tuple(sorted(day_ids)) if len(day_ids) <= route_ctx.cfg.exact_n else (
            tuple(route_seed) if route_seed is not None else None)
        key = fingerprint((day_key(route_ctx, day_ids), key_seed))
        if routes is None:
            out = order_day(day_ids, route_ctx, seed=route_seed)
        else:
            if key not in routes:
                put(routes, key, order_day(day_ids, route_ctx, seed=route_seed), cx.cfg.cache_entries)
            out = routes[key]
        if not validate([tried], [out], hard, set(), budget, max_leg):
            if reasons:
                out = replace(out, pin_conflicts=tuple((i, tuple(reasons)) for i in dropped))
            return tried, out, dropped
        if route_seed is not None:
            route_seed = list(out.order)       # continue from the last search instead of the original insertion order
    return cx, r, []


def window_override(day: Day, start: int, end: int) -> Day:
    """The user's edit of a day's window (set_day_window). The departure is physical: an edit never moves the day's end
    past it."""
    return replace(day, start=start, end=end if day.depart_by is None else min(end, day.depart_by))


def with_home(trip: Trip, home_id: str | None) -> Trip:
    """The same trip anchored at a different place to sleep (a lodging candidate, or None for the original base):
    same places, same travel matrix, same per-day sun / rain / preference — only where each day starts and ends
    changes, so the day-order cache (now keyed on the start and end node too) still pays off across candidates."""
    tc = trip.decision["trip_context"]
    days = trip_days(tc["context"], trip.cfg, home_id,
                     *(n if trip.points.get(n) else None for n in ("@entry", "@exit")), tc.get("sources"))
    days = [replace(old, start_node=d.start_node, end_node=d.end_node) for d, old in zip(days, trip.days)]   # as prepared
    ctxs = [replace(cx, day=d, home=home_id) for cx, d in zip(trip.ctxs, days)]
    return replace(trip, days=days, ctxs=ctxs)


def itinerary(days: list, results: list) -> list[dict]:
    return [{"day": d.index + 1, "date": d.date.isoformat() if d.date else None, "weekday": d.weekday,
             "window": [fmt(d.start), fmt(d.end)], "method": r.method,
             "items": [_item(i) for i in r.items]} for d, r in zip(days, results)]


def chunk_view(itinerary_days: list, chunk_days: int = 7) -> dict:
    mapping = {it["place_id"]: (d["day"] - 1) // chunk_days for d in itinerary_days
               for it in d["items"] if it["kind"] == "visit"}
    groups = [{"id": start // chunk_days, "start_day": start + 1,
               "end_day": min(start + chunk_days, len(itinerary_days)),
               "places": [pid for pid, k in mapping.items() if k == start // chunk_days]}
              for start in range(0, len(itinerary_days), chunk_days)]
    return {"chunk_assignments": mapping, "chunks": groups}


def travel_load(days: list, results: list) -> list[dict]:
    return [{"day": d.index + 1, "travel_min": r.travel_min, "wait_min": r.wait_min,
             "longest_leg_min": max((i.road_min for i in r.items if i.kind == "travel"), default=0)}
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
        **(chunk_view(itinerary(days, sched.results), trip.cfg.chunk_days) if len(days) > trip.cfg.chunk_days else {}),
        "itinerary": itinerary(days, sched.results),
        "travel_load": travel_load(days, sched.results),
        "time_suitability": time_description(sched.ctxs, sched.results),
        "recommendations": recommend(sched.ctxs, sched.results, decision, trip.by_id),
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
                label = {"rest": {"home": "về chỗ ở nghỉ", "drop_bags": "ghé chỗ ở gửi đồ"}.get(i.get("note"), "nghỉ"),
                         "free": "tự do quanh đây",
                         "busy": i.get("name") or "việc cố định"}.get(i["kind"])
                out.append(span + (WAIT_TEXT.get(i.get("note"), "chờ") if i["kind"] == "wait" else label or i["kind"]))
    for w in plan["warnings"]:
        out.append("! " + w["text"])
    for v in plan["violations"]:
        out.append(f'X {v["kind"]} ngày {(v["day"] + 1) if v["day"] is not None else "-"}: {v["detail"]}'
                   + (" (physical)" if v["physical"] else ""))
    out.append("Hợp lệ." if plan["ok"] else "KHÔNG hợp lệ.")
    return "\n".join(out)
