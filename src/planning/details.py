"""What the serving `details` of a place change in a plan (docs/PLANNING.md §Chi tiết địa điểm): what a visit costs one
person, the times of day reviewers call best or worst, the last entry, the season, a dangerous road after dark, and
what to prepare. Pure; a place without details changes nothing.

Only what the record serves counts. Every figure here is an estimate from earlier visitors except an official last entry,
which is a hard limit on when a visit may start.
"""

from corpus.serving import feature

from .model import Place
from .settings import Settings, fmt, to_min

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
SCAM_TEXT = {"parking": "gửi xe", "photo": "chụp ảnh", "tout": "cò mồi", "forced_purchase": "ép mua hàng",
             "menu_price": "giá món", "rental": "thuê đồ"}
WARNING_TEXT = {
    "season_avoid": "Ngày {day}: {name}: tháng {month} không phải mùa đẹp của nơi này (theo người đã đi).",
    "last_entry_review": "Ngày {day}: {name}: theo người đã đi, nơi này ngừng nhận khách lúc {time}; bạn tới {start}, gọi hỏi trước.",
    "night_road": "Ngày {day}: {name}: đi xe máy về sau hoàng hôn trên đường tối nguy hiểm; nên rời sớm hơn.",
}


def block(rec: dict) -> dict:
    return rec.get("details") or {}


def timing(rec: dict) -> dict:
    return block(rec).get("timing") or {}


def total_cost(rec_details: dict | None, people: int) -> int | None:
    """What a visit costs one person (entry + parking from the details), plus a price for a vehicle or a group shared by
    the party. None without a total."""
    cost = (rec_details or {}).get("cost") or {}
    total = cost.get("total_vnd")
    if not total:
        return None
    party = sum(x.get("amount_vnd") or 0 for x in cost.get("per_party") or [])
    return int(total["base"] + round(party / max(1, people)))


def extras_vnd(rec: dict) -> int:
    """What the optional extras (rides, rentals, games) could add for one person, at most."""
    total = (block(rec).get("cost") or {}).get("total_vnd")
    return max(0, total["with_extras"] - total["base"]) if total else 0


def official_last_entry(place: Place) -> int | None:
    """Minutes of the last entry when the place's own site gives it: no visit may start after it."""
    le = timing(place.rec).get("last_entry")
    return to_min(le["time"]) if le and le.get("source") == "official" else None


def _windows(window: dict, cfg: Settings) -> list[tuple[int, int]]:
    tod = cfg.time_suitability.get("tod") or {}
    return [(to_min(tod[k][0]), to_min(tod[k][1])) for k, n in (window.get("by_time_of_day") or {}).items()
            if n and k in tod]


def timing_delta(place: Place, start: int, cfg: Settings, *, end: int | None = None) -> float:
    """Planning minutes weighted by the visit's overlap with review-backed best and avoid periods.
    Conflicting periods cancel where they overlap; without an end, score the start time."""
    t = timing(place.rec)
    best = _windows(t.get("best_time") or {}, cfg)
    avoid = _windows(t.get("avoid_time") or {}, cfg)
    end = start + 1 if end is None else end
    if end <= start:
        return 0.0
    boundaries = sorted({start, end} | {max(start, min(end, v)) for window in best + avoid for v in window})
    ts = cfg.time_suitability
    delta = 0.0
    for a, b in zip(boundaries, boundaries[1:]):
        good = any(lo <= a < hi for lo, hi in best)
        bad = any(lo <= a < hi for lo, hi in avoid)
        weight = ts.get("timing_penalty", 0.0) if bad and not good else -ts.get("timing_bonus", 0.0) if good and not bad else 0.0
        delta += (b - a) * weight
    return delta / (end - start)


def firm(place: Place, fid: str) -> str | None:
    """The served value of a feature when it is VERIFIED or OUTDATED, else None."""
    f = feature(place.rec, fid)
    return f["value"] if f and f["status"] in ("VERIFIED", "OUTDATED") else None


def night_road(place: Place, mobility: str | None, end: int, sun: tuple[int, int] | None) -> bool:
    """On a motorbike, the visit ends after sunset and the road there is dangerous in the dark (a firm served value)."""
    return firm(place, "night_road_risk") == "present" and mobility == "motorbike" and sun is not None and end > sun[1]


def _trip_months(ctxs: list, decision: dict) -> dict[int, int | None]:
    month = decision["trip_context"]["context"].get("month")
    return {cx.day.index: cx.day.date.month if cx.day.date else month for cx in ctxs}


def season(place: Place, month: int | None) -> str | None:
    """avoid | best | None for the month of the trip."""
    t = timing(place.rec)
    if month is None:
        return None
    return "avoid" if month in (t.get("avoid_months") or []) else "best" if month in (t.get("best_months") or []) else None


def plan_notes(ctxs: list, results: list, decision: dict, weather: dict | None = None, places: dict | None = None) -> dict:
    """{"warnings": [...], "checklist": [...]} for a laid-out plan, from its visits: a season to avoid, a last entry
    only reviewers give, a dark road on a motorbike; what to bring, book and watch for. A fog line appears only when the
    weather source says the day is foggy. places: every place of the trip, for a stop the day's context lacks."""
    mobility = decision["trip_context"]["context"].get("mobility")
    months = _trip_months(ctxs, decision)
    warnings, checklist = [], []
    for cx, r in zip(ctxs, results):
        n, month = cx.day.index + 1, months[cx.day.index]
        foggy = bool(cx.day.date and ((weather or {}).get(cx.day.date.isoformat()) or {}).get("fog"))
        for it in (i for i in r.items if i.kind == "visit"):
            p = cx.places.get(it.place_id) or (places or {}).get(it.place_id)  # a place added after the day was built
            if p is None:
                continue
            at = {"day": n, "name": p.name}
            if season(p, month) == "avoid":
                warnings.append({"code": "season_avoid", "text": WARNING_TEXT["season_avoid"].format(month=month, **at)})
            le = timing(p.rec).get("last_entry")
            if le and le.get("source") != "official" and it.start > to_min(le["time"]):
                warnings.append({"code": "last_entry_review", "text": WARNING_TEXT["last_entry_review"].format(
                    time=le["time"], start=fmt(it.start), **at)})
            if night_road(p, mobility, it.end, cx.sun):
                warnings.append({"code": "night_road", "text": WARNING_TEXT["night_road"].format(**at)})
            add = lambda kind, text: checklist.append({"day": n, "place_id": p.id, "name": p.name, "kind": kind,  # noqa: E731
                                                       "text": text})
            if season(p, month) == "best":
                add("season", f"{p.name}: đúng mùa đẹp của nơi này.")
            for x in block(p.rec).get("bring") or []:
                add("bring", f"{p.name}: mang theo {x['text']}.")
            for x in block(p.rec).get("booking") or []:
                add("booking", f"{p.name}: {x['text']}.")
            if (stage := firm(p, "scam_stage")):
                add("scam", f"{p.name}: dễ bị chặt chém ở khâu {SCAM_TEXT.get(stage, stage)}, hỏi giá trước.")
            if firm(p, "cold") == "present":
                add("cold", f"{p.name}: lạnh hơn thường, mang áo ấm.")
            if foggy and firm(p, "fog_blocks_view") == "present":
                add("fog", f"{p.name}: dự báo sương mù, view có thể bị che hết.")
            for x in timing(p.rec).get("schedule") or []:
                if cx.day.weekday in (x.get("days") or []):
                    add("schedule", f"{p.name}: hôm nay có {x['text']}.")
    return {"warnings": warnings, "checklist": checklist}
