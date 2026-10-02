"""Planning sessions for the web (docs/specs/PLANNING_SPEC.md §API và web): create (fast, anchor = base), act (chips,
no model), variants, lodging (crawled in the background), confirm. One lock per session; each committing act is one
version that undo / redo moves between.
"""

import threading
import urllib.error
import urllib.request
from dataclasses import replace
from functools import cache
from json import dumps, loads

import live

from . import places as pl
from .build import ENTRY, EXIT, HOME, prepare, schedule_trip, with_home
from .lodging import candidates as lodging_candidates
from .lodging import progress_event
from .objectives import LABEL, add_lodging_cost, choose, metrics, score
from .repair import RepairError, repair_day
from .robustness import robustness as robustness_of
from .backup import backups as backups_of
from .scope import LODGING_FETCH, LODGING_HOME, NONE, RELAYOUT, VARIANT, act_scope
from .session import ActCtx, ActionError, Session, State, Store
from .session import apply_act as _apply
from .settings import Settings
from .settings import load as load_settings


def _http_post(url: str) -> str:
    req = urllib.request.Request(url, method="POST", data=b"{}", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8")


class NoSession(Exception):
    pass


class NotConfirmable(Exception):
    pass


def _nights(ctx: dict) -> int:
    return max((ctx.get("days") or 1) - 1, 0)


class _Base:
    """What create() computes once (no lodging yet) and the lodging crawl later fills in -- held in RAM, keyed by
    session id. Never persisted: a restart rebuilds it from Session.decision + State (Task 6)."""

    def __init__(self, trip, variants: list[dict], comparison: list[dict], ok: bool, warnings: list,
                back_to_decision: dict | None):
        self.trip = trip
        self.variants = variants          # objective -> variant dict, home = @home/@entry (no lodging)
        self.comparison = comparison
        self.ok = ok
        self.warnings = warnings
        self.back_to_decision = back_to_decision
        self.lodging_status = "pending"   # pending | ready | unavailable
        self.lodging_candidates: list[dict] = []


class Engine:
    def __init__(self, records: list[dict], cfg: Settings | None = None, live_cfg=None, store: Store | None = None,
                geocode_fn=None, matrix_fn=None, sun_fn=None, lodging_fn=None, route_fn=None,
                decision_url: str | None = None, http_post=None, background: bool = True):
        self.by_id = {r["id"]: r for r in records}
        self.records = records
        self.cfg = cfg or load_settings()
        self.live_cfg = live_cfg or live.load_settings()
        self.store = store or Store(None)
        self.geocode_fn = geocode_fn
        self.matrix_fn = matrix_fn
        self.sun_fn = sun_fn
        self.lodging_fn = lodging_fn or live.lodging_near
        self.route_fn = route_fn or live.route_shape
        self.decision_url = decision_url or self.cfg.decision_url
        self.http_post = http_post or _http_post
        self.background = background
        self._base: dict[str, _Base] = {}
        self._schedules: dict[str, list] = {}

    # ---------- resolving a Decision Output ----------

    def _resolve(self, decision: dict | None, decision_session_id: str | None) -> dict:
        if decision is not None:
            return decision
        if not decision_session_id:
            raise ActionError("need decision_output or decision_session_id")
        url = f"{self.decision_url}/api/decision/sessions/{decision_session_id}/confirm"
        try:
            body = self.http_post(url)
        except OSError as e:
            raise ActionError(f"could not reach the decision session: {e}") from None
        return loads(body)

    # ---------- Trip / variants (no lodging) ----------

    def _prepare(self, decision: dict, extra_nodes: dict | None = None):
        return prepare(decision, self.records, self.cfg, self.live_cfg, self.geocode_fn, self.matrix_fn, self.sun_fn,
                       extra_nodes=extra_nodes)

    def _build_base(self, decision: dict) -> _Base:
        trip = self._prepare(decision)
        objectives = choose(decision["trip_context"], [cx.rain for cx in trip.ctxs], trip.ctxs[0].prefs, self.cfg)
        variants, seen = [], set()
        for obj in objectives:
            s = schedule_trip(trip, self.cfg.objective_weights[obj])
            if s.violations:
                continue
            orders = tuple(r.order for r in s.results)
            if orders in seen:
                continue
            seen.add(orders)
            m = metrics(s.ctxs, s.results)
            days = [cx.day for cx in s.ctxs]
            from .build import itinerary as render_itinerary
            from .build import travel_load as render_travel_load
            variants.append({"id": f"v{len(variants) + 1}", "objective": obj, "label": LABEL[obj],
                             "score": list(score(obj, m)), "metrics": m,
                             "itinerary": render_itinerary(days, s.results), "travel_load": render_travel_load(days, s.results),
                             "robustness": robustness_of(s.ctxs, s.results, trip.travel.source),
                             "backups": backups_of(s.ctxs, s.results, decision, trip.by_id), "warnings": s.warnings,
                             "lodging": {"id": None, "name": None, "price_vnd": None},
                             "_results": s.results, "_home": trip.days[0].start_node if trip.days else None})
        ok = bool(variants)
        back = None
        if not ok:
            back = {"reason": "no_valid_variant", "places": sorted({v.place_id for v in
                    schedule_trip(trip, self.cfg.objective_weights[objectives[0]]).violations if v.place_id})}
        return _Base(trip, variants, [], ok, list(trip.warnings), back)

    def _crawl_lodging(self, sid: str) -> None:
        """Runs on a background thread (create()'s background=True) or synchronously (background=False, tests).
        Any failure here -- not just live.Unavailable -- degrades to "unavailable" rather than leaving the session
        stuck at "pending" forever: a background thread that dies silently is worse than a lodging block the user
        is told did not come through."""
        base = self._base[sid]
        decision = self.store.get(sid).decision
        try:
            cands = lodging_candidates(base.trip.by_place, decision, self.cfg, self.lodging_fn, self.live_cfg)
        except Exception:
            cands = []
        if cands:
            # base.trip's matrix was built at create() with no lodging nodes (fast path, anchor = base); a found
            # candidate must join that matrix before with_home() can route a day to/from it.
            base.trip = self._prepare(decision, extra_nodes={c["id"]: (c["lat"], c["lng"]) for c in cands})
        base.lodging_candidates = cands
        base.lodging_status = "ready" if cands else "unavailable"

    # ---------- API ----------

    def create(self, decision: dict | None = None, decision_session_id: str | None = None) -> dict:
        decision = self._resolve(decision, decision_session_id)
        s = self.store.new(decision, decision_session_id)
        base = self._build_base(decision)
        self._base[s.id] = base
        self.store.save(s)
        if self.background:
            threading.Thread(target=self._crawl_lodging, args=(s.id,), daemon=True).start()
        else:
            self._crawl_lodging(s.id)
        return {"id": s.id, "view": self._view(s)}

    def _get(self, sid: str) -> Session:
        try:
            return self.store.get(sid)
        except KeyError:
            raise NoSession(sid) from None

    def _active_itinerary(self, s: Session, base: _Base) -> tuple[list, list] | None:
        """The itinerary / travel_load of the session's currently chosen variant, with every committed act applied
        -- None before a variant is chosen, since there is nothing laid out yet to show."""
        if s.state.chosen_variant is None:
            return None
        results = self._schedules.get(s.id, [None] * len(s.states))[s.position]
        if results is None:
            results = next(v["_results"] for v in base.variants if v["id"] == s.state.chosen_variant)
        by_place = self._places_for(s, base)
        home = self._home_for(s, base)
        _, ctxs = self._ctxs_for(base.trip, by_place, home, s.state)
        days = [cx.day for cx in ctxs]
        from .build import itinerary as render_itinerary
        from .build import travel_load as render_travel_load
        return render_itinerary(days, results), render_travel_load(days, results)

    def _view(self, s: Session) -> dict:
        base = self._base[s.id]
        active = self._active_itinerary(s, base)
        return {"ok": base.ok, "variants": [{k: v for k, v in v.items() if not k.startswith("_")} for v in base.variants],
               "comparison": base.comparison, "warnings": base.warnings, "back_to_decision": base.back_to_decision,
               "lodging": {"status": base.lodging_status,
                           "candidates": [{"id": c["id"], "name": c["name"], "price_vnd": c["price_vnd"]}
                                         for c in base.lodging_candidates]},
               "itinerary": active[0] if active else None, "travel_load": active[1] if active else None,
               "state": s.state.model_dump(mode="json")}

    def load(self, sid: str) -> dict:
        s = self._get(sid)
        with self.store.lock(sid):
            return {"id": s.id, "view": self._view(s)}

    def variants(self, sid: str) -> list[dict]:
        self._get(sid)
        return self._view(self._get(sid))["variants"]

    def lodging(self, sid: str) -> dict:
        self._get(sid)
        return self._view(self._get(sid))["lodging"]

    # ---------- act / undo / redo ----------

    def _active_place(self, s: Session, base: _Base, pid: str):
        """base.trip.by_place with this session's relax acts (session.State.relaxed) layered on top, so validate()
        and repair_day see a place whose relaxed hard filters include both what Place Decision already relaxed
        (Place.relaxed, baked into the Decision Output) and what the user relaxed here, at the Planning layer."""
        relax_for = {r.feature for r in s.state.relaxed if r.place_id == pid}
        p = base.trip.by_place.get(pid)
        return replace(p, relaxed=p.relaxed + tuple(relax_for)) if p and relax_for else p

    def _places_for(self, s: Session, base: _Base) -> dict:
        return {pid: self._active_place(s, base, pid) for pid in base.trip.by_place}

    def _home_for(self, s: Session, base: _Base) -> str | None:
        state = s.state
        if not state.lodging_touched:
            return base.variants[0]["_home"] if base.variants else None
        if state.lodging_point:
            return state.lodging_point["id"]
        return state.lodging_id

    def _ctxs_for(self, trip, by_place: dict, home: str | None, state: State):
        t2 = trip if home in (None, trip.days[0].start_node if trip.days else None) else with_home(trip, home)
        ctxs = list(t2.ctxs)                 # a fresh list: never mutate t2.ctxs (shared with base.trip) in place
        if state.pace_override and state.pace_override != t2.pace:
            ctxs = [replace(cx, pace=state.pace_override) for cx in ctxs]
        for day, (lo, hi) in state.day_window_override.items():
            if 0 <= day < len(ctxs):
                ctxs[day] = replace(ctxs[day], day=replace(ctxs[day].day, start=lo, end=hi))
        ctxs = [replace(cx, places=by_place) for cx in ctxs]
        return t2, ctxs

    def _members(self, base: _Base, s: Session, prev_results: list) -> list:
        """The current membership of every day: the previous Schedule's membership, with State.assignment /
        dropped layered on top (what a RELAYOUT act is about to turn into reality)."""
        per_day = [list(r.order) for r in prev_results]
        for pid, day in s.state.assignment.items():
            per_day = [[i for i in ids if i != pid] for ids in per_day]
            if 0 <= day < len(per_day):
                per_day[day].append(pid)
        dropped = {d.place_id for d in s.state.dropped}
        return [[i for i in ids if i not in dropped] for ids in per_day]

    def _relayout(self, base: _Base, s: Session, prev_results: list, touched_days: set) -> list:
        by_place = self._places_for(s, base)
        home = self._home_for(s, base)
        trip, ctxs = self._ctxs_for(base.trip, by_place, home, s.state)
        members = self._members(base, s, prev_results)
        locked = set(s.state.locked)
        results = list(prev_results)
        for day in range(len(ctxs)):
            same_members = day < len(prev_results) and sorted(members[day]) == sorted(prev_results[day].order)
            if same_members and day not in touched_days:
                continue
            prev_order = prev_results[day].order if day < len(prev_results) else None
            if day in s.state.order_override:
                from .schedule import simulate
                results[day] = simulate(s.state.order_override[day], ctxs[day])
            else:
                results[day] = repair_day(members[day], ctxs[day], prev_order, locked, self.cfg)
        return results, ctxs

    def _rebuild_variant(self, base: _Base, s: Session) -> tuple:
        """VARIANT scope: a trip-wide parameter changed, the chosen objective's whole day split reruns from
        scratch (schedule_trip), same as building a fresh variant -- this is the one path allowed to reshuffle a
        day the act did not literally touch, because the parameter it changed (pace / objective / a day window)
        legitimately affects every day."""
        obj = s.state.objective_override or next(v["objective"] for v in base.variants if v["id"] == s.state.chosen_variant)
        by_place = self._places_for(s, base)
        home = self._home_for(s, base)
        trip = replace(base.trip, by_place=by_place)
        t2 = trip if home in (None, trip.days[0].start_node if trip.days else None) else with_home(trip, home)
        weights = dict(self.cfg.objective_weights[obj])
        sched = schedule_trip(t2, weights)
        return sched.results, sched.ctxs

    def _variant_dict(self, base: _Base, s: Session, results: list, ctxs: list) -> dict:
        obj = s.state.objective_override or next(v["objective"] for v in base.variants if v["id"] == s.state.chosen_variant)
        m = metrics(ctxs, results)
        cand = next((c for c in base.lodging_candidates if c["id"] == self._home_for(s, base)), None)
        if cand:
            m = add_lodging_cost(m, cand["price_vnd"], _nights(s.decision["trip_context"]["context"]))
        from .build import itinerary as render_itinerary
        from .build import travel_load as render_travel_load
        days = [cx.day for cx in ctxs]
        return {"id": s.state.chosen_variant, "objective": obj, "label": LABEL[obj], "score": list(score(obj, m)),
               "metrics": m, "itinerary": render_itinerary(days, results), "travel_load": render_travel_load(days, results),
               "robustness": robustness_of(ctxs, results, base.trip.travel.source),
               "backups": backups_of(ctxs, results, s.decision, base.trip.by_id), "warnings": [],
               "lodging": {"id": cand["id"], "name": cand["name"], "price_vnd": cand["price_vnd"]} if cand
               else {"id": None, "name": None, "price_vnd": None}, "_results": results, "_home": self._home_for(s, base)}

    def act(self, sid: str, action: dict) -> dict:
        s = self._get(sid)
        base = self._base[sid]
        with self.store.lock(sid):
            t = action.get("type")
            if t == "undo":
                if s.position == 0:
                    raise ActionError("nothing to undo")
                s.position -= 1
            elif t == "redo":
                if s.position + 1 >= len(s.states):
                    raise ActionError("nothing to redo")
                s.position += 1
            else:
                if s.state.chosen_variant is None and t != "pick_variant":
                    raise ActionError("pick a variant before editing the plan")
                prev_results = self._schedules.get(sid, [None])[s.position] or \
                    next(v["_results"] for v in base.variants if v["id"] == s.state.chosen_variant) \
                    if s.state.chosen_variant else []
                ctx = ActCtx(by_place=base.trip.by_place, n_days=len(base.trip.days),
                            variant_ids={v["id"] for v in base.variants},
                            backup_ids={b["id"]: b for b in s.decision.get("backup_pool") or []},
                            day_members=[list(r.order) for r in prev_results] if prev_results else
                            ([] if not base.variants else []),
                            objective_names=set(LABEL), valid_paces=set(self.cfg.per_day))
                if t == "pick_lodging":
                    if action.get("id") not in {c["id"] for c in base.lodging_candidates}:
                        raise ActionError(f"unknown or no-longer-offered lodging {action.get('id')!r}")
                elif t == "set_lodging":
                    text = (action.get("text") or "").strip()
                    if not text:
                        raise ActionError("set_lodging needs non-empty text")
                    try:
                        hit = self.geocode_fn(text) if self.geocode_fn else live.geocode(text, self.live_cfg)
                    except live.Unavailable:
                        hit = None
                    point = {"id": f"manual:{text}", "lat": hit["lat"], "lng": hit["lng"], "text": text,
                            "source": hit["source"], "fetched_at": hit.get("fetched_at")} if hit else None
                    if point:
                        # join the manual point to the matrix before with_home() needs to route a day to/from it
                        base.trip = self._prepare(decision=s.decision, extra_nodes={
                            **{c["id"]: (c["lat"], c["lng"]) for c in base.lodging_candidates},
                            point["id"]: (point["lat"], point["lng"])})
                    action = {**action, "_point": point}
                elif t == "relax" and action.get("scope") == "whole_trip" and "place_ids" not in action:
                    feature = action.get("feature")
                    affected = [pid for pid, p in base.trip.by_place.items()
                               if feature not in p.relaxed and self._has_hard_violation(base, s, pid, feature, prev_results)]
                    action = {**action, "place_ids": affected}
                new_state = _apply(s.state, action, ctx)
                scope = act_scope(action)
                if scope == NONE:
                    results, ctxs = prev_results, None
                elif scope == RELAYOUT:
                    touched = self._touched_days(s.state, new_state, prev_results)
                    s2 = s.model_copy(update={"states": s.states[: s.position + 1] + [new_state], "position": s.position + 1})
                    results, ctxs = self._relayout(base, s2, prev_results, touched)
                elif scope == VARIANT:
                    s2 = s.model_copy(update={"states": s.states[: s.position + 1] + [new_state], "position": s.position + 1})
                    results, ctxs = self._rebuild_variant(base, s2)
                elif scope == LODGING_HOME:
                    s2 = s.model_copy(update={"states": s.states[: s.position + 1] + [new_state], "position": s.position + 1})
                    results, ctxs = self._relayout(base, s2, prev_results, set(range(len(base.trip.days))))
                else:  # LODGING_FETCH
                    s2 = s.model_copy(update={"states": s.states[: s.position + 1] + [new_state], "position": s.position + 1})
                    base.lodging_candidates = self._refetch_lodging(base, s2)
                    results, ctxs = self._relayout(base, s2, prev_results, set())
                s.states = s.states[: s.position + 1] + [new_state]
                s.position += 1
            self._schedules.setdefault(sid, [None] * len(s.states))
            while len(self._schedules[sid]) < len(s.states):
                self._schedules[sid].append(None)
            self._schedules[sid] = self._schedules[sid][: len(s.states)]
            if t not in ("undo", "redo"):
                self._schedules[sid][s.position] = results if t != "pick_variant" else \
                    next(v["_results"] for v in base.variants if v["id"] == s.state.chosen_variant)
            s.log.append({"version": s.position, "action": action})
            self.store.save(s)
            return {"view": self._view(s), "diff": {"scope": act_scope(action) if t not in ("undo", "redo") else "none"}}

    def _touched_days(self, old: State, new: State, prev_results: list) -> set:
        days = set()
        for pid, day in new.assignment.items():
            if old.assignment.get(pid) != day:
                days.add(day)
                prev_day = next((i for i, r in enumerate(prev_results) if pid in r.order), None)
                if prev_day is not None:
                    days.add(prev_day)
        if set(d.place_id for d in new.dropped) != set(d.place_id for d in old.dropped):
            for pid in {d.place_id for d in new.dropped} - {d.place_id for d in old.dropped}:
                prev_day = next((i for i, r in enumerate(prev_results) if pid in r.order), None)
                if prev_day is not None:
                    days.add(prev_day)
        days |= set(new.order_override) - set(old.order_override)
        days |= {d for d, o in new.order_override.items() if old.order_override.get(d) != o}
        return days

    def _has_hard_violation(self, base, s, pid, feature, prev_results) -> bool:
        from corpus.serving import check
        p = base.trip.by_place.get(pid)
        return bool(p) and check(p.rec, feature, "present") == "fail"

    def _refetch_lodging(self, base: _Base, s: Session) -> list:
        decision = dict(s.decision)
        tc = dict(decision["trip_context"])
        tc["context"] = {**tc["context"], "budget_vnd": tc["context"].get("budget_vnd")}
        decision["trip_context"] = tc
        try:
            cands = lodging_candidates(base.trip.by_place, decision, self.cfg, self.lodging_fn, self.live_cfg)
        except live.Unavailable:
            cands = base.lodging_candidates
        cap = s.state.budget_override
        return [c for c in cands if cap is None or c["price_vnd"] is None or c["price_vnd"] <= cap]

    # ---------- confirm ----------

    def confirm(self, sid: str) -> dict:
        s = self._get(sid)
        base = self._base[sid]
        with self.store.lock(sid):
            if s.state.chosen_variant is None:
                raise NotConfirmable("no variant chosen")
            results = self._schedules.get(sid, [None] * len(s.states))[s.position]
            if results is None:
                results = next(v["_results"] for v in base.variants if v["id"] == s.state.chosen_variant)
            by_place = self._places_for(s, base)
            home = self._home_for(s, base)
            trip, ctxs = self._ctxs_for(base.trip, by_place, home, s.state)
            from .validate import validate
            tc = s.decision["trip_context"]
            anchors = {c["id"] for c in s.decision["confirmed"] if c.get("role") == "anchor"}
            violations = validate(ctxs, results, tc.get("hard_filters") or [], anchors, tc["context"].get("budget_vnd"),
                                  (tc.get("pace") or {}).get("max_leg_min"))
            if violations:
                raise NotConfirmable("plan has unresolved violations")
            variant = self._variant_dict(base, s, results, ctxs)
            coords = {**{p.id: (p.lat, p.lng) for p in trip.by_place.values()},
                     **{n: (pt.lat, pt.lng) for n, pt in trip.points.items() if pt},
                     **{c["id"]: (c["lat"], c["lng"]) for c in base.lodging_candidates}}
            from .output import build as build_output
            out = build_output(trip, base.variants, variant, results, s.decision, coords, self.live_cfg,
                               route_fn=self.route_fn)
            s.output = out
            self.store.save(s)
            return out
