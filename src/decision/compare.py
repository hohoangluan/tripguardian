"""⑦ Compare two candidates (docs/P3_PLACE_DECISION.md §10): only aspects with evidence on both sides; a side without
evidence is "chưa biết", never a loss; the trip-level sacrifice is a rough estimate."""

from corpus.serving import feature

from .cards import feature_label, value_label
from .model import FIRM, Cand

DAYTIME = ("morning", "noon", "afternoon", "evening")


def _firm(f) -> bool:
    return bool(f) and f["status"] in FIRM and f["n"] >= 2


def _cell(f, cfg) -> str:
    return f"{value_label(f['value'], cfg)} ({f['n']} người)"


def _crowd(c: Cand, days) -> int | None:
    cbt = c.rec["operation"].get("crowd_by_time")
    if not cbt:
        return None
    types = sorted({d.day_type for d in days if d.day_type}) or ["weekday", "weekend"]
    vals = [v for t in types for b in DAYTIME if (v := (cbt.get(t) or {}).get(b)) is not None]
    return round(sum(vals) / len(vals)) if vals else None


def _price(c: Cand) -> int | None:
    p = c.rec["operation"].get("price_per_person")
    lo = p["value"].get("min_vnd") if p else None
    return None if lo is None else int((lo + (p["value"].get("max_vnd") or lo)) / 2)


def _lower(label, aspect, x, y, text) -> dict | None:
    if x is None or y is None or x == y:
        return None
    return {"aspect": aspect, "label": label, "a": text(x), "b": text(y), "better": "a" if x < y else "b"}


def compare(a: Cand, b: Cand, wanted: list[str], days, cfg) -> dict:
    if a.role != b.role:
        raise ValueError("places of different roles are not alternatives")
    rows = []
    for fid, order in cfg.polarity.items():
        fa, fb = feature(a.rec, fid), feature(b.rec, fid)
        if not (_firm(fa) and _firm(fb)) or fa["value"] == fb["value"] or fa["value"] not in order or fb["value"] not in order:
            continue
        rows.append({"aspect": fid, "label": feature_label(fid, cfg), "a": _cell(fa, cfg), "b": _cell(fb, cfg),
                     "better": "a" if order.index(fa["value"]) < order.index(fb["value"]) else "b"})
    for fid in dict.fromkeys(wanted):
        if fid in cfg.polarity:
            continue
        fa, fb = feature(a.rec, fid), feature(b.rec, fid)
        if bool(fa) == bool(fb):
            continue
        rows.append({"aspect": fid, "label": feature_label(fid, cfg), "a": _cell(fa, cfg) if fa else "chưa biết",
                     "b": _cell(fb, cfg) if fb else "chưa biết", "better": "unknown"})
    sacrifice = [r for r in (
        _lower(f"Đi từ {a.center or 'điểm xuất phát'} (ước tính)", "distance", a.minutes, b.minutes, lambda m: f"≈{m} phút"),
        _lower("Độ đông ban ngày (Google)", "crowd_by_time", _crowd(a, days), _crowd(b, days), lambda v: f"{v}%"),
        _lower("Giá mỗi người", "price", _price(a), _price(b), lambda v: f"{v // 1000}k"),
    ) if r]
    ta = (a.rec["operation"].get("visit_minutes") or {}).get("typical")
    tb = (b.rec["operation"].get("visit_minutes") or {}).get("typical")
    if ta and tb and ta != tb:
        sacrifice.append({"aspect": "visit", "label": "Thời gian tham quan (ước tính)", "a": f"{ta} phút",
                          "b": f"{tb} phút", "better": "none"})
    return {"a": {"id": a.id, "name": a.name}, "b": {"id": b.id, "name": b.name}, "rows": rows, "sacrifice": sacrifice}
