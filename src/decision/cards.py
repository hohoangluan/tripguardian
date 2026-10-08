"""Candidate cards (docs/PLACE_DECISION.md §11) from templates: every line comes from a serving record field or a
rule result, so a card cannot say what the data does not hold."""

from corpus.serving import feature

from .model import FIRM, Cand, value

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


def price_text(rec: dict) -> str | None:
    p = rec["operation"].get("price_per_person")
    lo = p["value"].get("min_vnd") if p else None
    if lo is None:
        return None
    hi = p["value"].get("max_vnd") or lo
    return f"{lo // 1000}k/người" if hi == lo else f"{lo // 1000}k–{hi // 1000}k/người"


def _why(c: Cand, anchor: bool, cfg) -> list[dict]:
    out = [{"text": "Nơi bạn muốn đến", "sid": None}] if anchor else []
    out += [{"text": f"{phrase(f, v, cfg)}, {n} người nhắc", "sid": f} for f, v, contrib, n in c.matches if contrib > 0]
    if c.minutes is not None and c.minutes <= cfg.near_min:
        out.append({"text": f"Gần {c.center}, ≈{c.minutes} phút (ước tính)", "sid": None})
    return out[:3]


def _tradeoffs(c: Cand, cfg) -> list[dict]:
    out = [{"text": f["text"], "sid": f["sid"]} for f in c.flags]
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
    vm = rec["operation"].get("visit_minutes")
    price = price_text(rec)
    trend = (rec["provenance"].get("rating_trend") or {}).get("direction")
    return {
        "id": c.id, "name": c.name, "category": rec["identity"].get("category"), "area": rec["identity"].get("area"),
        "role": c.role, "group": group, "status": c.status, "score": c.score, "parts": c.parts,
        "why": _why(c, anchor, cfg), "tradeoffs": _tradeoffs(c, cfg),
        "visit": {k: vm.get(k) for k in ("short", "typical", "long", "source")} if vm else None,
        "location": {"center": c.center, "km": c.km, "minutes": c.minutes},
        "price": price,
        "confidence": _confidence(c, wanted, cfg),
        "declined": value(rec, "condition_change") == "declined" or trend == "falling",
        "depends_on_unknown": f"Chưa biết ngân sách của bạn; giá khoảng {price}"
        if price and "budget_vnd" in si.unknowns else None,
        "warnings": [warning_text(w, cfg) for w in c.warnings] + ([WARNING["missing_record"]] if c.missing else []),
        "unverified": [f"Chưa xác minh được: {feature_label(x['feature'], cfg).lower()}" for x in c.checks
                       if x["result"] == "unknown"],
        "failed": [_fail_text(x, cfg) for x in c.checks if x["result"] == "fail"],
        "chosen": chosen, "locked": locked, "anchor": anchor,
        "alternatives": [{"id": i, "name": n} for i, n in alternatives], "suggested": suggested, "top": top,
    }
