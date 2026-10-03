"""Planning sessions for the web (docs/specs/PLANNING_SPEC.md §API và web): create (fast, anchor = base), act (chips,
no model), variants, lodging (crawled in the background), confirm. One lock per session; each committing act is one
version that undo / redo moves between.
"""

import asyncio
import threading
import traceback
import urllib.error
import urllib.request
from dataclasses import replace
from json import loads
from typing import Awaitable, Callable

import live

from .build import prepare, schedule_trip, with_home
from .lodging import candidates as lodging_candidates
from .objectives import LABEL, add_lodging_cost, choose, metrics, score
from .repair import repair_day
from .robustness import robustness as robustness_of
from .backup import backups as backups_of
from .agent import AgentError
from .guard import TurnPlan, guard
from .policy import DONE, NONE as NO_PLAN_SAY, policy
from .scope import LODGING_FETCH, LODGING_HOME, NONE, RELAYOUT, VARIANT, act_scope, widest
from .session import ActCtx, ActionError, Session, State, Store
from .session import apply_act as _apply
from .settings import Settings
from .settings import load as load_settings


def _http_post(url: str) -> str:
    req = urllib.request.Request(url, method="POST", data=b"{}", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8")


Agent = Callable[[dict, Callable[[str], None]], Awaitable[TurnPlan]]


class NoSession(Exception):
    pass


class NotConfirmable(Exception):
    pass


def _nights(ctx: dict) -> int:
    return max((ctx.get("days") or 1) - 1, 0)


class _Base:
    """What create() computes once (no lodging yet) and the lodging crawl later fills in -- held in RAM, keyed by
    session id. Never persisted: a restart rebuilds it from Session.decision + states + log (Engine._ensure_base)."""

    def __init__(self, trip, variants: list[dict], comparison: list[dict], ok: bool, warnings: list,
                back_to_decision: dict | None):
        self.trip = trip
        self.variants = variants          # objective -> variant dict, home = @home/@entry (no lodging)
        self.comparison = comparison
        self.ok = ok
        self.warnings = warnings
        self.back_to_decision = back_to_decision
        self.lodging_status = "pending"   # pending | ready | unavailable
        self.lodging_candidates: list[dict] = []   # every candidate ever crawled, never filtered in place


class Engine:
    def __init__(self, records: list[dict], cfg: Settings | None = None, live_cfg=None, store: Store | None = None,
                geocode_fn=None, matrix_fn=None, sun_fn=None, lodging_fn=None, route_fn=None,
                decision_url: str | None = None, http_post=None, background: bool = True,
                agent: "Agent | None" = None):
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
        self.agent = agent
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
        """Runs on a background thread (create()'s background=True) or synchronously (background=False, tests, and
        _ensure_base's lazy rebuild). Any failure here -- not just live.Unavailable -- degrades to "unavailable"
        rather than leaving the session stuck at "pending" forever. The write-back happens under the session's own
        lock and merges in whatever lodging point the user may have set manually while the crawl (a real network
        call, done outside the lock) was still running, so a concurrent set_lodging is never lost."""
        base = self._base[sid]
        decision = self.store.get(sid).decision
        try:
            cands = lodging_candidates(base.trip.by_place, decision, self.cfg, self.lodging_fn, self.live_cfg)
        except Exception:
            cands = []
        with self.store.lock(sid):
            base.lodging_candidates = cands
            extra = {c["id"]: (c["lat"], c["lng"]) for c in cands}
            point = self.store.get(sid).state.lodging_point
            if point:
                extra[point["id"]] = (point["lat"], point["lng"])
            if extra:
                base.trip = self._prepare(decision, extra_nodes=extra)
            base.lodging_status = "ready" if cands else "unavailable"

    def _ensure_base(self, sid: str) -> _Base:
        """Lazily rebuilds the in-RAM Trip / variants / schedule cache for a session the Store already knows about
        but this Engine instance has never touched (a fresh Engine after a process restart, or a session created
        by another Engine sharing the same disk Store). Only Session (decision + states + log) is ever persisted;
        everything here is cheap to re-derive -- live.cache and the lodging crawl's own TTL already make repeat
        network calls fast -- rather than serialized (Trip/DayCtx hold Settings/Place objects, not a natural fit
        for JSON, and re-deriving avoids a second source of truth to keep in sync)."""
        if sid in self._base:
            return self._base[sid]
        s = self.store.get(sid)
        base = self._build_base(s.decision)
        self._base[sid] = base
        self._crawl_lodging(sid)
        results: list = [None] * len(s.states)
        for k in range(1, len(s.states)):
            old_state = s.states[k - 1]
            prev_results = results[k - 1]
            if prev_results is None:
                prev_results = next((v["_results"] for v in base.variants if v["id"] == old_state.chosen_variant),
                                    []) if old_state.chosen_variant else []
            action = s.log[k - 1]["action"]
            s_view = s.model_copy(update={"states": s.states[: k + 1], "position": k})
            results[k] = self._compute_results(base, s_view, old_state, prev_results, action)
        self._schedules[sid] = results
        return base

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

    def _offered_lodging(self, base: _Base, state: State) -> list[dict]:
        """Every crawled candidate still within the session's current price cap -- state.budget_override narrows
        what is *offered*, it never discards what was actually found (undo must be able to bring a candidate back,
        and the chosen one must stay resolvable even if it falls outside a later-lowered cap)."""
        cap = state.budget_override
        return [c for c in base.lodging_candidates if cap is None or c["price_vnd"] is None or c["price_vnd"] <= cap]

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
        base = self._ensure_base(s.id)
        active = self._active_itinerary(s, base)
        return {"ok": base.ok, "variants": [{k: v for k, v in v.items() if not k.startswith("_")} for v in base.variants],
               "comparison": base.comparison, "warnings": base.warnings, "back_to_decision": base.back_to_decision,
               "lodging": {"status": base.lodging_status,
                           "candidates": [{"id": c["id"], "name": c["name"], "price_vnd": c["price_vnd"]}
                                         for c in self._offered_lodging(base, s.state)]},
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

    # ---------- laying out a schedule (shared by a live act and _ensure_base's replay) ----------

    def _active_place(self, s: Session, base: _Base, pid: str):
        """base.trip.by_place with this session's relax acts (session.State.relaxed) layered on top, so validate()
        and repair_day see a place whose relaxed hard filters include both what Place Decision already relaxed
        (Place.relaxed, baked into the Decision Output) and what the user relaxed here, at the Planning layer."""
        relax_for = {r.feature for r in s.state.relaxed if r.place_id == pid}
        p = base.trip.by_place.get(pid)
        return replace(p, relaxed=p.relaxed + tuple(relax_for)) if p and relax_for else p

    def _places_for(self, s: Session, base: _Base) -> dict:
        dropped = {d.place_id for d in s.state.dropped}
        return {pid: self._active_place(s, base, pid) for pid in base.trip.by_place if pid not in dropped}

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

    def _members(self, s: Session, prev_results: list) -> list:
        """The current membership of every day: the previous Schedule's membership, with State.assignment /
        dropped layered on top (what a RELAYOUT -- or a VARIANT rebuild's repair pass -- is about to turn into
        reality). assignment is the only thing that pins a place to a specific day; it is set by move_place,
        add_from_backup, swap and lock_slot (locking pins the place's current day)."""
        per_day = [list(r.order) for r in prev_results]
        for pid, day in s.state.assignment.items():
            per_day = [[i for i in ids if i != pid] for ids in per_day]
            if 0 <= day < len(per_day):
                per_day[day].append(pid)
        dropped = {d.place_id for d in s.state.dropped}
        return [[i for i in ids if i not in dropped] for ids in per_day]

    def _repair_pass(self, s: Session, ctxs: list, baseline: list, touched_days: set) -> list:
        """Lay every day out from `baseline` (the previous Schedule for a RELAYOUT, or a just-rebuilt automatic
        split for a VARIANT rebuild), applying order_override verbatim and repair_day everywhere else -- a day
        whose membership did not change and was not explicitly touched is left exactly as `baseline` had it.

        repair_day's own locked set is scoped per day to the places assignment actually pins to that day (every
        locked place has an assignment entry: lock_slot sets one). A VARIANT rebuild's `baseline` is schedule_trip's
        own fresh, state-blind clustering, which may put a locked-and-assigned-elsewhere place on this day by
        default -- that is not it "leaving" anything, it is _members() about to relocate it on purpose; passing the
        full locked set here would make repair_day refuse a relocation the act layer already decided was fine."""
        members = self._members(s, baseline)
        results = list(baseline)
        for day in range(len(ctxs)):
            same_members = day < len(baseline) and sorted(members[day]) == sorted(baseline[day].order)
            if same_members and day not in touched_days:
                continue
            prev_order = baseline[day].order if day < len(baseline) else None
            locked_here = {pid for pid in s.state.locked if s.state.assignment.get(pid) == day}
            if day in s.state.order_override:
                from .schedule import simulate
                results[day] = simulate(s.state.order_override[day], ctxs[day])
            else:
                results[day] = repair_day(members[day], ctxs[day], prev_order, locked_here, self.cfg)
        return results

    def _relayout(self, base: _Base, s: Session, prev_results: list, touched_days: set) -> tuple:
        by_place = self._places_for(s, base)
        home = self._home_for(s, base)
        trip, ctxs = self._ctxs_for(base.trip, by_place, home, s.state)
        return self._repair_pass(s, ctxs, prev_results, touched_days), ctxs

    def _rebuild_variant(self, base: _Base, s: Session) -> tuple:
        """VARIANT scope: a trip-wide parameter changed (pace, objective, or a day window), so the chosen
        objective's whole day split reruns from scratch (schedule_trip) against a trip that already excludes
        dropped places and carries the pace / day-window overrides -- this is the one path allowed to reshuffle a
        day the act did not literally touch, because the parameter it changed legitimately affects every day.
        schedule_trip's own automatic layout knows nothing about State.assignment / order_override / locked, so a
        repair pass (the same one a RELAYOUT uses) re-applies them on top, seeded from this fresh layout -- a
        place the user moved or locked lands back on its pinned day regardless of where the automatic clustering
        would have put it, and repair_day still refuses to let a locked place leave its day."""
        obj = s.state.objective_override or next(v["objective"] for v in base.variants if v["id"] == s.state.chosen_variant)
        by_place = self._places_for(s, base)
        home = self._home_for(s, base)
        trip = replace(base.trip, by_place=by_place)
        t2 = trip if home in (None, trip.days[0].start_node if trip.days else None) else with_home(trip, home)
        if s.state.pace_override:
            t2 = replace(t2, pace=s.state.pace_override)
        ctxs = list(t2.ctxs)
        if s.state.pace_override:
            ctxs = [replace(cx, pace=s.state.pace_override) for cx in ctxs]
        for day, (lo, hi) in s.state.day_window_override.items():
            if 0 <= day < len(ctxs):
                ctxs[day] = replace(ctxs[day], day=replace(ctxs[day].day, start=lo, end=hi))
        t2 = replace(t2, ctxs=ctxs)
        weights = dict(self.cfg.objective_weights[obj])
        sched = schedule_trip(t2, weights)
        results = self._repair_pass(s, sched.ctxs, sched.results, set(range(len(sched.ctxs))))
        return results, sched.ctxs

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

    def _has_hard_violation(self, base: _Base, s: Session, pid: str, feature: str) -> bool:
        """Whether pid is currently failing feature as one of the trip's own hard_filters -- used only to resolve
        a whole_trip relax to the places it actually affects, so it must match validate()'s own notion of a hard
        violation (the right op, the filter's own value, not already relaxed), not just "the feature evaluates to
        present somewhere on the record"."""
        from corpus.serving import check
        p = base.trip.by_place.get(pid)
        if not p:
            return False
        hard_filters = s.decision["trip_context"].get("hard_filters") or []
        return any(hf["op"] == "ne" and hf["feature"] == feature and feature not in p.relaxed
                  and check(p.rec, feature, hf["value"]) == "fail" for hf in hard_filters)

    def _ensure_lodging_node(self, base: _Base, decision: dict, point: dict) -> None:
        """set_lodging's manual point must be in the matrix before with_home() can route a day to / from it; a
        no-op once it already is (replay calls this once per logged set_lodging, live calls it once live)."""
        if point["id"] in base.trip.travel.index:
            return
        base.trip = self._prepare(decision, extra_nodes={
            **{c["id"]: (c["lat"], c["lng"]) for c in base.lodging_candidates}, point["id"]: (point["lat"], point["lng"])})

    def _refetch_lodging(self, base: _Base, s: Session) -> None:
        """set_lodging_budget: a higher cap may surface candidates the original crawl's own price filter excluded
        at the source -- re-crawl and merge anything new into the full candidate list (never replace it: a lower
        cap must only narrow what _offered_lodging shows, not discard what was actually found)."""
        decision = dict(s.decision)
        tc = dict(decision["trip_context"])
        tc["context"] = {**tc["context"], "budget_vnd": tc["context"].get("budget_vnd")}
        decision["trip_context"] = tc
        try:
            cands = lodging_candidates(base.trip.by_place, decision, self.cfg, self.lodging_fn, self.live_cfg)
        except Exception:
            cands = []
        seen = {c["id"] for c in base.lodging_candidates}
        new = [c for c in cands if c["id"] not in seen]
        if new:
            base.lodging_candidates = base.lodging_candidates + new
            base.trip = self._prepare(s.decision, extra_nodes={c["id"]: (c["lat"], c["lng"]) for c in base.lodging_candidates})

    def _compute_results(self, base: _Base, s2: Session, old_state: State, prev_results: list, action: dict) -> list:
        """The scope dispatch a committing act lays its results out with -- used both by act() for the newest act
        and by _ensure_base()'s replay for every earlier one, so a rebuilt session lays out identically to how it
        did live. s2: a Session view whose .state is already the state right after `action`. Side effects
        structurally required for with_home() (joining a manual lodging point to the matrix) are replayed too;
        forward-looking validation (e.g. pick_lodging's still-offered check) is not -- the action already passed
        it once, when it was first performed."""
        t = action.get("type")
        if t == "set_lodging" and action.get("_point"):
            self._ensure_lodging_node(base, s2.decision, action["_point"])
        if t == "pick_variant":
            # NONE scope (no relayout), but prev_results is meaningless here (it belongs to whatever was active
            # before this pick, if anything) -- the newly chosen variant's own pristine schedule is what's active.
            return next(v["_results"] for v in base.variants if v["id"] == s2.state.chosen_variant)
        scope = act_scope(action)
        if scope == NONE:
            return prev_results
        if scope == RELAYOUT:
            touched = self._touched_days(old_state, s2.state, prev_results)
            results, _ = self._relayout(base, s2, prev_results, touched)
            return results
        if scope == VARIANT:
            results, _ = self._rebuild_variant(base, s2)
            return results
        if scope == LODGING_HOME:
            results, _ = self._relayout(base, s2, prev_results, set(range(len(base.trip.days))))
            return results
        # LODGING_FETCH: set_lodging_budget only narrows what is offered later (_offered_lodging), it does not
        # move the day anchor, so no day needs relaying out; set_lodging changes every day's start/end node.
        if t == "set_lodging_budget":
            self._refetch_lodging(base, s2)
            return prev_results
        results, _ = self._relayout(base, s2, prev_results, set(range(len(base.trip.days))))
        return results

    # ---------- act / undo / redo ----------

    def act(self, sid: str, action: dict) -> dict:
        s = self._get(sid)
        base = self._ensure_base(sid)
        with self.store.lock(sid):
            t = action.get("type")
            if t == "undo":
                if s.position == 0:
                    raise ActionError("nothing to undo")
                s.position -= 1
                self.store.save(s)
                return {"view": self._view(s), "diff": {"scope": "none"}}
            if t == "redo":
                if s.position + 1 >= len(s.states):
                    raise ActionError("nothing to redo")
                s.position += 1
                self.store.save(s)
                return {"view": self._view(s), "diff": {"scope": "none"}}

            if s.state.chosen_variant is None and t != "pick_variant":
                raise ActionError("pick a variant before editing the plan")
            prev_results = self._schedules.get(sid, [None])[s.position] or \
                (next(v["_results"] for v in base.variants if v["id"] == s.state.chosen_variant)
                if s.state.chosen_variant else [])
            ctx = ActCtx(by_place=base.trip.by_place, n_days=len(base.trip.days),
                        variant_ids={v["id"] for v in base.variants},
                        backup_ids={b["id"]: b for b in s.decision.get("backup_pool") or []},
                        day_members=[list(r.order) for r in prev_results] if prev_results else [],
                        objective_names=set(LABEL), valid_paces=set(self.cfg.per_day))
            if t == "pick_lodging":
                if action.get("id") not in {c["id"] for c in self._offered_lodging(base, s.state)}:
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
                    self._ensure_lodging_node(base, s.decision, point)
                action = {**action, "_point": point}
            elif t == "relax" and action.get("scope") == "whole_trip" and "place_ids" not in action:
                feature = action.get("feature")
                affected = [pid for pid, p in base.trip.by_place.items()
                           if feature not in p.relaxed and self._has_hard_violation(base, s, pid, feature)]
                action = {**action, "place_ids": affected}

            new_state = _apply(s.state, action, ctx)
            s2 = s.model_copy(update={"states": s.states[: s.position + 1] + [new_state], "position": s.position + 1})
            results = self._compute_results(base, s2, s.state, prev_results, action)

            s.states = s.states[: s.position + 1] + [new_state]
            s.position += 1
            self._schedules.setdefault(sid, [None] * len(s.states))
            while len(self._schedules[sid]) < len(s.states):
                self._schedules[sid].append(None)
            self._schedules[sid] = self._schedules[sid][: len(s.states)]
            self._schedules[sid][s.position] = results
            s.log = s.log[: s.position - 1] + [{"action": action}]
            self.store.save(s)
            return {"view": self._view(s), "diff": {"scope": act_scope(action)}}

    # ---------- confirm ----------

    def confirm(self, sid: str) -> dict:
        s = self._get(sid)
        base = self._ensure_base(sid)
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

    def baseline_travel_min(self, sid: str) -> int:
        """Total travel minutes of the chosen variant's own day membership, laid out by plain nearest-neighbour
        from base/entry (docs/specs/PLANNING_SPEC.md §Đo: "baseline = nearest-neighbour + anchor base, không chọn
        chỗ ở"). base.variants is always built before the lodging crawl (_build_base), so its own `_results` are
        already anchored at base/entry, never at a lodging candidate -- exactly the baseline the spec means."""
        s = self._get(sid)
        base = self._ensure_base(sid)
        if s.state.chosen_variant is None:
            raise ActionError("pick a variant before measuring a baseline")
        from .route import _nearest_neighbour
        from .schedule import simulate
        results = next(v["_results"] for v in base.variants if v["id"] == s.state.chosen_variant)
        return sum(simulate(_nearest_neighbour(list(r.order), cx), cx).travel_min
                   for cx, r in zip(base.trip.ctxs, results))

    # ---------- turn (docs/specs/PLANNING_SPEC.md §Vòng người dùng sửa và góp ý) ----------

    def _turn_current(self, s: Session, base: _Base) -> list | None:
        """The laid-out days a turn talks about: the active Schedule, or the first variant's before a pick."""
        results = self._schedules.get(s.id, [None] * len(s.states))[s.position] if s.state.chosen_variant else None
        if results is None and base.variants:
            results = base.variants[0]["_results"]
        return results

    def _turn_aliases(self, s: Session, base: _Base) -> dict[str, dict]:
        """P# for every place currently in the plan, L# for every lodging candidate on screen, V# for every variant on
        screen -- built from the same state the screen shows, so the agent can only name what the user can see."""
        out: dict[str, dict] = {}
        by_place = self._places_for(s, base)
        for day, r in enumerate(self._turn_current(s, base) or []):
            for pid in r.order:
                p = by_place.get(pid)
                if p is not None:
                    out[f"P{sum(1 for v in out.values() if v['kind'] == 'place') + 1}"] = {
                        "kind": "place", "id": pid, "name": p.rec["identity"]["name"], "day": day}
        for c in self._offered_lodging(base, s.state):
            out[f"L{sum(1 for v in out.values() if v['kind'] == 'lodging') + 1}"] = {
                "kind": "lodging", "id": c["id"], "name": c["name"]}
        for v in base.variants:
            out[f"V{sum(1 for x in out.values() if x['kind'] == 'variant') + 1}"] = {
                "kind": "variant", "id": v["id"], "label": v["label"]}
        return out

    def _turn_day_order(self, s: Session, base: _Base) -> dict[int, list[str]]:
        return {i: list(r.order) for i, r in enumerate(self._turn_current(s, base) or [])}

    def _turn_fields(self, aliases: dict, text: str) -> dict:
        from corpus.ontology import load as load_ontology
        features = "\n".join(f"{f.id}: {'|'.join(f.values)}" for f in load_ontology().features.values())
        by_day: dict[int, list[str]] = {}
        for k, v in aliases.items():
            if v["kind"] == "place":
                by_day.setdefault(v["day"], []).append(f"{k} {v['name']}")
        days = "\n".join(f"Ngày {d + 1}: " + ", ".join(items) for d, items in sorted(by_day.items())) or "none"
        variants = "\n".join(f"{k} | {v['label']}" for k, v in aliases.items() if v["kind"] == "variant") or "none"
        lodging = "\n".join(f"{k} | {v['name']}" for k, v in aliases.items() if v["kind"] == "lodging") or "none"
        return {"features": features, "days": days, "variants": variants, "lodging": lodging, "text": text}

    def _turn_screen_text(self, fields: dict) -> str:
        """Everything the screen shows that a number in `say` may legitimately come from."""
        return f"{fields['days']} {fields['variants']} {fields['lodging']}"

    def turn(self, sid: str, text: str, emit: Callable[[str, dict], None]) -> None:
        """One typed message: one agent call (or the keyword policy when it fails), then each produced action goes
        through the same act() a chip click uses -- so scope, locked-place protection and undo are the chip's own."""
        base = self._ensure_base(sid)
        with self.store.lock(sid):
            s = self._get(sid)
            aliases = self._turn_aliases(s, base)
            day_order = self._turn_day_order(s, base)
            fields = self._turn_fields(aliases, text)
            streamed: list[str] = []

            def on_say(d: str) -> None:
                streamed.append(d)
                emit("say", {"delta": d})

            try:
                if self.agent is None:
                    raise AgentError("no agent configured")
                plan = asyncio.run(self.agent(fields, on_say))
                g = guard(plan, text, aliases, day_order, self._turn_screen_text(fields))
                actions, say = g.actions, g.say
            except Exception as e:  # any agent failure degrades to the keyword policy, never to a 500
                if not isinstance(e, AgentError):
                    traceback.print_exc()   # a bug, not an unavailable model: keep it visible in the server log
                (actions, say), log = policy(text, aliases), [f"agent_fallback: {type(e).__name__}: {e}"]
            else:
                log = g.log

            done, scopes = [], []
            drops_before = len(s.state.dropped)
            for action in actions:
                if action.get("type") == "drop_place" and drops_before + len(
                        [a for a in done if a.get("type") == "drop_place"]) >= self.cfg.rethink_drops:
                    log.append(f"skip {action}: rethink_drops reached")
                    say = ("Bạn đã bỏ khá nhiều nơi trong lượt này. Có thể lịch đang không hợp với bạn ngay từ đầu "
                           "-- quay lại Place Decision để chọn lại nơi sẽ hợp hơn là bỏ từng chỗ một.")
                    continue
                try:
                    out = self.act(sid, action)
                except ActionError as e:
                    log.append(f"skip {action}: {e}")
                    continue
                done.append(action)
                scopes.append(out["diff"]["scope"])

            say = say or (DONE if done else NO_PLAN_SAY)
            if say != "".join(streamed):
                emit("say", {"replace": say})
            emit("view", {"view": self._view(self._get(sid)), "diff": {"scope": widest(scopes)}})
            emit("done", {})
