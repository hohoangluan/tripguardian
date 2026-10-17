"""③-⑤ for every place of a corpus snapshot region at once (docs/PLACE_DECISION.md §6-8). The per-place functions
(screen.py, fit.py, rank.py) stay the definition and build the cards; this module must give the same status, fit and
score for every place (tests/decision/test_frame.py, tests/decision/test_equivalence.py). Sums run in the reference
order, vectorised over places, float64; rounding is Python's round()."""

import hashlib
import json
from dataclasses import dataclass
from functools import cache

import numpy as np

from corpus import load_ontology
from requirements import activity_for, scope_allows

from .fit import DAYTIME, NEEDS, radius, trip_companions
from .model import FIRM, role_of
from .rank import wants
from .trip_days import DAYS
from .wishes import build as build_wishes

SPECIAL = {"venue_category", "activity", "wine_tasting_available"}  # hard_result has its own rules for these
PROTECTED = {"effort", "suitability"}                                # hard_result: no uncertain_value pass
SOFT_SPECIAL = {"wine_tasting_available"}                            # applicable() has its own rule for it


@cache
def _ontology():
    return load_ontology()  # corpus.ontology.load parses the YAML on every call


def warm() -> None:
    """Load what the first run would otherwise load (the ontology file)."""
    _ontology()


def roles(region, overrides: dict[str, str], keep: set[str]) -> tuple[list, list]:
    """Final role and activity of every place as pipeline.run sets them. An `activities` override and a kept place
    without a role are recomputed with the per-place functions."""
    role = region.places["role"].to_list()
    act = region.places["activity"].to_list()
    for pid in set(overrides) | keep:
        i = region.index.get(pid)
        if i is None:
            continue
        rec = region.record(pid)
        r = role_of(rec)
        a = activity_for(rec, overrides.get(pid), r)
        if r and a == "eating":
            r = "meal"
        elif r and a:
            r = "experience"
        if r is None and pid in keep:
            r = "experience"
        role[i] = r
        act[i] = activity_for(rec, overrides.get(pid), r)
    return role, act


@dataclass
class Screen:
    status: list
    fails: dict


def _applies(h, act: list) -> np.ndarray:
    allowed = {a: scope_allows(h, a) for a in set(act)}
    return np.array([allowed[a] for a in act], dtype=bool)


def _generic(region, h) -> np.ndarray:
    """pass | fail | unknown of one feature filter for every place, ignoring whether it applies (requirements.hard_result
    after applicable())."""
    col = region.feature(h.feature)
    eqv = col.eq(h.value)
    if h.op == "eq":
        return np.where(~col.exists | ~col.firm, "unknown",
                        np.where(~eqv, "fail", np.where(col.only(h.value), "pass", "unknown")))
    has = col.has(h.value)
    out = np.where(~col.exists, "unknown",
                   np.where(eqv, np.where(col.firm, "fail", "unknown"),
                            np.where(has | ~col.firm, "unknown", "pass")))
    f = _ontology().features.get(h.feature)
    if f is not None and f.group not in PROTECTED:
        up = (out == "unknown") & col.exists & col.uncertain & ~eqv & ~has
        out = np.where(up, "pass", out)
    return out


def _hard(region, h, act: list) -> np.ndarray:
    """pass | fail | unknown | not_applicable of one generic hard filter for every place (requirements.hard_result)."""
    return np.where(_applies(h, act), _generic(region, h), "not_applicable")


WINE = {"wine_tasting", "tasting", "alcohol_consumption", "drinking"}
ALCOHOL_SERVING = {"tasting", "drinking", "coffee", "eating"}


def _match(match: np.ndarray, h) -> np.ndarray:
    return np.where(match == (h.op == "eq"), "pass", "fail")


def _hard_special(region, h, act: list, overrides: dict) -> np.ndarray:
    """venue_category, activity and wine_tasting_available: requirements.hard_result's own rules, over the columns."""
    unknown = np.array(["unknown"])
    if h.feature == "venue_category":
        actual = region.column("category_for")
        return np.where(np.array([a is None for a in actual]), unknown, _match(np.array([a == h.value for a in actual]), h))
    if h.feature == "activity":
        no_act = np.array([a is None for a in act])
        is_ = np.array([a == h.value for a in act])
        if h.value != "alcohol_consumption":
            return np.where(no_act, unknown, _match(is_, h))
        alc = region.feature("alcohol_required")
        direct = np.array([a in {"wine_tasting", "alcohol_consumption"} for a in act])
        serving = np.array([a in ALCOHOL_SERVING for a in act])
        tasting = np.array([a == "tasting" for a in act])
        single = np.array([d is not None and set(d) == {v} for d, v in zip(alc.dist, alc.value)], dtype=bool)
        clear = alc.firm & single  # one value, nobody contradicts it
        match = direct | (serving & clear & alc.eq("yes"))
        unsure = serving & ((~alc.exists & tasting) | (alc.exists & ~clear))
        return np.where(no_act | unsure, unknown, _match(match, h))
    # wine_tasting_available: applicable only to drinking-like activities, or when the place is known to offer it
    sel_in = np.array([a in WINE for a in act])
    override = np.array([pid in overrides for pid in region.ids], dtype=bool)
    col = region.feature(h.feature)
    app = np.where(override, sel_in, col.exists | sel_in | np.array([a is None for a in act]))
    return np.where(app, _generic(region, h), "not_applicable")


def screen_table(region, si, days, relaxed: set, role: list, act: list) -> Screen:
    n = len(region.ids)
    fails: dict[str, np.ndarray] = {}
    unknown = np.zeros(n, dtype=bool)
    if not any(d.weekday is None for d in days):  # screen.closed_all_days
        mask = 0
        for d in days:
            mask |= 1 << DAYS.index(d.weekday)
        p = region.places
        closed = ((p["hours_status"] == "VERIFIED").fill_null(False).to_numpy()
                  & p["has_hours_value"].to_numpy()
                  & ((p["open_mask"].to_numpy() & mask) == 0))
        fails["closed_all_trip_days"] = closed.astype(np.int32)
    for h in si.hard_filters:
        res = _hard_special(region, h, act, si.activities) if h.feature in SPECIAL else _hard(region, h, act)
        skip = np.array([(pid, h.feature) in relaxed for pid in region.ids], dtype=bool) if relaxed else np.zeros(n, bool)
        fail = (res == "fail") & ~skip
        key = f"hard:{h.feature}"
        fails[key] = fails.get(key, np.zeros(n, np.int32)) + fail.astype(np.int32)
        unknown |= (res == "unknown") & ~skip
    any_fail = np.zeros(n, dtype=bool)
    for v in fails.values():
        any_fail |= v > 0
    status = np.where(any_fail, "excluded", np.where(unknown, "unverified", "main")).tolist()
    return Screen(status, fails)


def _round(xs) -> list[float]:
    return [round(x, 4) for x in np.asarray(xs, dtype=np.float64).tolist()]


def far_minutes(region, ctrs: list, mobility: str | None, cfg) -> np.ndarray:
    """Travel minutes (decision.geo.minutes' formula) from the NEAREST of `ctrs` (as fit_table) to every place; NaN
    where the place has no point."""
    p = region.places
    la1, lo1 = np.radians(p["lat"].to_numpy()), np.radians(p["lng"].to_numpy())
    d = np.full(len(region.ids), np.inf)
    for _, (qlat, qlng) in ctrs:
        la2, lo2 = np.radians(qlat), np.radians(qlng)
        h = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
        d = np.minimum(d, 2 * 6371 * np.arcsin(np.sqrt(h)))
    return np.maximum(1, np.round(d * cfg.road_factor / cfg.speed_kmh[mobility or "motorbike"] * 60))


def busy_mask(region, day_types, cfg) -> np.ndarray:
    """Places Google's popular times call busy (>= crowd_busy_pct) at some time of the given day types; a place without
    popular times is never busy (unknown, not quiet and not crowded)."""
    p = region.places
    busy = np.zeros(len(region.ids), dtype=bool)
    for dt in day_types:
        for b in DAYTIME:
            busy |= (p[f"crowd_{dt}_{b}"].fill_null(0).to_numpy() >= cfg.crowd_busy_pct)
    return p["has_crowd"].to_numpy() & busy


def fit_table(region, si, days, ctrs, anchor_areas: set, profile, cfg) -> list[float]:
    """decision.fit.fit's number for every place: distance + area + crowd + details, clipped, rounded."""
    p = region.places
    n = len(region.ids)
    lat = p["lat"].to_numpy()
    lng = p["lng"].to_numpy()
    has_pt = ~np.isnan(lat) & ~np.isnan(lng)
    dist = np.zeros(n)
    if has_pt.any():
        d = np.full(n, np.inf)
        la1, lo1 = np.radians(lat), np.radians(lng)
        for _, (qlat, qlng) in ctrs:  # decision.geo.km, same operation order
            la2, lo2 = np.radians(qlat), np.radians(qlng)
            h = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
            d = np.minimum(d, 2 * 6371 * np.arcsin(np.sqrt(h)))
        r = radius(si, profile, cfg)
        dist = np.where(has_pt, 1 - np.minimum(1.0, d / r), 0.0)
    area = np.array([cfg.area_bonus if a in anchor_areas else 0.0 for a in p["area"].to_list()])
    crowd = np.zeros(n)
    if (profile.crowd_tolerance or si.pace.crowd_tolerance) == "avoid":
        known = sorted({d.day_type for d in days if d.day_type})
        if known:
            crowd = np.where(busy_mask(region, known, cfg), -cfg.crowd_penalty, 0.0)
    details = np.zeros(n)
    cf = cfg.details_fit
    for who in trip_companions(si, cfg):
        val, st = region.verdict(who)
        firm = np.array([s in FIRM for s in st], dtype=bool)
        good = np.array([v == "good" for v in val], dtype=bool) & firm
        bad = np.array([v == "bad" for v in val], dtype=bool) & firm
        details = details + np.where(good, cf["good_bonus"], 0.0)
        details = details - np.where(bad, cf["bad_penalty"], 0.0)
        for fid, want in NEEDS.get(who, ()):
            col = region.feature(fid)
            details = details + np.where(col.exists & col.firm & col.eq(want), cf["feature_bonus"], 0.0)
    total = np.maximum(0.0, np.minimum(1.0, dist + area + crowd + details))
    return _round(total)


def score_table(region, si, profile, cfg, fit: list, live: np.ndarray, role: list, act: list,
                extra_voices: int = 0, overrides: dict | None = None, group: list | None = None,
                wishes=()) -> tuple[list[float], list[int]]:
    """decision.rank.score's number for every place, `pop` ranked among the live places (+ extra_voices zeros for
    kept places without a record). overrides: the session's activities (only the slow path needs them)."""
    group = group if group is not None else display_groups(region, role, cfg)
    p = region.places
    n = len(region.ids)
    voices_all = p["voices"].to_numpy().astype(np.int64)
    live_voices = sorted(voices_all[live].tolist() + [0] * extra_voices)
    top = max(1, len(live_voices) - 1)
    pop = np.minimum(1.0, np.searchsorted(np.array(live_voices), voices_all, side="left") / top)
    ws = wants(si, profile)
    pref, unc = _preference(region, ws, role, act, n, overrides or {})
    visited = set(si.novelty.visited) | set(profile.visited)
    nov_v = {"new": -1.0, "familiar": 0.3}.get(si.novelty.level, 0.0)
    nov = np.array([nov_v if pid in visited else 0.0 for pid in region.ids])
    exp_kind = si.context.experience
    exp = pop if exp_kind == "first" else (1 - pop if exp_kind == "returning" else np.zeros(n))
    mid = p["price_mid_vnd"].fill_null(0.0).to_numpy()
    norm = np.where(p["price_mid_vnd"].is_null().to_numpy(), 0.0, np.minimum(1.0, mid / cfg.price_ref_vnd))
    parts = {"ctx": np.array(fit, dtype=np.float64),
             "pref": np.array(_round(pref)),
             "nov": nov,
             "exp": exp,
             "pop": np.array(_round(pop)),
             "unc": -np.array(_round(unc)),
             "price": -np.array(_round(profile.price_sensitivity * norm)),
             "wish": np.array(_round(_wish(region, wishes, role, group)))}
    # rank.score: sum(cfg.weights.get(k, 0.0) * v for k, v in parts.items()); Python 3.12's float sum is compensated
    return _round(_py_sum([cfg.weights.get(k, 0.0) * v for k, v in parts.items()], n)), live_voices


def _py_sum(terms: list, n: int) -> np.ndarray:
    """builtin sum() over float terms, vectorised: CPython 3.12 adds with Neumaier compensation (bltinmodule.c)."""
    acc, comp = np.zeros(n), np.zeros(n)
    for x in terms:
        t = acc + x
        comp = comp + np.where(np.abs(acc) >= np.abs(x), (acc - t) + x, (x - t) + acc)
        acc = t
    return np.where((comp != 0) & np.isfinite(comp), acc + comp, acc)


def _wish(region, wishes, role: list, group: list) -> np.ndarray:
    """decision.wishes.lift for every place: 1 − Π(1 − a·strength), multiplied in the order lift multiplies."""
    n = len(region.ids)
    keep = np.ones(n)
    if not wishes:
        return np.zeros(n)
    role_a = np.array([r or "" for r in role], dtype=object)
    group_a = np.array(group, dtype=object)
    for w in wishes:
        s = np.zeros(n)
        if w.places is not None:
            for pid, v in w.places.items():
                if (i := region.index.get(pid)) is not None:
                    s[i] = v
        else:
            s[group_a == w.group] = 1.0
        if w.role is not None:
            s[role_a != w.role] = 0.0
        keep = keep * (1 - w.a * s)
    return 1 - keep


def firm_ids(region):
    """wishes.build's firm(feature, value): the places whose served value is that, VERIFIED or OUTDATED."""
    def firm(fid: str, value: str) -> set[str]:
        col = region.feature(fid)
        return {pid for pid, v, ok in zip(region.ids, col.value, col.firm) if ok and v == value}
    return firm


def _preference(region, ws, role, act, n, overrides: dict) -> tuple[np.ndarray, np.ndarray]:
    """rank.preference for every place: (fit / total, missing / total), 0 when no want applies."""
    if any(w[0] in SOFT_SPECIAL for w in ws):
        return _preference_slow(region, ws, role, n, overrides)
    total = np.zeros(n)
    fit = np.zeros(n)
    missing = np.zeros(n)
    for fid, val, ctx, w, scope in ws:
        app = _applies({"feature": fid, "scope": scope}, act)
        col = region.feature(fid)
        cur = list(col.value)
        for k, v in reversed(list((ctx or {}).items())):  # first context key with data wins (rank._contextual)
            top = region.ctx_top(fid, f"{k}={v}")
            cur = [t if t is not None else c for t, c in zip(top, cur)]
        hit = np.array([c == val for c in cur], dtype=bool) & col.exists
        total = total + np.where(app, abs(w), 0)
        if w > 0:
            missing = missing + np.where(app & (~col.exists | col.uncertain), w, 0)
        fit = fit + np.where(app & hit, w * col.conf, 0.0)
    safe = np.where(total > 0, total, 1)
    return np.where(total > 0, fit / safe, 0.0), np.where(total > 0, missing / safe, 0.0)


def _preference_slow(region, ws, role, n, overrides: dict):
    """A want rank.preference treats specially (wine_tasting_available): the per-place rule on every place."""
    from .rank import preference
    pref, unc = np.zeros(n), np.zeros(n)
    for i, pid in enumerate(region.ids):
        if role[i] is None:
            continue
        pref[i], unc[i], _ = preference(region.record(pid), ws, overrides.get(pid), role[i])
    return pref, unc


@dataclass
class Table:
    role: list
    act: list
    status: list
    fails: dict
    fit: list
    score: list
    live: np.ndarray
    members: np.ndarray
    voices: list
    group: list
    anchor_areas: set
    key: str = ""  # everything the numbers above were computed from (a Cand built from them is valid while it is the same)
    wishes: tuple = ()  # decision.wishes.build of the Search Input the score tier read


def display_groups(region, role: list, cfg) -> list[str]:
    """diversify.display_group for every place (first display group that lists the category group)."""
    of: dict[str, str] = {}
    for k, gs in cfg.display_groups.items():
        for g in gs:
            of.setdefault(g, k)
    return ["meal" if r == "meal" else of.get(g, "sights") for r, g in zip(role, region.column("category_group"))]


def tabs(region, cfg) -> list[str]:
    """The Lựa chọn tab of every place: the first tab that lists its category group (config tabs), else sights."""
    of: dict[str, str] = {}
    for k, gs in cfg.tabs.items():
        for g in gs:
            of.setdefault(g, k)
    return [of.get(g, "sights") for g in region.column("category_group")]


def _key(*parts) -> str:
    return json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False)


def _cached(memo, tier: str, key: str, fn):
    """memo: tier -> (key, value) of the last call; a tier is recomputed only when its input key changed."""
    if memo is None:
        return fn()
    hit = memo.get(tier)
    if hit and hit[0] == key:
        return hit[1]
    val = fn()
    memo[tier] = (key, val)
    return val


def table(region, si, profile, days, relaxed, ctrs, anchors: list, keep: set, n_missing: int, cfg,
          memo: dict | None = None) -> Table:
    """Role, screen, fit and score of every place of the region; the numbers pipeline.run reads. memo: per session,
    three tiers keyed by exactly the inputs each one reads (docs/superpowers/specs/2026-10-13-corpus-snapshot-design.md
    §6.2): screen (hard filters, days, relaxed, activities), fit (+ context, pace, anchors, profile), score (+ soft
    weights, Trip wishes, liked groups, novelty, vibes, live set)."""
    index = region.index
    base_role = region.column("role")
    roleless = sorted(pid for pid in keep if pid in index and base_role[index[pid]] is None)  # kept, no plan role
    day_sig = [(d.weekday, d.day_type, d.start, d.end) for d in days]
    hard_sig = si.model_dump(mode="json", include={"hard_filters", "activities"})
    ks = _key(hard_sig, day_sig, sorted(relaxed), roleless)

    def screen_tier():
        role, act = roles(region, si.activities, keep)
        scr = screen_table(region, si, days, relaxed, role, act)
        stay = region.places["is_stay"].to_numpy()
        members = np.array([r is not None for r in role], dtype=bool) & ~stay  # lodging is never a candidate
        return role, act, scr, members, np.array(scr.status), display_groups(region, role, cfg)

    role, act, scr, members, status, group = _cached(memo, "screen", ks, screen_tier)
    keep_mask = np.array([pid in keep for pid in region.ids], dtype=bool)
    live = members & ((status != "excluded") | keep_mask)
    area_of = region.column("area")
    anchor_areas = {a for pid in anchors if pid in index and (a := area_of[index[pid]])}
    kf = _key(si.model_dump(mode="json", include={"context", "pace", "hard_filters"}), day_sig, ctrs,
              sorted(anchor_areas), profile.model_dump(mode="json", include={"travel_mult", "crowd_tolerance"}))
    fit_all = _cached(memo, "fit", kf, lambda: fit_table(region, si, days, ctrs, anchor_areas, profile, cfg))
    fit = np.where(live, np.array(fit_all, dtype=np.float64), 0.0).tolist()
    kw = _key(si.model_dump(mode="json", include={"wishes", "vibes", "liked_groups"}), si.context.purpose)
    names, index = region.column("name"), region.index
    wl = _cached(memo, "wishes", kw, lambda: build_wishes(
        si, region.light, cfg, region.sigs, firm_ids(region), lambda pid: names[index[pid]] if pid in index else None))
    kc = _key(kf, ks, hashlib.md5(live.tobytes()).hexdigest(), n_missing, profile.model_dump(mode="json"),
              si.model_dump(mode="json", include={"soft_weights", "novelty", "vibes", "context", "wishes",
                                                  "liked_groups"}))
    score, voices = _cached(memo, "score", kc, lambda: score_table(region, si, profile, cfg, fit, live, role, act,
                                                                    n_missing, si.activities, group=group, wishes=wl))
    return Table(role, act, scr.status, scr.fails, fit, score, live, members, voices, group, anchor_areas, kc, wl)
