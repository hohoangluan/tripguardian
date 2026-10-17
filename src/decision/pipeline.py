"""Runs ③–⑨ on a session (docs/PLACE_DECISION.md §3) and builds the view the web shows. Everything re-runs on each
change (~1.4k records are cheap); the session state (chosen / locked / dropped) is what keeps the invariants."""

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from corpus.snapshot import Region, shared

from . import diet as dietary, frame
from .cards import card, feature_label, value_label
from .chunks import assign_chunks, coverage, describe_chunks
from .curation import pending
from .diversify import pick, sizes, tab
from .feasibility import evaluate
from .geo import km, point
from .fit import centers, fit
from .model import Cand
from .rank import score
from .screen import screen
from .trip_days import trip_days
from .window import change, pages, window
from .wishes import SAID

MISSING_NAME = "Địa điểm chưa có trong dữ liệu"


class Data:
    """The corpus Place Decision reads: one snapshot region. Data(records) builds one in memory (tests, bench)."""

    def __init__(self, records: list[dict] | None = None, region: Region | None = None):
        self.region = region if region is not None else Region.from_records(records or [])
        self.by_id = self.region.by_id

    @property
    def records(self) -> list[dict]:
        return self.region.records()

    @classmethod
    def load(cls, region: str | None = None, *, data_root: Path | None = None, snapshot_version: str | None = None) -> "Data":
        frame.warm()
        kwargs = {"version": snapshot_version} if snapshot_version is not None else {}
        return cls(region=shared(data_root / "snapshot" if data_root is not None else None, **kwargs).region(region).warm())


@dataclass
class Result:
    view: dict
    cands: Mapping[str, Cand]
    alternatives: dict[str, list[str]]
    group_of: dict[str, str]
    days: list
    shown: dict[str, list[str]]
    ranked: dict[str, list[str]]
    chunk_assignments: dict[str, int]
    wishes: tuple = ()  # decision.wishes.build of the run's Search Input
    card_of: Callable[[str], dict] | None = None  # place id -> its card as the view shows it (a ranked or unverified id)
    unverified: list[str] | None = None  # every unverified place, best first (the view carries the first few)
    far: dict[str, tuple[int, str]] | None = None  # hidden as too far: place id -> (minutes, center name)


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


def _lodging_view(si, st) -> dict:
    lod = si.context.lodging
    booked = ({"id": lod.place_id if lod.kind == "corpus" else None, "text": lod.text, "lat": lod.lat, "lng": lod.lng}
              if si.context.lodging_booked == "yes" and lod is not None and lod.lat is not None else None)
    return {"booked": booked, "chosen": st.lodging.model_dump() if st.lodging else None,
            "needed": booked is None and st.lodging is None}


@dataclass
class Row:
    """A pool place before it is built into a Cand: what diversify.pick reads (id, score, rec for the group)."""
    id: str
    score: float
    role: str
    dup: int | None
    rec: dict  # {"id", "identity": {"category_group"}, "usable_as", "near_duplicate_group"}


class Cands(Mapping):
    """Every place one run considered, built into a Cand (same as the per-place run built) only when asked: cards,
    compare, why_not, feasibility."""

    def __init__(self, region, t, si, days, relaxed, ctrs, profile, cfg, keep: set, missing: list[str],
                 made: dict[str, Cand] | None = None):
        self.region, self.t, self.si, self.days, self.relaxed = region, t, si, days, relaxed
        self.ctrs, self.profile, self.cfg, self.keep = ctrs, profile, cfg, keep
        self.missing = set(missing)
        self._made = made if made is not None else {}  # shared by the runs of a session while t.key is the same

    def __contains__(self, pid) -> bool:
        if pid in self.missing:
            return True
        i = self.region.index.get(pid)
        return i is not None and bool(self.t.members[i])

    def __getitem__(self, pid) -> Cand:
        if pid not in self:
            raise KeyError(pid)
        if pid not in self._made or self._made[pid].keep != (pid in self.keep or pid in self.missing):
            if pid in self.missing:
                c = Cand(stub(pid), "experience", keep=True, missing=True)
            else:
                i = self.region.index[pid]
                c = Cand(self.region.record(pid), self.t.role[i], keep=pid in self.keep)
            screen(c, self.si, self.days, self.relaxed)
            if c.status != "excluded" or c.keep:
                fit(c, self.si, self.days, self.ctrs, self.t.anchor_areas, self.profile, self.cfg)
                score([c], self.si, self.profile, self.cfg, voices=self.t.voices, wishes=self.t.wishes)
            self._made[pid] = c
        return self._made[pid]

    def __iter__(self):
        yield from sorted(self.missing)
        yield from (pid for i, pid in enumerate(self.region.ids) if self.t.members[i])

    def __len__(self) -> int:
        return len(self.missing) + int(self.t.members.sum())


def run(s, data: Data, cfg, memo: dict | None = None) -> Result:
    si, st = s.search_input, s.state
    si = si.model_copy(update={'activities': {**si.activities, **st.activities}})
    days = trip_days(si.context, cfg)
    known_days = si.context.days is not None
    wish = set(st.wishlist)
    dropped = {d.place_id for d in st.dropped}
    region = data.region
    # lodging is Planning's (corpus list <city>_stay): never a suggestion, not even when named
    stay = region.stay
    anchors = [a.place_id for a in si.anchors if a.place_id not in wish | dropped | stay]  # a dropped anchor is gone
    keep = (set(anchors) | set(st.selected)) - wish - stay
    missing = sorted(p for p in keep if p not in region.index)
    relaxed = {tuple(x) for x in st.relaxed}

    ctrs = centers(si, data.by_id, cfg)
    t = frame.table(region, si, st.profile, days, relaxed, ctrs, anchors, keep, len(missing), cfg, memo)
    made: dict[str, Cand] = {}
    if memo is not None:
        hit = memo.get("cands")
        if hit and hit[0] == t.key:
            made = hit[1]
        else:
            memo["cands"] = (t.key, made)
    cands = Cands(region, t, si, days, relaxed, ctrs, st.profile, cfg, keep, missing, made)
    rids = region.ids
    live_ix = np.flatnonzero(t.live)
    tab_col = frame.tabs(region, cfg)
    group_of = {rids[i]: tab_col[i] for i in live_ix}  # Lựa chọn's tab (t.group is the wishes' coarser kind)
    for pid in missing:
        group_of[pid] = tab(cands[pid], cfg)

    visited = set(si.novelty.visited) | set(st.profile.visited)
    dup, light = region.column("near_duplicate_group"), region.light
    status = np.array(t.status)
    fit_arr = np.array(t.fit)
    kept = np.array([pid in keep for pid in rids], dtype=bool)
    not_kept = ~(kept | np.array([pid in dropped for pid in rids], dtype=bool))
    free = not_kept & ~np.array([pid in wish for pid in rids], dtype=bool)
    if si.novelty.level == "new":
        free &= ~np.array([pid in visited for pid in rids], dtype=bool)
    # too far from the nearest center (base or city center, and anchors; as fit) is hidden from every tab and the shortlist;
    # a place with no point is never judged far, and kept places (anchors, picks) are never hidden (docs §9.3)
    with np.errstate(invalid="ignore"):
        away = frame.far_minutes(region, ctrs, si.context.mobility, cfg)
        far_ix = np.flatnonzero(t.live & ~kept & (away > cfg.max_travel_min))
    far = {rids[i]: (int(away[i]), min(ctrs, key=lambda c: km(point(region.record(rids[i])), c[1]))[0]) for i in far_ix}
    not_far = np.ones(len(rids), dtype=bool)
    not_far[far_ix] = False
    free &= not_far
    listed_ix = np.flatnonzero(t.live & free & (status == "main"))  # every place the tabs list
    listed = [Row(rids[i], t.score[i], t.role[i], dup[i], light[i]) for i in listed_ix]
    diet = dietary.wanted(si, st.profile, st.unmapped)
    tier = dietary.tiers(region, [p for p in [*st.selected, *(r.id for r in listed)] if group_of.get(p) in dietary.TABS], diet)
    # the shortlist's pool; a place the diet excludes is listed in its tab but never shortlisted
    pool = [r for r, i in zip(listed, listed_ix) if fit_arr[i] >= cfg.min_context_fit and tier.get(r.id, 1) < 3]
    chosen = [cands[i] for i in st.selected if i in cands]
    size = sizes(si, len(days), sum(1 for a in anchors if cands[a].role == "experience"), cfg)
    reps, alts = [], {}
    for role in ("experience", "meal"):
        k = size[role] - sum(1 for c in chosen if c.role == role and c.id not in anchors)
        r_, a_ = pick([c for c in pool if c.role == role], k, cfg, sigs=region.sigs)
        reps += [cands[x.id] for x in r_]
        alts.update({lid: [cands[x.id] for x in v] for lid, v in a_.items()})
    for c in chosen:
        g = c.rec.get("near_duplicate_group")
        if g is not None and c.id not in alts:
            same = sorted((x for x in pool if x.dup == g), key=lambda x: (-x.score, x.id))
            if same:
                alts[c.id] = [cands[x.id] for x in same[:3]]

    # a tab lists its places by score alone, the user's picks among them; "Hợp nhất" marks its best non-picked
    # places, as many as the shortlist (MMR) took from that tab
    # a user who avoids crowds sees the places Google calls busy after every other one of the tab, whatever their score
    avoid = (st.profile.crowd_tolerance or si.pace.crowd_tolerance) == "avoid"
    busy = (frame.busy_mask(region, sorted({d.day_type for d in days if d.day_type}) or ["weekday", "weekend"], cfg)
            if avoid else None)
    crowded = (lambda pid: bool(busy[region.index[pid]]) if pid in region.index else False) if avoid else (lambda pid: False)  # noqa: E731
    ranked: dict[str, list[str]] = {}
    for c in sorted([*(x for x in chosen if x.id not in anchors), *listed],
                    key=lambda c: (tier.get(c.id, 1), crowded(c.id), -c.score, c.id)):
        ranked.setdefault(group_of.get(c.id, "sights"), []).append(c.id)
    picked = {c.id for c in chosen}
    top = set()
    for gid, ids in ranked.items():
        k = sum(1 for c in reps if group_of.get(c.id) == gid)
        top.update([p for p in ids if p not in picked and tier.get(p, 1) < 2][:k])  # never a place the diet does not fit

    suggested = next((c.id for c in reps if group_of[c.id] == st.suggest_group), None) if st.suggest_group else None
    want = wanted(si, st.profile)
    labels = cfg.labels["group"]

    card_memo = memo.setdefault("cards", {}) if memo is not None else None
    selected_set, locked_set, anchor_set = set(st.selected), set(st.locked), set(anchors)

    def mk(c: Cand) -> dict:
        args = dict(chosen=c.id in selected_set, locked=c.id in locked_set, anchor=c.id in anchor_set,
                    alternatives=[(x.id, x.name) for x in alts.get(c.id, [])], suggested=c.id == suggested,
                    group=group_of.get(c.id, "sights"), top=c.id in top)
        if card_memo is None:
            out = card(c, si, cfg, wanted=want, **args)
            if (n := dietary.note(tier.get(c.id, 1), diet)):
                out["tradeoffs"] = [*out["tradeoffs"], {"text": n, "sid": None}]
            return out
        # a card is a pure function of its Cand (shared by the runs of a session while t.key holds), the arguments
        # above and the Search Input parts it reads; a run that changes none of them reuses the card as built
        key = (args, want, si.activities.get(c.id), si.soft_weights, "budget_vnd" in si.unknowns)
        hit = card_memo.get(c.id)
        if hit is None or hit[0] is not c or hit[1] != key:
            hit = card_memo[c.id] = (c, key, card(c, si, cfg, wanted=want, **args))
        out = dict(hit[2])
        if (n := dietary.note(tier.get(c.id, 1), diet)):
            out["tradeoffs"] = [*out["tradeoffs"], {"text": n, "sid": None}]
        return out

    groups, shown, changed = [], {}, {}
    if anchors:
        groups.append({"id": "anchors", "label": labels["anchors"], "cards": [mk(cands[a]) for a in anchors],
                       "total": len(anchors)})
    for gid in cfg.tabs:
        ids = ranked.get(gid, [])
        win, page = window(ids, st.page.get(gid, 0), cfg)
        if win:
            shown[gid], changed[gid] = win, change(st.shown.get(gid, []), win, cfg)
            groups.append({"id": gid, "label": labels[gid], "cards": [mk(cands[i]) for i in win], "total": len(ids),
                           "page": page, "pages": pages(len(ids), cfg), "page_size": cfg.page_size,
                           "offset": page * cfg.page_size})

    unv_ix = np.flatnonzero(t.live & not_kept & not_far & (status == "unverified"))
    unverified = sorted((rids[i] for i in unv_ix), key=lambda p: (-t.score[region.index[p]], p))
    excluded = Counter()
    excl = (status == "excluded") & t.members & ~kept
    for reason, count in t.fails.items():  # failed checks per place, counted as the Counter over c.checks counted them
        if (n := int(count[excl].sum())):
            excluded[reason] += n
    feas = evaluate(chosen, si, days, known_days, set(anchors), set(st.locked), ctrs,
                    {f for f in want if f in cfg.timed_features}, cfg)
    pend = pending(st, data.by_id, si, feas, s.first_shortlist, group_of, cfg)
    allocation = assign_chunks(chosen, st.chunk_assignments, days, cfg)

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
        "change": changed,
        "shortlist": [x["id"] for g in groups for x in g["cards"]],
        "selected": list(st.selected), "locked": list(st.locked),
        "chunk_assignments": allocation,
        "chunks": describe_chunks(chosen, allocation, days),
        "coverage": coverage(chosen, si, days, feas, cfg, st.free_time),
        "unverified": {"count": len(unverified), "open": any(h.unknown_policy == "flag" for h in si.hard_filters),
                       "cards": [mk(cands[p]) for p in unverified[:cfg.unverified_show]]},
        "excluded": {"by_rule": [{"rule": r, "label": _rule_label(r, si, cfg), "count": n}
                                 for r, n in sorted(excluded.items())]},
        "wishlist": [{"id": p, "name": name(p), "reason": wish_reason(p)} for p in st.wishlist],
        "dropped": [{"id": d.place_id, "name": name(d.place_id), "reason": d.reason} for d in st.dropped],
        "feasibility": feas,
        # where the user sleeps, one for the whole trip: `booked` is what Hiểu chuyến đi was told (with a point),
        # `chosen` what the user picked at Lựa chọn (it replaces `booked`); `needed` = neither is known yet
        "lodging": _lodging_view(si, st),
        "pending": pend.model_dump() if pend else None,
        "profile": st.profile.model_dump(),
        "known_days": known_days,
        "days": [{"index": d.index, "date": d.date.isoformat() if d.date else None, "weekday": d.weekday} for d in days],
        "unknowns": list(si.unknowns),
        "unmapped": [*si.unmapped, *st.unmapped],
    }
    return Result(view, cands, {k: [x.id for x in v] for k, v in alts.items()}, group_of, days, shown, ranked, allocation,
                  t.wishes, lambda pid: mk(cands[pid]), unverified, far)


def _unmet(res: Result, pid: str, group: str) -> list[str]:
    """The said wishes that have places in this place's group, and that this place does not meet."""
    out = []
    role = res.cands[pid].role if pid in res.cands else None
    for w in res.wishes:
        if w.kind not in SAID or w.places is None or pid in w.places or w.key == f"like:{pid}":
            continue
        if w.role is not None and role != w.role:  # a dish never applies to a café: it is not why the café ranks lower
            continue
        if any(res.group_of.get(p) == group for p in w.places):
            out.append(f"Chưa thấy ghi món {w.label} ở nơi này" if w.kind == "dish"
                       else f"Chưa khớp mong muốn “{w.label}”" if w.label else "Chưa giống nơi bạn nhắc tới")
    return out


def why_not(res: Result, pid: str, si, cfg) -> dict:
    """Why a place is not in the shortlist (tool explain_exclusion, docs/PLACE_DECISION.md §6.4)."""
    c = res.cands.get(pid)
    if c is None:
        return {"id": pid, "name": None, "known": False, "listed": False, "status": None, "score": None, "parts": {},
                "reasons": ["Nơi này không có trong dữ liệu đang phục vụ hoặc không dùng được cho lịch trình"]}
    v = res.view
    reasons = []
    if pid in v["shortlist"]:
        reasons.append("Nơi này đang có trong gợi ý")
    elif any(d["id"] == pid for d in v["dropped"]):
        reasons.append("Bạn đã bỏ nơi này")
    elif any(w["id"] == pid for w in v["wishlist"]):
        reasons.append("Bạn để nơi này trong danh sách mong muốn")
    elif (g := next((g for g, ids in res.ranked.items() if pid in ids), None)) is not None:
        ids = res.ranked[g]
        k = ids.index(pid)
        reasons.append(f"Nơi này có trong danh sách {cfg.labels['group'][g]}, xếp thứ {k + 1}/{len(ids)}; "
                       f"ở trang {k // cfg.page_size + 1}")
        reasons += _unmet(res, pid, g)
    else:
        info = card(c, si, cfg)
        reasons += [f"Bị loại: {t}" for t in info["failed"]]
        reasons += [f"{t} (bạn có thể xem trong mục chưa xác minh)" for t in info["unverified"]]
        if not reasons:
            if res.far and pid in res.far:
                n, center = res.far[pid]
                reasons.append(f"Xa so với {center} (≈{n} phút, quá giới hạn {cfg.max_travel_min} phút)")
            elif c.fit < cfg.min_context_fit:
                reasons.append(f"Xa so với {c.center}" + (f" (≈{c.minutes} phút)" if c.minutes else ""))
            elif si.novelty.level == "new" and pid in si.novelty.visited:
                reasons.append("Bạn đã đi nơi này và muốn thử nơi mới")
            elif any(pid in alts for alts in res.alternatives.values()):
                reasons.append("Giống một nơi đang gợi ý; nằm trong phương án thay thế của nơi đó")
            else:
                reasons.append("Điểm phù hợp thấp hơn các nơi đang gợi ý")
                reasons += _unmet(res, pid, res.group_of.get(pid, "sights"))
    listed = pid in v["shortlist"] or any(pid in ids for ids in res.ranked.values())
    return {"id": pid, "name": c.name, "known": True, "listed": listed, "status": c.status, "reasons": reasons,
            "score": c.score, "parts": c.parts}
