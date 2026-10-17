"""Candidate cards (docs/PLACE_DECISION.md §11) from templates: every line comes from a serving record field or a
rule result, so a card cannot say what the data does not hold."""

from corpus import load_ontology
from corpus.serving import dishes, feature
from requirements import activity_for, applicable, scope_allows

from .model import FIRM, Cand, cost_total, known_for, value
from .wishes import SAID

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


PURPOSE_TEXT = {"relax": "thư giãn", "food_culture": "ăn uống, văn hóa", "nature": "thiên nhiên",
                "explore": "khám phá", "photo": "chụp ảnh"}
SOURCE_TEXT = {"menu_popular": " · theo menu", "menu": " · theo menu", "review_order": " · theo review"}


def wish_text(hit: tuple, rec: dict, cfg, sources: dict | None = None) -> str:
    """One met wish (decision.wishes.lift hit) in the user's words; a dish names where it was written down.
    sources: dish -> best source already looked up for this place (Cand.dish_source), filled here."""
    _, kind, label, _ = hit
    if kind == "dish":
        sources = sources if sources is not None else {}
        if label not in sources:
            found = dishes.search([rec], label, 1)
            sources[label] = max((e["source"] for e in found[0]["evidence"]), key=dishes.SOURCE_RANK.get) if found else None
        return f"Có {label} bạn muốn" + SOURCE_TEXT.get(sources[label], "")
    if kind == "kind":
        return f"Đúng loại {label} bạn tìm"
    if kind == "vibe":
        return f"Hợp phong cách “{label}” bạn chọn"
    if kind == "like":
        return f"Giống {label} bạn thích" if label else "Giống nơi bạn nhắc tới"
    if kind == "group":
        return f"Vì bạn thích {cfg.labels['group'][label].lower()}"
    return f"Hợp chuyến {PURPOSE_TEXT.get(label, label)} ✎"


def _fallback(c: Cand, cfg) -> dict:
    """A card no wish, feature or nearness speaks for still says something true: the larger of its two parts a line
    can state, location (ctx) or how many wrote about it (pop)."""
    w = cfg.weights
    if c.missing:
        text = "Chưa có dữ liệu về nơi này; bạn tự kiểm trước chuyến"
    elif c.minutes is not None and w.get("ctx", 0) * c.parts.get("ctx", 0) >= w.get("pop", 0) * c.parts.get("pop", 0):
        text = f"Cách {c.center} ≈{c.minutes} phút (ước tính)"
    else:
        text = f"{c.rec['provenance'].get('voices') or 0} người đã viết về nơi này"
    return {"text": text, "sid": None}


def _why(c: Cand, anchor: bool, cfg) -> list[dict]:
    """Up to 3 lines: anchor, wishes the user said, matched features, leanings (group / purpose), nearness. Only the
    lines kept are written out."""
    lines = [("anchor", None)] if anchor else []
    lines += [("wish", h) for h in c.wishes if h[1] in SAID]
    lines += [("feature", m) for m in c.matches if m[2] > 0]
    lines += [("wish", h) for h in c.wishes if h[1] not in SAID]
    if c.minutes is not None and c.minutes <= cfg.near_min:
        lines.append(("near", None))

    def text(kind, x) -> dict:
        if kind == "anchor":
            return {"text": "Nơi bạn muốn đến", "sid": None}
        if kind == "wish":
            return {"text": wish_text(x, c.rec, cfg, c.dish_source), "sid": None}
        if kind == "feature":
            return {"text": f"{phrase(x[0], x[1], cfg)}, {x[3]} người nhắc", "sid": x[0]}
        return {"text": f"Gần {c.center}, ≈{c.minutes} phút (ước tính)", "sid": None}

    return [text(k, x) for k, x in lines[:3]] or [_fallback(c, cfg)]


_POLARITY: dict[int, tuple] = {}  # id(cfg) -> (cfg, rows); cfg is a frozen Settings, so the rows are built once


def _polarity_rows(cfg) -> list[tuple[str, str, str]]:
    """(feature id, its record group, its worst value) per polarity feature; a polarity feature the ontology does
    not know is read as 'no value' by feature(), so it is skipped here too."""
    hit = _POLARITY.get(id(cfg))
    if hit is None or hit[0] is not cfg:
        ont = load_ontology().features
        hit = _POLARITY[id(cfg)] = (cfg, [(fid, ont[fid].group, order[-1]) for fid, order in cfg.polarity.items()
                                          if fid in ont and not fid.startswith("fit.")])
    return hit[1]


def _tradeoffs(c: Cand, cfg) -> list[dict]:
    out = [{"text": f["text"], "sid": f["sid"]} for f in c.flags]
    out += [{"text": f"{phrase(f, v, cfg)}, điều bạn muốn tránh", "sid": f} for f, v, contrib, _ in c.matches
            if contrib < 0]
    seen = {x["sid"] for x in out if x["sid"]}
    for fid, group, bad in _polarity_rows(cfg):
        f = c.rec.get(group, {}).get(fid)
        if not f or fid in seen or f["status"] not in FIRM or f["n"] < 2 or f["value"] != bad:
            continue
        out.append({"text": f"{phrase(fid, f['value'], cfg)}, theo {f['n']} người", "sid": fid})
    return out[:3]


_SCOPE_OK: dict[tuple, bool] = {}


def _confidence(c: Cand, wanted, cfg, activity=None, requirements=()) -> dict:
    if c.missing:
        return {"level": "low", "reason": "Chưa có dữ liệu về nơi này."}
    voices = c.rec["provenance"].get("voices") or 0
    selected = activity_for(c.rec, activity, c.role)  # once per card; applicable() would derive it per feature
    by_feature: dict[str, list] = {}
    for r in requirements:
        by_feature.setdefault(r.feature, []).append(r)

    def allows(fid, r) -> bool:  # scope_allows is a pure function of (feature, scope, activity)
        key = (fid, getattr(r, "scope", None), selected)
        if key not in _SCOPE_OK:
            _SCOPE_OK[key] = scope_allows(r if r is not None else {"feature": fid}, selected)
        return _SCOPE_OK[key]

    def relevant(fid):  # same rule as applicable(c.rec, ..., activity, c.role), without re-deriving the activity
        matched = by_feature.get(fid)
        if fid == "wine_tasting_available":  # its rule also reads the record
            return any(applicable(c.rec, r, activity, c.role) for r in matched) if matched else applicable(
                c.rec, {"feature": fid}, activity, c.role)
        return any(allows(fid, r) for r in matched) if matched else allows(fid, None)
    wanted = list(dict.fromkeys(fid for fid in wanted if relevant(fid)))
    found = {f: feature(c.rec, f) for f in wanted}
    missing = [f for f in wanted if found[f] is None]
    shaky = [f for f in wanted if (x := found[f]) and x["status"] != "VERIFIED"]
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
        "price": price, "known_for": known_for(rec), "cost": cost_total(rec),
        "confidence": _confidence(c, wanted, cfg, si.activities.get(c.id), si.soft_weights),
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
