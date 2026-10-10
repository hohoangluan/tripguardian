"""Candidate cards (docs/P3_PLACE_DECISION.md §11) from templates: every line comes from a serving record field or a
rule result, so a card cannot say what the data does not hold."""

from corpus.serving import feature

from .model import FIRM, Cand, day_visit, value
from .rank import fit_level

WARNING = {"hours_unknown": "Chưa có giờ mở cửa",
           "hours_outdated": "Giờ mở cửa có thể đã đổi, kiểm tra lại trước chuyến",
           "missing_record": "Chưa có trong dữ liệu đang phục vụ (có thể đã đóng cửa)"}


def feature_label(fid: str, cfg) -> str:
    return cfg.labels["feature"].get(fid, fid.replace("_", " "))


def value_label(v: str, cfg) -> str:
    return cfg.labels["value"].get(v, v)


def phrase(fid: str, val: str, cfg) -> str:
    return feature_label(fid, cfg) if val == "present" else f"{feature_label(fid, cfg)}: {value_label(val, cfg)}"


def warning_text(code: str, cfg) -> str:
    if code.startswith("uncertain_value:"):
        return f"{feature_label(code.split(':', 1)[1], cfg)}: chưa xác nhận chắc"
    return WARNING.get(code, code)


def vnd(n: int) -> str:
    """80000 -> "80k", 1200000 -> "1,2 triệu"."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".").replace(".", ",") + " triệu"
    return f"{round(n / 1000)}k"


def price_text(rec: dict) -> str | None:
    """Google's price band per person: "₫1–100K" is "dưới 100k", "Trên 500K" is "từ 500k"."""
    p = rec["operation"].get("price_per_person")
    lo, hi = (p["value"].get("min_vnd"), p["value"].get("max_vnd")) if p else (None, None)
    if not lo and not hi:
        return None
    if not lo or lo < 1000:
        return f"dưới {vnd(hi)}/người"
    if not hi:
        return f"từ {vnd(lo)}/người"
    return f"khoảng {vnd(lo)}/người" if hi == lo else f"{vnd(lo)}–{vnd(hi)}/người"


def fee_text(rec: dict) -> str | None:
    """Entry fee when the price band says nothing: an estimate in VND, or free by what authors say."""
    fee = (rec["operation"].get("entry_fee") or {}).get("typical_vnd")
    if fee:
        return f"vé khoảng {vnd(fee)}"
    f = feature(rec, "entry_fee")
    return "vào cửa miễn phí" if f and f["status"] in FIRM and f["value"] == "free" and f["n"] >= 2 else None


WHY_MIN = 0.1  # a match that adds less than this to the preference fit is incidental, not a reason to show


def _why(c: Cand, anchor: bool, cfg) -> list[dict]:
    out = [{"text": "Nơi bạn muốn đến", "sid": None}] if anchor else []
    out += [{"text": f"{phrase(f, v, cfg)}, {n} người nhắc", "sid": f} for f, v, contrib, n in c.matches
            if contrib >= WHY_MIN]
    if c.minutes is not None and c.minutes <= cfg.near_min:
        out.append({"text": f"Gần {c.center}, ≈{c.minutes} phút (ước tính)", "sid": None})
    return out[:3]


TRIP_WIDE = {"rain"}  # flags true of every outdoor place this trip: said once above the list (pipeline `notes`)


def _tradeoffs(c: Cand, cfg) -> list[dict]:
    out = [{"text": f["text"], "sid": f["sid"]} for f in c.flags if f["code"] not in TRIP_WIDE]
    out += [{"text": f"{phrase(f, v, cfg)}, điều bạn muốn tránh", "sid": f} for f, v, contrib, _ in c.matches
            if contrib < 0]
    seen = {x["sid"] for x in out if x["sid"]}
    for fid, order in cfg.polarity.items():
        f = feature(c.rec, fid)
        if fid in seen or not f or f["status"] not in FIRM or f["n"] < 2 or f["value"] != order[-1]:
            continue
        out.append({"text": f"{phrase(fid, f['value'], cfg)}, theo {f['n']} người", "sid": fid})
    return out[:3]


def _confidence(c: Cand, wanted, cfg) -> dict:
    if c.missing:
        return {"level": "low", "reason": "Chưa có dữ liệu về nơi này."}
    voices = c.rec["provenance"].get("voices") or 0
    wanted = list(dict.fromkeys(wanted))
    missing = [f for f in wanted if feature(c.rec, f) is None]
    shaky = [f for f in wanted if (x := feature(c.rec, f)) and x["status"] != "VERIFIED"]
    reason = f"{voices} người đã viết về nơi này"
    if missing:
        reason += "; chưa có bằng chứng về " + ", ".join(feature_label(f, cfg).lower() for f in missing)
    if shaky:
        reason += "; chưa chắc: " + ", ".join(feature_label(f, cfg).lower() for f in shaky)
    if not wanted:
        level = "high" if voices >= 40 else "medium" if voices >= 10 else "low"
    else:
        bad = len(missing) + len(shaky)
        level = "high" if bad == 0 else "low" if bad * 2 > len(wanted) else "medium"
    return {"level": level, "reason": reason + "."}


def _fail_text(x: dict, cfg) -> str:
    if x["kind"] == "physical":
        return "Đóng cửa mọi ngày của chuyến"
    if x["op"] == "eq":
        return f"{feature_label(x['feature'], cfg)}: không phải {value_label(x['value'], cfg)}"
    return f"{feature_label(x['feature'], cfg)}: {value_label(x['value'], cfg)}"


def card(c: Cand, si, cfg, *, wanted=(), chosen=False, locked=False, anchor=False, alternatives=(), suggested=False,
         group="", top=False) -> dict:
    rec = c.rec
    vm = day_visit(rec, cfg)
    band = price_text(rec)
    price = band or fee_text(rec)
    trend = (rec["provenance"].get("rating_trend") or {}).get("direction")
    return {
        "id": c.id, "name": c.name, "category": rec["identity"].get("category"), "area": rec["identity"].get("area"),
        "role": c.role, "group": group, "status": c.status, "score": c.score, "parts": c.parts,
        "fit": {"stars": c.stars, "level": fit_level(c.stars, cfg)} if c.stars is not None else None,
        "why": _why(c, anchor, cfg), "tradeoffs": _tradeoffs(c, cfg),
        "outdoor": any(f["code"] == "rain" for f in c.flags),
        "visit": {k: vm.get(k) for k in ("short", "typical", "long", "source", "stay")} if vm else None,
        "location": {"center": c.center, "km": c.km, "minutes": c.minutes},
        "price": price,
        "confidence": _confidence(c, wanted, cfg),
        "declined": value(rec, "condition_change") == "declined" or trend == "falling",
        "depends_on_unknown": f"Chưa biết ngân sách của bạn; giá {band}"
        if band and "budget_vnd" in si.unknowns else None,
        "warnings": [warning_text(w, cfg) for w in c.warnings] + ([WARNING["missing_record"]] if c.missing else []),
        "unverified": [f"Chưa xác minh được: {feature_label(x['feature'], cfg).lower()}" for x in c.checks
                       if x["result"] == "unknown"],
        "failed": [_fail_text(x, cfg) for x in c.checks if x["result"] == "fail"],
        "chosen": chosen, "locked": locked, "anchor": anchor,
        "alternatives": [{"id": i, "name": n} for i, n in alternatives], "suggested": suggested, "top": top,
    }
