"""Deterministic read-back and confirmation identity for scheduling inputs."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from decimal import Decimal
from typing import Literal

from .state import Frozen, SearchInput, SoftKey, ontology


class Line(Frozen):
    kind: Literal["said", "guess", "default", "check"]
    text: str
    tab: Literal["trip", "companions", "mobility", "care", "pace", "budget", "lodging", "more"]
    undo: str | None = None


class Readback(Frozen):
    lines: tuple[Line, ...]
    digest: str


def _semantic(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {k: _semantic(v) for k, v in value.items()
                if k not in {"source", "evidence", "confidence", "status", "scope_source", "scope_evidence",
                             "scope_guessed", "issues"}}
    if isinstance(value, (tuple, list)):
        return [_semantic(v) for v in value]
    return value


def plan_digest(si: SearchInput) -> str:
    """Hash scheduling semantics; taste, provenance and confirmation never affect it."""
    context = si.context.model_dump(mode="json")
    context = {k: v for k, v in context.items() if k not in {"experience", "purpose"}}
    data = {"context": _semantic(context), "hard": _semantic(si.hard_filters),
            "anchors": _semantic(si.anchors), "pace": si.pace.level, "max_leg_min": si.pace.max_leg_min,
            "activities": _semantic(si.activities), "time_preferences": _semantic(si.time_preferences)}
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def vnd(amount: int) -> str:
    """Read a VND amount in Vietnamese units without losing fractional units."""
    for unit, label in ((1_000_000_000, "tỷ"), (1_000_000, "triệu"), (1000, "nghìn"), (1, "đồng")):
        if abs(amount) >= unit or unit == 1:
            value = format(Decimal(amount) / unit, "f")
            if "." in value:
                value = value.rstrip("0").rstrip(".")
            return value.replace(".", ",") + " " + label


def build(si: SearchInput) -> Readback:
    """Group facts by edit tab, keeping defaults and inferred values visibly separate."""
    from .questions import HARD_LABEL, SOFT_LABEL

    lines, guesses, defaults, checks = [], [], [], []
    c, sources, frame = si.context, si.sources, si.context.frame

    def part(text, key=None, source=None):
        return text, key, source or sources.get(key, "default")

    def group(tab, parts):
        active = [p for p in parts if p[2] != "default"]
        defaults.extend(p[0] for p in parts if p[2] == "default")
        if not active:
            return
        inferred = [p for p in active if p[2] != "user"]
        if inferred:
            said = [p for p in active if p[2] == "user"]
            for i, item in enumerate(inferred):
                parts = [*said, item] if i == 0 else [item]
                guesses.append(Line(kind="guess", text=" · ".join(p[0] for p in parts), tab=tab, undo=item[1]))
        else:
            lines.append(Line(kind="said", text=" · ".join(p[0] for p in active), tab=tab))

    def dates(day):
        return ("CN" if day.weekday() == 6 else f"T{day.weekday() + 2}") + f" {day:%d/%m}"

    head = []
    if c.start_date:
        head.append(part(dates(c.start_date), "start_date"))
        if c.days:
            end = dates(c.start_date + timedelta(days=c.days - 1))
            if sources.get("days") == sources.get("start_date"):
                head[-1] = part(head[-1][0] + " → " + end, "start_date")
            else:
                head.append(part("đến " + end, "days"))
    variations = []
    if frame and frame.days:
        busy_days, hours = {}, {}
        for i, day in enumerate(frame.days):
            day_key = f"frame.days.{i}"
            start_key = (f"{day_key}.start" if f"{day_key}.start" in sources else
                         "checkin_at" if i == 0 and c.checkin_at is not None and sources.get("checkin_at") != "default" else
                         "frame.arrive" if i == 0 and frame.arrive else
                         "checkin_at" if i == 0 and len(frame.days) > 1 else "frame.day_start")
            end_key = (f"{day_key}.end" if f"{day_key}.end" in sources else
                       "checkout_at" if i == len(frame.days) - 1 and c.checkout_at is not None and sources.get("checkout_at") != "default" else
                       "frame.leave" if i == len(frame.days) - 1 and frame.leave else
                       "checkout_at" if i == len(frame.days) - 1 and len(frame.days) > 1 else "day_end")
            for key, clock, label, boundary in (
                (start_key, day.start, "từ", i == 0),
                (end_key, day.end, "xong", i == len(frame.days) - 1),
            ):
                name = "ngày cuối" if label == "xong" and boundary else f"ngày {i + 1}"
                text = f"{name} {label} {clock}"
                moment = frame.arrive if label == "từ" and i == 0 else frame.leave if label == "xong" and boundary else None
                if moment:
                    how = {"plane": "bay", "bus": "xe khách", "self": "tự đi"}.get(moment.how, "")
                    reason = (" tới" if how else "tới") if label == "từ" else ("" if how else "về")
                    reason_text = f"{how}{reason} {moment.at[11:16].lstrip('0')}"
                    moment_key = "frame.arrive" if label == "từ" else "frame.leave"
                    if sources.get(moment_key, "default") == sources.get(key, "default"):
                        text += f" ({reason_text})"
                    else:
                        head.append(part(reason_text, moment_key))
                item = part(text, key)
                if not boundary:
                    identity = (label, clock, item[2], key if item[2] not in {"user", "default"} else None)
                    hours.setdefault(identity, []).append(i + 1)
                elif item[2] == "default":
                    defaults.append(text)
                else:
                    head.append(item)
            intensity_key = f"{day_key}.intensity"
            if day.intensity != "normal" and intensity_key in sources:
                label = {"free": "để trống lịch", "light": "thong thả", "full": "đi nhiều nơi"}[day.intensity]
                variations.append(part(f"Ngày {i + 1}: {label}", intensity_key))
            for busy in day.busy:
                for label in busy.labels:
                    key = (label, busy.start, busy.end, busy.where)
                    busy_days.setdefault(key, []).append(i + 1)
        for (label, clock, source, key), days in hours.items():
            variations.append(part(f"Ngày {', '.join(map(str, days))} {label} {clock}", key, source))
        for (label, start, end, where), days in busy_days.items():
            when = "mọi ngày" if len(days) == len(frame.days) else "ngày " + ", ".join(map(str, days))
            location = " ở chỗ ở" if where == "lodging" else ""
            variations.append(part(f"{label} {start}–{end}{location} ({when})", f"frame.busy.{label}"))
        if frame.issues:
            checks.append("giờ mong muốn cần điều chỉnh theo giờ đến, giờ về và thời gian còn lại trong ngày")
    else:
        checks.append("khung giờ và bữa ăn chưa được xác định")
    group("trip", head)
    group("trip", variations)

    companions = []
    if c.people:
        companions.append(part(f"{c.people} người", "people"))
    if c.companions:
        companions.append(part(", ".join(ontology().companions[x].vi for x in c.companions if x in ontology().companions), "companions"))
    if c.companions_other:
        companions.append(part(", ".join(c.companions_other), source="user"))
    group("companions", companions)

    mobility = []
    if c.mobility:
        mobility.append(part({"motorbike": "Xe máy", "car": "Ô tô", "walk": "Đi bộ"}[c.mobility], "mobility"))
    if c.driver:
        mobility.append(part("thuê tài xế" if c.driver == "hired" else "tự lái", "driver"))
    if si.pace.max_leg_min:
        mobility.append(part(f"mỗi chặng tối đa {si.pace.max_leg_min} phút", "max_leg_min"))
    if frame and frame.drive_day_min is not None:
        mobility.append(part(f"lái tối đa {frame.drive_day_min} phút/ngày", "frame.drive_day_min"))
    group("mobility", mobility)
    if c.lodging:
        group("lodging", [part("Chỗ ở: " + c.lodging.text, "lodging")])

    pace = []
    if si.pace.level:
        pace.append(part({"slow": "Thong thả", "normal": "Vừa phải", "packed": "Đi nhiều nơi"}[si.pace.level], "pace"))
    if frame:
        if frame.rest:
            pace.append(part(f"nghỉ {frame.rest.rest_min} phút sau mỗi {frame.rest.every_min} phút", "frame.rest"))
        meals = frame.meals
        names = {"breakfast": "bữa sáng", "lunch": "bữa trưa", "dinner": "bữa tối"}
        text = f"ăn {3 - len(meals.skip)} bữa mỗi ngày"
        if meals.skip:
            text += ", bỏ " + ", ".join(names[x] for x in meals.skip)
        if meals.breakfast_at_lodging:
            text += "; ăn sáng tại chỗ ở"
        if meals.snacks:
            text += "; có ăn nhẹ"
        if meals.shift_min:
            text += f"; giờ ăn xê dịch {meals.shift_min} phút"
        pace.append(part(text, "frame.meals"))
        if frame.pattern:
            pace.append(part("xen kẽ hoạt động phù hợp với trẻ em", "frame.pattern"))
    group("pace", pace)

    care = []
    for hard in si.hard_filters:
        label = HARD_LABEL.get(hard.feature) or "; ".join(dict.fromkeys(e.quote for e in hard.evidence if e.quote))
        if not label and hard.feature == "coach_access":
            label = "đường vào phù hợp xe lớn"
        if label:
            care.append(part(label, source="user" if hard.evidence else "default"))
        else:
            checks.append("có giới hạn cần kiểm tra khi chọn địa điểm")
    group("care", care)
    if c.budget_intent:
        b = c.budget_intent
        scope = {"trip_total": "cả nhóm cho chuyến đi", "per_day": "cả nhóm mỗi ngày",
                 "per_person": "mỗi người cho chuyến đi", "per_person_day": "mỗi người mỗi ngày"}[b.scope]
        group("budget", [part("Ngân sách " + vnd(b.amount), "budget_vnd", b.source),
                         part(scope, "budget_scope", "inferred" if b.scope_guessed else b.scope_source)])
    elif c.budget_unlimited:
        group("budget", [part("Không giới hạn ngân sách", "budget_unlimited")])

    more = []
    if si.anchors:
        must = sum(a.priority == "must" for a in si.anchors)
        more.append(part(f"Đã chọn {len(si.anchors)} điểm, {must} điểm bắt buộc đến", source="user"))
    for soft in si.soft_weights:
        label = SOFT_LABEL.get(f"{soft.feature}={soft.value}") or "; ".join(dict.fromkeys(e.quote for e in soft.evidence if e.quote))
        if label and soft.weight:
            item = part(("Thích: " if soft.weight > 0 else "Tránh: ") + label.lower(),
                        "soft:" + str(SoftKey(feature=soft.feature, value=soft.value,
                                             context=tuple(sorted((soft.context or {}).items())))), soft.source)
            if soft.source not in {"user", "default"}:
                group("more", [item])
            else:
                more.append(item)
    if frame:
        periods = {"morning": "buổi sáng", "midday": "buổi trưa", "afternoon": "buổi chiều",
                   "evening": "buổi tối", "daytime": "ban ngày", "sunrise": "lúc bình minh", "sunset": "lúc hoàng hôn"}
        for period in frame.periods:
            more.append(part(f"{period.activity or 'Hoạt động ưu tiên'} {periods[period.period]}", source="user"))
        if frame.periods:
            checks.append("chưa kiểm được nơi đẹp nhất theo buổi")
        for minutes in frame.visit.values():
            more.append(part(f"một điểm đã chọn cần {minutes} phút tham quan", source="user"))
    group("more", more)
    checks.extend(si.unmapped)

    # Keep the whole card compact even when every said group and several guesses are present.
    limit = max(1, min(3, 12 - len(lines) - bool(defaults) - bool(checks)))
    if len(guesses) > limit:
        tail = guesses[limit - 1:]
        guesses = guesses[:limit - 1] + [Line(kind="guess", text=" · ".join(l.text for l in tail), tab=tail[0].tab)]
    lines.extend(guesses)
    if defaults:
        lines.append(Line(kind="default", text="Mặc định: " + " · ".join(dict.fromkeys(defaults)), tab="trip"))
    if checks:
        lines.append(Line(kind="check", text="Tự kiểm: " + "; ".join(dict.fromkeys(checks)), tab="more"))
    return Readback(lines=tuple(lines), digest=plan_digest(si))
