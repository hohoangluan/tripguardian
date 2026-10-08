"""Runs ③–⑨ on a session (docs/PLACE_DECISION.md §3) and builds the view the web shows. Everything re-runs on each
change (~1.4k records are cheap); the session state (chosen / locked / dropped) is what keeps the invariants."""

from collections import Counter
from dataclasses import dataclass, field

from corpus.serving import load as load_records

from .cards import card, feature_label, value_label
from .curation import pending
from .diversify import display_group, pick, sizes
from .feasibility import evaluate
from .fit import centers, fit
from .model import Cand, role_of
from .rank import score
from .screen import screen
from .trip_days import trip_days
from .window import merge

MISSING_NAME = "Địa điểm chưa có trong dữ liệu"


@dataclass
class Data:
    records: list[dict]
    by_id: dict = field(init=False)

    def __post_init__(self):
        self.by_id = {r["id"]: r for r in self.records}

    @classmethod
    def load(cls) -> "Data":
        return cls(load_records())


@dataclass
class Result:
    view: dict
    cands: dict[str, Cand]
    alternatives: dict[str, list[str]]
    group_of: dict[str, str]
    days: list
    shown: dict[str, list[str]]
    ranked: dict[str, list[str]]


def stub(pid: str) -> dict:
    """A kept place without a serving record: every aspect unknown."""
    return {"id": pid, "status": "VERIFIED", "status_reason": None,
            "identity": {"name": MISSING_NAME, "kind": "POI", "category": None, "category_group": None, "lat": None,
                         "lng": None, "address": None, "area": None},
            "operation": {"hours": None, "price_per_person": None, "entry_fee": None, "visit_minutes": None,
                          "booking": None, "crowd_by_time": None},
            "experience": {}, "environment": {}, "service": {}, "effort": {}, "suitability": {},
            "effort_hint": {"value": "unknown", "kind": "estimate"}, "usable_as": [],
            "provenance": {"as_of": None, "coverage": {}, "voices": 0, "rating_trend": None, "inputs": []},
            "near_duplicate_group": None}


def wanted(si, profile) -> list[str]:
    return list(dict.fromkeys([w.feature for w in si.soft_weights if w.weight > 0]
                              + [x.feature for x in profile.soft if x.weight > 0]))


def _rule_label(reason: str, si, cfg) -> str:
    if reason == "closed_all_trip_days":
        return "Đóng cửa mọi ngày của chuyến"
    f = reason.split(":", 1)[1]
    h = next((x for x in si.hard_filters if x.feature == f), None)
    op = "=" if h and h.op == "eq" else "≠"
    return f"Điều kiện “{feature_label(f, cfg).lower()} {op} {value_label(h.value, cfg) if h else '?'}”"


def run(s, data: Data, cfg) -> Result:
    si, st = s.search_input, s.state
    days = trip_days(si.context, cfg)
    known_days = si.context.days is not None
    wish = set(st.wishlist)
    dropped = {d.place_id for d in st.dropped}
    anchors = [a.place_id for a in si.anchors if a.place_id not in wish | dropped]  # a dropped anchor is gone
    keep = (set(anchors) | set(st.selected)) - wish

    cands: dict[str, Cand] = {}
    for r in data.records:
        role = role_of(r)
        if role or r["id"] in keep:
            cands[r["id"]] = Cand(r, role or "experience", keep=r["id"] in keep)
    for pid in sorted(keep - cands.keys()):
        cands[pid] = Cand(stub(pid), "experience", keep=True, missing=True)
    relaxed = {tuple(x) for x in st.relaxed}
    for c in cands.values():
        screen(c, si, days, relaxed)

    ctrs = centers(si, data.by_id, cfg)
    anchor_areas = {a for pid in anchors if (a := cands[pid].rec["identity"].get("area"))}
    live = [c for c in cands.values() if c.status != "excluded" or c.keep]
    for c in live:
        fit(c, si, days, ctrs, anchor_areas, st.profile, cfg)
    score(live, si, st.profile, cfg)
    group_of = {c.id: display_group(c, cfg) for c in live}

    visited = set(si.novelty.visited) | set(st.profile.visited)
    pool = [c for c in live if not c.keep and c.status == "main" and c.id not in dropped and c.id not in wish
            and c.fit >= cfg.min_context_fit and not (si.novelty.level == "new" and c.id in visited)]
    chosen = [cands[i] for i in st.selected if i in cands]
    size = sizes(si, len(days), sum(1 for a in anchors if cands[a].role == "experience"), cfg)
    reps, alts = [], {}
    for role in ("experience", "meal"):
        k = size[role] - sum(1 for c in chosen if c.role == role and c.id not in anchors)
        r_, a_ = pick([c for c in pool if c.role == role], k, cfg)
        reps += r_
        alts.update(a_)
    for c in chosen:
        g = c.rec.get("near_duplicate_group")
        if g is not None and c.id not in alts:
            same = sorted((x for x in pool if x.rec.get("near_duplicate_group") == g), key=lambda x: (-x.score, x.id))
            if same:
                alts[c.id] = same[:3]

    top = {c.id for c in reps}
    rest = sorted((c for c in pool if c.id not in top), key=lambda c: (-c.score, c.id))
    ranked: dict[str, list[str]] = {}
    for c in [*(x for x in chosen if x.id not in anchors), *reps, *rest]:
        ranked.setdefault(group_of.get(c.id, "sights"), []).append(c.id)

    suggested = next((c.id for c in reps if group_of[c.id] == st.suggest_group), None) if st.suggest_group else None
    want = wanted(si, st.profile)
    labels = cfg.labels["group"]

    def mk(c: Cand) -> dict:
        return card(c, si, cfg, wanted=want, chosen=c.id in st.selected, locked=c.id in st.locked,
                    anchor=c.id in anchors, alternatives=[(x.id, x.name) for x in alts.get(c.id, [])],
                    suggested=c.id == suggested, group=group_of.get(c.id, "sights"), top=c.id in top)

    groups, shown, change = [], {}, {}
    if anchors:
        groups.append({"id": "anchors", "label": labels["anchors"], "cards": [mk(cands[a]) for a in anchors],
                       "total": len(anchors)})
    for gid in [*cfg.display_groups, "meal"]:
        ids = ranked.get(gid, [])
        pinned = {c.id for c in chosen if group_of.get(c.id) == gid}
        win, ch = merge(st.shown.get(gid, []), ids, pinned, cfg)
        if win:
            shown[gid], change[gid] = win, ch
            groups.append({"id": gid, "label": labels[gid], "cards": [mk(cands[i]) for i in win], "total": len(ids)})

    unverified = sorted((c for c in live if not c.keep and c.status == "unverified" and c.id not in dropped),
                        key=lambda c: (-c.score, c.id))
    excluded = Counter(x["reason"] for c in cands.values() if c.status == "excluded" and not c.keep
                       for x in c.checks if x["result"] == "fail")
    feas = evaluate(chosen, si, days, known_days, set(anchors), set(st.locked), ctrs,
                    {f for f in want if f in cfg.timed_features}, cfg)
    pend = pending(st, data.by_id, si, feas, s.first_shortlist, group_of, cfg)

    def name(pid: str) -> str:
        c = cands.get(pid)
        return c.name if c else (data.by_id.get(pid) or stub(pid))["identity"]["name"]

    def wish_reason(pid: str) -> str:
        c = cands.get(pid)
        if c and any(x["kind"] == "physical" and x["result"] == "fail" for x in c.checks):
            return "Đóng cửa mọi ngày của chuyến"
        return "Bạn để dành cho dịp khác"

    view = {
        "version": len(s.history),
        "groups": groups,
        "change": change,
        "shortlist": [x["id"] for g in groups for x in g["cards"]],
        "selected": list(st.selected), "locked": list(st.locked),
        "unverified": {"count": len(unverified), "open": any(h.unknown_policy == "flag" for h in si.hard_filters),
                       "cards": [mk(c) for c in unverified[:cfg.unverified_show]]},
        "excluded": {"by_rule": [{"rule": r, "label": _rule_label(r, si, cfg), "count": n}
                                 for r, n in sorted(excluded.items())]},
        "wishlist": [{"id": p, "name": name(p), "reason": wish_reason(p)} for p in st.wishlist],
        "dropped": [{"id": d.place_id, "name": name(d.place_id), "reason": d.reason} for d in st.dropped],
        "feasibility": feas,
        "pending": pend.model_dump() if pend else None,
        "profile": st.profile.model_dump(),
        "known_days": known_days,
        "days": [{"index": d.index, "date": d.date.isoformat() if d.date else None, "weekday": d.weekday} for d in days],
        "unknowns": list(si.unknowns),
        "unmapped": [*si.unmapped, *st.unmapped],
    }
    return Result(view, cands, {k: [x.id for x in v] for k, v in alts.items()}, group_of, days, shown, ranked)


def why_not(res: Result, pid: str, si, cfg) -> dict:
    """Why a place is not in the shortlist (tool explain_exclusion, docs/PLACE_DECISION.md §6.4)."""
    c = res.cands.get(pid)
    if c is None:
        return {"id": pid, "name": None, "known": False, "status": None, "score": None, "parts": {},
                "reasons": ["Nơi này không có trong dữ liệu đang phục vụ hoặc không dùng được cho lịch trình"]}
    v = res.view
    reasons = []
    if pid in v["shortlist"]:
        reasons.append("Nơi này đang có trong gợi ý")
    elif any(d["id"] == pid for d in v["dropped"]):
        reasons.append("Bạn đã bỏ nơi này")
    elif any(w["id"] == pid for w in v["wishlist"]):
        reasons.append("Bạn để nơi này trong danh sách mong muốn")
    else:
        info = card(c, si, cfg)
        reasons += [f"Bị loại: {t}" for t in info["failed"]]
        reasons += [f"{t} (bạn có thể xem trong mục chưa xác minh)" for t in info["unverified"]]
        if not reasons:
            if c.fit < cfg.min_context_fit:
                reasons.append(f"Xa so với {c.center}" + (f" (≈{c.minutes} phút)" if c.minutes else ""))
            elif si.novelty.level == "new" and pid in si.novelty.visited:
                reasons.append("Bạn đã đi nơi này và muốn thử nơi mới")
            elif any(pid in alts for alts in res.alternatives.values()):
                reasons.append("Giống một nơi đang gợi ý; nằm trong phương án thay thế của nơi đó")
            else:
                reasons.append("Điểm phù hợp thấp hơn các nơi đang gợi ý")
    return {"id": pid, "name": c.name, "known": True, "status": c.status, "reasons": reasons, "score": c.score,
            "parts": c.parts}
