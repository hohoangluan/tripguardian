"""Planning sessions for the web (docs/PLANNING.md §API và web): create (fast, anchor = base), act (chips,
no model), variants, lodging (crawled in the background), confirm. One lock per session; each committing act is one
version that undo / redo moves between.
"""

import asyncio
import copy
import hashlib
import json
import threading
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import replace
from datetime import datetime, timezone
from json import loads
from typing import Awaitable, Callable

import live

from .build import prepare, pull_early, schedule_trip, with_home
from .lodging import candidates as lodging_candidates
from .lodging import booked, live_cards, price_cap, rank, refresh_prices, search_area, with_booked_base
from .objectives import LABEL, add_lodging_cost, choose, metrics, score
from .repair import repair_day
from .robustness import robustness as robustness_of
from .backup import backups as backups_of
from .conditions import crowd_tips, describe
from .timefit import describe as time_description
from .recommendations import recommend
from .agent import AgentError
from .guard import TurnPlan, guard
from .proposal import PlanningProposal
from .policy import DONE, NONE as NO_PLAN_SAY, policy
from .scope import LODGING_FETCH, LODGING_HOME, NONE, RELAYOUT, VARIANT, act_scope, widest
from .session import ActCtx, ActionError, Session, State, Store
from .session import apply_act as _apply
from .settings import Settings
from .settings import load as load_settings
from .cache import day_key, fingerprint, put, travel_key


def _now() -> str:
    """When a log entry was made (UTC, seconds), for the journey timeline in Admin."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
        self.lodging_status = "pending"   # pending | ready | unavailable | booked (the trip has its lodging)
        self.lodging_candidates: list[dict] = []   # every candidate ever crawled, never filtered in place
        self.days: dict = {}
        self.checks: dict = {}
        self.robustness: dict = {}
        self.backups: dict = {}
        self.active: dict = {}
        self.repairs: dict = {}
        self.suggestions: dict = {}
        self.pending: set = set()
        self.generation = time.monotonic_ns()


class Engine:
    def __init__(self, records: list[dict], cfg: Settings | None = None, live_cfg=None, store: Store | None = None,
                geocode_fn=None, matrix_fn=None, sun_fn=None, lodging_fn=None, route_fn=None,
                decision_url: str | None = None, http_post=None, background: bool = True,
                agent: "Agent | None" = None, proposal_agent=None, conditions_fn=None, labels: dict | None = None):
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
        self.proposal_agent = proposal_agent
        self.conditions_fn = conditions_fn      # (decision, by_id) -> (weather, signals); None = no live conditions
        self.labels = labels or {}              # Place Decision's feature / value words, for "hợp vì" (tools.py)
        self._base: dict[str, _Base] = {}
        self._schedules: dict[str, list] = {}
        self._previews: dict[str, tuple[float, _Base]] = {}   # Decision Output hash -> (built at, base)
        self._previews_lock = threading.Lock()
        self._epochs: dict[str, int] = {}
        self.timings: dict[str, dict] = {}
        self._suggestion_slots = threading.BoundedSemaphore(max(1, self.cfg.suggestion_workers))

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
        decision = with_booked_base(decision)  # a booked lodging is where every day starts and ends
        weather, signals = self.conditions_fn(decision, self.by_id) if self.conditions_fn else (None, None)
        return prepare(decision, self.records, self.cfg, self.live_cfg, self.geocode_fn, self.matrix_fn, self.sun_fn,
                       weather, extra_nodes=extra_nodes, signals=signals)

    def _build_base(self, decision: dict) -> _Base:
        trip = self._prepare(decision)
        objectives = choose(decision["trip_context"], [cx.wet for cx in trip.ctxs], trip.ctxs[0].prefs, self.cfg)
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
                             "time_suitability": time_description(s.ctxs, s.results),
                             "recommendations": [],
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
        call, done outside the lock) was still running, so a concurrent set_lodging is never lost. The pool is
        ranked once the travel matrix reaches it (taste first, location after: lodging.rank); served stays then get
        a date's live price in the background, without moving."""
        base = self._base[sid]
        decision = self.store.get(sid).decision
        if booked(decision):
            base.lodging_status = "booked"  # the user has a lodging: nothing to crawl or suggest
            return
        try:
            cands = lodging_candidates(base.trip.by_place, decision, self.cfg, self.lodging_fn, self.live_cfg, self.records)
        except Exception:
            cands = []
        with self.store.lock(sid):
            extra = {c["id"]: (c["lat"], c["lng"]) for c in cands}
            point = self.store.get(sid).state.lodging_point
            if point:
                extra[point["id"]] = (point["lat"], point["lng"])
            if extra:
                base.trip = self._prepare(decision, extra_nodes=extra)
            cands = rank(cands, decision, self._avg_min(base.trip, cands), self.cfg, self.labels)
            base.lodging_candidates = cands
            base.lodging_status = "ready" if cands else "unavailable"
        if any(c["source"] == "corpus" for c in cands):
            if self.background:
                threading.Thread(target=self._lodging_prices, args=(sid,), daemon=True).start()
            else:
                self._lodging_prices(sid)

    @staticmethod
    def _avg_min(trip, cands: list[dict]) -> dict:
        """Candidate id -> mean minutes to the trip's places on the travel matrix (None off the matrix)."""
        ids = [p for p in trip.by_place if p in trip.travel.index]
        return {c["id"]: sum(trip.travel.leg(c["id"], p)[0] for p in ids) / len(ids)
                if ids and c["id"] in trip.travel.index else None for c in cands}

    def _lodging_prices(self, sid: str) -> None:
        """A date's live price for the served stays on screen; a dead source leaves the reference prices."""
        base = self._base[sid]
        decision = self.store.get(sid).decision
        tc = decision["trip_context"]["context"]
        try:
            cards = live_cards(search_area(base.trip.by_place, tc.get("mobility"), self.cfg), tc, None,
                               self.lodging_fn, self.live_cfg)
        except Exception:
            return
        with self.store.lock(sid):
            base.lodging_candidates = refresh_prices(base.lodging_candidates, cards,
                                                     price_cap(tc, _nights(tc), self.cfg))

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
        if point := booked(decision):  # as if set_lodging had run: the user's own lodging, from the start
            s.states[0] = State(lodging_touched=True, lodging_id=point["id"], lodging_point=point)
        base = self._take_preview(decision) or self._build_base(decision)
        self._base[s.id] = base
        self.store.save(s)
        if self.background:
            threading.Thread(target=self._crawl_lodging, args=(s.id,), daemon=True).start()
        else:
            self._crawl_lodging(s.id)
        with self.store.lock(s.id):
            self._queue_suggestions(s)
            return {"id": s.id, "view": self._view(s)}

    # ---------- background preview (no session; reused by create) ----------

    PREVIEW_TTL_S = 900
    PREVIEW_KEEP = 16

    @staticmethod
    def _decision_key(decision: dict) -> str:
        return hashlib.sha256(json.dumps(decision, sort_keys=True, default=str).encode()).hexdigest()

    def _take_preview(self, decision: dict) -> "_Base | None":
        """A base an earlier preview() built for exactly this Decision Output; create() owns it from here on."""
        with self._previews_lock:
            hit = self._previews.pop(self._decision_key(decision), None)
        return hit[1] if hit and time.monotonic() - hit[0] < self.PREVIEW_TTL_S else None

    def preview(self, decision: dict) -> dict:
        """Variants for a Decision Output not confirmed yet: what the schedule would look like now. Creates no
        session and writes nothing; the base is cached by the output's hash so create() for it skips the build."""
        key = self._decision_key(decision)
        with self._previews_lock:
            hit = self._previews.get(key)
        if hit and time.monotonic() - hit[0] < self.PREVIEW_TTL_S:
            base = hit[1]
        else:
            base = self._build_base(decision)
            with self._previews_lock:
                self._previews[key] = (time.monotonic(), base)
                while len(self._previews) > self.PREVIEW_KEEP:
                    self._previews.pop(next(iter(self._previews)))
        return {"ok": base.ok, "days": len(base.trip.days), "warnings": base.warnings,
                "back_to_decision": base.back_to_decision,
                "variants": [{"id": v["id"], "objective": v["objective"], "label": v["label"], "metrics": v["metrics"],
                              "robustness": {"level": v["robustness"]["level"], "label": v["robustness"]["label"]},
                              "places": [[it["place_id"] for it in d["items"] if it["kind"] == "visit" and it.get("place_id")]
                                         for d in v["itinerary"]]}
                             for v in base.variants]}

    def _get(self, sid: str) -> Session:
        try:
            return self.store.get(sid)
        except KeyError:
            raise NoSession(sid) from None

    def _offered_lodging(self, base: _Base, state: State) -> list[dict]:
        """Every crawled candidate still within the session's current price cap -- state.budget_override narrows
        what is *offered*, it never discards what was actually found (undo must be able to bring a candidate back,
        and the chosen one must stay resolvable even if it falls outside a later-lowered cap). Without an override,
        a served stay whose late live price went over the trip's cap is not offered."""
        cap = state.budget_override
        if cap is None:
            return [c for c in base.lodging_candidates if not c.get("over_cap")]
        return [c for c in base.lodging_candidates if c["price_vnd"] is None or c["price_vnd"] <= cap]

    def _active_itinerary(self, s: Session, base: _Base, results=None) -> dict | None:
        """The itinerary / travel_load of the session's currently chosen variant, with every committed act applied
        -- None before a variant is chosen, since there is nothing laid out yet to show."""
        if s.state.chosen_variant is None:
            return None
        if results is None:
            results = self._schedules.get(s.id, [None] * len(s.states))[s.position]
        if results is None:
            results = next(v["_results"] for v in base.variants if v["id"] == s.state.chosen_variant)
        by_place = self._places_for(s, base)
        home = self._home_for(s, base)
        _, ctxs = self._ctxs_for(base.trip, by_place, home, s.state, results)
        from .build import itinerary as render_itinerary
        from .build import travel_load as render_travel_load
        from .validate import validate
        tc = s.decision["trip_context"]
        keys = [fingerprint((day_key(cx, result.order), result)) for cx, result in zip(ctxs, results)]
        cand = next((c for c in base.lodging_candidates if c["id"] == home), None)
        candidate_nodes = {p["id"] for p in s.decision.get("backup_pool") or []} | {pid for r in results for pid in r.order}
        candidate_nodes |= {n for cx in ctxs for n in (cx.day.start_node, cx.day.end_node) if n is not None}
        travels = {id(cx.travel): cx.travel for cx in ctxs}
        context_key = fingerprint((keys, tc, s.decision.get("confirmed"), s.decision.get("backup_pool"),
                                   {p["id"]: self.by_id.get(p["id"]) for p in s.decision.get("backup_pool") or []},
                                   [travel_key(t, candidate_nodes) for t in travels.values()]))
        active_key = fingerprint((context_key, cand))
        if active_key in base.active:
            self.timings.setdefault(s.id, {})["day_cache_hits"] = self.timings.get(s.id, {}).get("day_cache_hits", 0) + len(keys)
            return base.active[active_key]
        artifacts = []
        for cx, result, key in zip(ctxs, results, keys):
            if key not in base.days:
                started = time.perf_counter()
                m = metrics([cx], [result])
                self.timings.setdefault(s.id, {})["metrics_ms"] = (time.perf_counter() - started) * 1000
                put(base.days, key, {"itinerary": render_itinerary([cx.day], [result])[0],
                                    "travel_load": render_travel_load([cx.day], [result])[0],
                                    "time_suitability": time_description([cx], [result])[0], "metrics": m},
                    self.cfg.cache_entries)
            else:
                self.timings.setdefault(s.id, {})["day_cache_hits"] = self.timings.get(s.id, {}).get("day_cache_hits", 0) + 1
            artifacts.append(base.days[key])
        m = {k: sum(a["metrics"][k] for a in artifacts) for k in artifacts[0]["metrics"]} if artifacts else metrics([], [])
        if cand:
            m = add_lodging_cost(m, cand["price_vnd"], _nights(tc["context"]))
        started = time.perf_counter()
        anchors = {c["id"] for c in s.decision["confirmed"] if c.get("role") == "anchor"}
        violations = validate(ctxs, results, tc.get("hard_filters") or [], anchors, tc["context"].get("budget_vnd"),
                              (tc.get("pace") or {}).get("max_leg_min"), day_cache=base.checks,
                              cache_limit=self.cfg.cache_entries)
        self.timings.setdefault(s.id, {})["validate_ms"] = (time.perf_counter() - started) * 1000
        if context_key not in base.backups:
            put(base.backups, context_key, backups_of(ctxs, results, s.decision, self.by_id), self.cfg.cache_entries)
        return put(base.active, active_key, {"itinerary": [a["itinerary"] for a in artifacts], "travel_load": [a["travel_load"] for a in artifacts],
                "time_suitability": [a["time_suitability"] for a in artifacts], "metrics": m,
                "violations": [vars(v) for v in violations],
                "context_key": context_key,
                "backups": base.backups[context_key],
                "robustness": robustness_of(ctxs, results, base.trip.travel.source, day_cache=base.robustness),
                "ctxs": ctxs, "results": results}, self.cfg.cache_entries)

    def _suggestions(self, s, base, active) -> dict:
        key = active["context_key"] if active else None
        token = fingerprint((s.id, base.generation, self._epochs.get(s.id, 0), key))
        result = base.suggestions.get(key) or {"status": "pending" if active else "unavailable", "items": []}
        return {**result, "token": token, "session_id": s.id}

    def _queue_suggestions(self, s: Session, active=None) -> None:
        base = self._ensure_base(s.id)
        active = active if active is not None else self._active_itinerary(s, base)
        if not active:
            return
        key = active["context_key"]
        if key in base.suggestions or key in base.pending:
            return
        if self.background and not self._suggestion_slots.acquire(blocking=False):
            return
        background = self.background
        base.pending.add(key)
        pool_records = {p["id"]: self.by_id[p["id"]] for p in s.decision.get("backup_pool") or [] if p["id"] in self.by_id}
        try:
            ctxs, results, decision, by_id = copy.deepcopy((active["ctxs"], active["results"], s.decision, pool_records))
        except Exception:
            base.pending.discard(key)
            if background:
                self._suggestion_slots.release()
            put(base.suggestions, key, {"status": "unavailable", "items": []}, self.cfg.cache_entries)
            return
        def work():
            started = time.perf_counter()
            try:
                result = {"status": "ready", "items": recommend(ctxs, results, decision, by_id)}
            except Exception:
                result = {"status": "unavailable", "items": []}
            finally:
                if background:
                    self._suggestion_slots.release()
            with self.store.lock(s.id):
                base.pending.discard(key)
                if self._base.get(s.id) is base:
                    put(base.suggestions, key, result, self.cfg.cache_entries)
                    self.timings.setdefault(s.id, {})["suggestions_ms"] = (time.perf_counter() - started) * 1000
        if background:
            try:
                threading.Thread(target=work, daemon=True).start()
            except Exception:
                base.pending.discard(key)
                self._suggestion_slots.release()
                put(base.suggestions, key, {"status": "unavailable", "items": []}, self.cfg.cache_entries)
        else:
            work()

    def suggestions(self, sid: str) -> dict:
        with self.store.lock(sid):
            s = self._get(sid)
            self._queue_suggestions(s)
            base = self._ensure_base(sid)
            return self._suggestions(s, base, self._active_itinerary(s, base))

    def _view(self, s: Session, results=None, active=None) -> dict:
        base = self._ensure_base(s.id)
        active = active if active is not None else self._active_itinerary(s, base, results)
        suggestions = self._suggestions(s, base, active)
        return {"ok": base.ok, "variants": [{k: v for k, v in v.items() if not k.startswith("_")} for v in base.variants],
               "comparison": base.comparison, "warnings": base.warnings, "back_to_decision": base.back_to_decision,
               "lodging": {"status": base.lodging_status,
                           "candidates": [self._lodging_card(c) for c in self._offered_lodging(base, s.state)]},
               "itinerary": active["itinerary"] if active else None, "travel_load": active["travel_load"] if active else None,
               "metrics": active["metrics"] if active else None, "violations": active["violations"] if active else [],
               "backups": active["backups"] if active else None, "robustness": active["robustness"] if active else None,
               "time_suitability": active["time_suitability"] if active else None,
               "recommendations": suggestions["items"], "suggestions": suggestions,
               "day_conditions": [{"day": cx.day.index + 1, "date": cx.day.date.isoformat() if cx.day.date else None,
                                   **(describe(cx.cond) or {})} for cx in base.trip.ctxs if cx.cond],
               "crowd_tips": crowd_tips(list(self._places_for(s, base).values()), [cx.cond for cx in base.trip.ctxs], self.cfg),
               "state": s.state.model_dump(mode="json")}

    def _lodging_card(self, c: dict) -> dict:
        """What the "Bạn ở đâu?" screen shows of a candidate (docs/Role_Web_Functional_Design.md §6)."""
        names = self.labels.get("feature") or {}
        return {"id": c["id"], "name": c["name"], "price_vnd": c["price_vnd"], "source": c.get("source"),
                "price_at": c.get("price_at") if c.get("price_source") else None,
                "rating": c.get("rating"), "reviews": c.get("reviews"), "avg_min": c.get("avg_min"),
                "fit": [{k: f[k] for k in ("text", "mentions", "quote")} for f in c.get("fit") or []],
                "unverified": [names.get(f, f.replace("_", " ")).lower() for f in c.get("unverified") or []]}

    def load(self, sid: str) -> dict:
        with self.store.lock(sid):
            s = self._get(sid)
            active = self._active_itinerary(s, self._ensure_base(sid))
            self._queue_suggestions(s, active)
            return {"id": s.id, "view": self._view(s, active=active)}

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
        if p is None and pid in {b["id"] for b in s.decision.get("backup_pool") or []}:
            from .places import build_places
            tc = {**s.decision["trip_context"], "activities": {
                **(s.decision["trip_context"].get("activities") or {}), **s.state.activity_override}}
            built, _ = build_places({"confirmed": [{"id": pid}], "trip_context": tc}, self.by_id, self.cfg)
            p = built[0] if built else None
        elif p and pid in s.state.activity_override:
            activity = s.state.activity_override[pid]
            p = replace(p, activity=activity, activity_explicit=True, kind="meal" if activity == "eating" else "experience")
        return replace(p, relaxed=p.relaxed + tuple(relax_for)) if p and relax_for else p

    def _places_for(self, s: Session, base: _Base) -> dict:
        dropped = {d.place_id for d in s.state.dropped}
        out = {}
        for pid in set(base.trip.by_place) | set(s.state.assignment):
            if pid not in dropped:
                p = self._active_place(s, base, pid)
                if p is None:
                    raise ActionError(f"cannot schedule backup {pid!r}: missing place data")
                out[pid] = p
        return out

    def _home_for(self, s: Session, base: _Base) -> str | None:
        state = s.state
        if not state.lodging_touched:
            return base.variants[0]["_home"] if base.variants else None
        if state.lodging_point:
            return state.lodging_point["id"]
        return state.lodging_id

    def _ctxs_for(self, trip, by_place: dict, home: str | None, state: State, results: list | None = None):
        """results: days already laid out; their windows get the scheduler's own early start for a sunrise place."""
        t2 = trip if home in (None, trip.days[0].start_node if trip.days else None) else with_home(trip, home)
        ctxs = list(t2.ctxs)                 # a fresh list: never mutate t2.ctxs (shared with base.trip) in place
        if state.pace_override and state.pace_override != t2.pace:
            ctxs = [replace(cx, pace=state.pace_override) for cx in ctxs]
        for day, (lo, hi) in state.day_window_override.items():
            if 0 <= day < len(ctxs):
                ctxs[day] = replace(ctxs[day], day=replace(ctxs[day].day, start=lo, end=hi))
        ctxs = [replace(cx, places=by_place, travel=t2.travel, cfg=self.cfg) for cx in ctxs]
        if results is not None:
            ctxs = [pull_early(cx, [i.place_id for i in r.items if i.kind == "visit"], by_place, t2.travel)[0]
                    for cx, r in zip(ctxs, results)] + ctxs[len(results):]
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
                base = self._base[s.id]
                tc = s.decision["trip_context"]
                hard, budget, max_leg = tc.get("hard_filters") or [], tc["context"].get("budget_vnd"), (tc.get("pace") or {}).get("max_leg_min")
                key = fingerprint((day_key(ctxs[day], members[day]), members[day], prev_order,
                                   sorted(locked_here), hard, budget, max_leg))
                from .validate import validate
                if key not in base.repairs:
                    result = repair_day(members[day], ctxs[day], prev_order, locked_here, self.cfg,
                                        valid=lambda r: not validate([ctxs[day]], [r], hard, set(), budget, max_leg))
                    put(base.repairs, key, result, self.cfg.cache_entries)
                results[day] = base.repairs[key]
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
               "time_suitability": time_description(ctxs, results),
               "recommendations": self._suggestions(s, base, self._active_itinerary(s, base, results))["items"],
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
        from requirements import allowed
        p = base.trip.by_place.get(pid)
        if not p:
            return False
        hard_filters = s.decision["trip_context"].get("hard_filters") or []
        return any(hf["feature"] == feature and feature not in p.relaxed
                  and not allowed(p.rec, hf, p.activity, p.kind) for hf in hard_filters)

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
        if t == "recommend":
            return self._proposal_trial(base, s2, old_state, prev_results, action["proposal"])[1]
        if t == "set_lodging" and action.get("_point"):
            self._ensure_lodging_node(base, s2.decision, action["_point"])
        if t == "pick_variant":
            state = s2.state
            if (state.assignment or state.dropped or state.order_override or state.pace_override
                    or state.objective_override or state.day_window_override or state.lodging_touched or state.relaxed
                    or state.activity_override):
                return self._rebuild_variant(base, s2)[0]
            return next(v["_results"] for v in base.variants if v["id"] == s2.state.chosen_variant)
        scope = act_scope(action)
        if scope == NONE:
            return prev_results
        if scope == RELAYOUT:
            touched = self._touched_days(old_state, s2.state, prev_results)
            results, _ = self._relayout(base, s2, prev_results, touched)
            return results
        if scope == VARIANT:
            if t == "set_day_window":
                results, ctxs = self._relayout(base, s2, prev_results, {action["day"]})
                from .validate import validate
                tc = s2.decision["trip_context"]
                anchors = {c["id"] for c in s2.decision["confirmed"] if c.get("role") == "anchor"}
                if not validate(ctxs, results, tc.get("hard_filters") or [], anchors,
                                tc["context"].get("budget_vnd"), (tc.get("pace") or {}).get("max_leg_min")):
                    return results
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
        started = time.perf_counter()
        with self.store.lock(sid):
            s = self._get(sid)
            base = self._ensure_base(sid)
            self.timings[sid] = {key: 0 for key in ("layout_ms", "validate_ms", "metrics_ms", "suggestions_ms",
                                                   "view_ms", "operation_ms", "day_cache_hits")}
            t = action.get("type")
            if t == "undo":
                if s.position == 0:
                    raise ActionError("nothing to undo")
                draft = s.model_copy(update={"position": s.position - 1})
                active = self._active_itinerary(draft, base)
                view = self._view(draft, active=active)
                self.store.save(draft)
                s.position = draft.position
                self._epochs[sid] = self._epochs.get(sid, 0) + 1
                self._queue_suggestions(s, active)
                view["suggestions"] = self._suggestions(s, base, active)
                view["recommendations"] = view["suggestions"]["items"]
                self.timings.setdefault(sid, {})["operation_ms"] = (time.perf_counter() - started) * 1000
                return {"view": view, "diff": {"scope": "none"}}
            if t == "redo":
                if s.position + 1 >= len(s.states):
                    raise ActionError("nothing to redo")
                draft = s.model_copy(update={"position": s.position + 1})
                active = self._active_itinerary(draft, base)
                view = self._view(draft, active=active)
                self.store.save(draft)
                s.position = draft.position
                self._epochs[sid] = self._epochs.get(sid, 0) + 1
                self._queue_suggestions(s, active)
                view["suggestions"] = self._suggestions(s, base, active)
                view["recommendations"] = view["suggestions"]["items"]
                self.timings.setdefault(sid, {})["operation_ms"] = (time.perf_counter() - started) * 1000
                return {"view": view, "diff": {"scope": "none"}}

            if s.state.chosen_variant is None and t != "pick_variant":
                raise ActionError("pick a variant before editing the plan")
            prev_results = self._schedules.get(sid, [None])[s.position] or \
                (next(v["_results"] for v in base.variants if v["id"] == s.state.chosen_variant)
                if s.state.chosen_variant else [])
            ctx = ActCtx(by_place={**base.trip.by_place, **self._places_for(s, base)}, n_days=len(base.trip.days),
                        variant_ids={v["id"] for v in base.variants},
                        backup_ids={b["id"]: b for b in s.decision.get("backup_pool") or []},
                        day_members=[list(r.order) for r in prev_results] if prev_results else [],
                        objective_names=set(LABEL), valid_paces=set(self.cfg.per_day),
                        activities=s.decision["trip_context"].get("activities") or {})
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
            layout_start = time.perf_counter()
            results = self._compute_results(base, s2, s.state, prev_results, action)
            self.timings.setdefault(sid, {})["layout_ms"] = (time.perf_counter() - layout_start) * 1000
            render_start = time.perf_counter()
            active = self._active_itinerary(s2, base, results)
            view = self._view(s2, results, active)
            self.timings[sid]["view_ms"] = (time.perf_counter() - render_start) * 1000
            s2.log = s.log[:s.position] + [{"action": action, "at": _now()}]
            s2.output = None
            self.store.save(s2)
            s.states, s.position, s.log, s.output = s2.states, s2.position, s2.log, s2.output
            self._schedules.setdefault(sid, [None] * len(s.states))
            while len(self._schedules[sid]) < len(s.states):
                self._schedules[sid].append(None)
            self._schedules[sid] = self._schedules[sid][: len(s.states)]
            self._schedules[sid][s.position] = results
            self._epochs[sid] = self._epochs.get(sid, 0) + 1
            self._queue_suggestions(s, active)
            view["suggestions"] = self._suggestions(s, base, active)
            view["recommendations"] = view["suggestions"]["items"]
            self.timings[sid]["operation_ms"] = (time.perf_counter() - started) * 1000
            scope = act_scope(action)
            if t == "set_day_window" and all(old is new for i, (old, new) in enumerate(zip(prev_results, results))
                                             if i != action["day"]):
                scope = RELAYOUT
            return {"view": view, "diff": {"scope": scope}}

    # ---------- internal recommendation ----------

    def _proposal_trial(self, base, session, state, previous, proposal):
        trial = session.model_copy(deep=True)
        trial.states = [state.model_copy(deep=True)]
        trial.position = 0
        ctx = ActCtx({**base.trip.by_place, **self._places_for(trial, base)}, len(base.trip.days),
                     {v['id'] for v in base.variants}, {b['id']: b for b in session.decision.get('backup_pool') or []},
                     [list(r.order) for r in previous], set(LABEL), set(self.cfg.per_day),
                     session.decision['trip_context'].get('activities') or {})
        trial.states[0] = _apply(trial.state, {'type': 'pick_variant', 'id': proposal['variant_id']}, ctx)
        # Rebuild for the chosen objective with the user's pace, day windows, home and edits.
        results, _ = self._rebuild_variant(base, trial)
        for action in proposal.get('acts', []):
            ctx = replace(ctx, by_place={**base.trip.by_place, **self._places_for(trial, base)},
                          day_members=[list(r.order) for r in results])
            old = trial.state
            trial.states[0] = _apply(old, action, ctx)
            results = self._compute_results(base, trial, old, results, action)
        return trial.state, results

    def recommend(self, sid: str) -> dict:
        """One proposal over a deterministic baseline; only validated drafts become session state."""
        self._get(sid)
        with self.store.lock(sid):
            base = self._ensure_base(sid)
            session = self._get(sid)
            if not base.variants:
                return {'id': sid, 'view': self._view(session),
                        'proposal': {'status': 'fallback', 'diagnostics': ['no_valid_baseline']}}
            if session.state.chosen_variant is None:
                self.act(sid, {'type': 'pick_variant', 'id': base.variants[0]['id']})
            previous = self._turn_current(session, base)
            view = self._view(session)
            def stable_view(value):
                return {k: v for k, v in value.items() if k not in {'suggestions', 'recommendations'}}
            snapshot = {'session': session.model_dump(mode='json'), 'view': stable_view(view)}
            fingerprint = hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()
            diagnostics = {f'warning:{i}': w for i, w in enumerate(view['warnings'])}
            fields = {'fingerprint': fingerprint, 'variants': view['variants'], 'diagnostics': diagnostics,
                      'state': view['state'], 'itinerary': view['itinerary'],
                      'hard_filters': session.decision['trip_context'].get('hard_filters') or []}
            status, log = 'fallback', []
            try:
                if self.proposal_agent is None:
                    raise ActionError('proposal_unavailable')
                async def call():
                    return await asyncio.wait_for(self.proposal_agent(fields), timeout=self.cfg.total_s)
                raw = asyncio.run(call())
                proposal = PlanningProposal.model_validate(raw).model_dump(mode='json')
                current = {'session': session.model_dump(mode='json'), 'view': stable_view(self._view(session))}
                current_fp = hashlib.sha256(json.dumps(current, sort_keys=True, default=str).encode()).hexdigest()
                if proposal['fingerprint'] != fingerprint or current_fp != fingerprint:
                    raise ActionError('stale_fingerprint')
                if any(reason not in diagnostics for reason in proposal['reasons']):
                    raise ActionError('unknown_diagnostic')
                state, results = self._proposal_trial(base, session, session.state, previous, proposal)
                def membership(rs):
                    return sorted(pid for r in rs for pid in r.order)
                if membership(results) != membership(previous):
                    raise ActionError('membership_changed')
                anchors = {c['id'] for c in session.decision['confirmed'] if c.get('role') == 'anchor'}
                decision_locked = {c['id'] for c in session.decision['confirmed']
                                   if c.get('role') == 'locked'}
                protected = anchors | decision_locked | set(session.state.locked)
                def slots(rs):
                    return [(day, item) for day, result in enumerate(rs) for item in result.items
                            if item.place_id in protected]
                if slots(results) != slots(previous):
                    raise ActionError('protected_slot_changed')
                _, ctxs = self._ctxs_for(base.trip, self._places_for(session, base),
                                         self._home_for(session, base), state, results)
                from .validate import validate
                tc = session.decision['trip_context']
                if validate(ctxs, results, tc.get('hard_filters') or [], anchors,
                            tc['context'].get('budget_vnd'), (tc.get('pace') or {}).get('max_leg_min')):
                    raise ActionError('validation_failed')
                # Compare both validated schedules with the CURRENT objective, never the
                # proposed variant's objective. score() includes travel as its tie-breaker.
                objective = session.state.objective_override or next(
                    v['objective'] for v in base.variants if v['id'] == session.state.chosen_variant)
                baseline_metrics = metrics(ctxs, previous)
                draft_metrics = metrics(ctxs, results)
                if score(objective, draft_metrics) > score(objective, baseline_metrics):
                    raise ActionError('objective_worse')
                committed = session.model_copy(deep=True)
                committed.states = session.states[:session.position + 1] + [state]
                committed.log = session.log[:session.position] + [{'action': {'type': 'recommend', 'proposal': proposal},
                                                                  'at': _now()}]
                committed.position += 1
                self._view(committed, results)
                self.store.save(committed)
                session.states, session.log, session.position = committed.states, committed.log, committed.position
                self._schedules[sid] = self._schedules.get(sid, [None] * session.position)[:session.position] + [results]
                self._epochs[sid] = self._epochs.get(sid, 0) + 1
                self._queue_suggestions(session)
                status, log = 'accepted', proposal['reasons']
            except Exception as exc:
                log = [str(exc) if isinstance(exc, ActionError) else type(exc).__name__]
            return {'id': sid, 'view': self._view(session), 'proposal': {'status': status, 'diagnostics': log}}

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
            trip, ctxs = self._ctxs_for(base.trip, by_place, home, s.state, results)
            from .validate import validate
            tc = s.decision["trip_context"]
            anchors = {c["id"] for c in s.decision["confirmed"] if c.get("role") == "anchor"}
            violations = validate(ctxs, results, tc.get("hard_filters") or [], anchors, tc["context"].get("budget_vnd"),
                                  (tc.get("pace") or {}).get("max_leg_min"))
            if violations:
                raise NotConfirmable("plan has unresolved violations")
            variant = self._variant_dict(base, s, results, ctxs)
            coords = {**{p.id: (p.lat, p.lng) for p in by_place.values()},
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
        from base/entry (docs/PLANNING.md §Đo: "baseline = nearest-neighbour + anchor base, không chọn
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

    # ---------- turn (docs/PLANNING.md §Vòng người dùng sửa và góp ý) ----------

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
