"""Planning sessions for the web (docs/P4_PLANNING.md §CLI và API): create (fast, anchor = base), act (chips,
no model), variants, lodging (crawled in the background), confirm. One lock per session; each committing act is one
version that undo / redo moves between.
"""

import asyncio
import hashlib
import json
import math
import threading
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import replace
from datetime import datetime, UTC
from json import loads
from collections.abc import Awaitable, Callable

import live
from trip import nights as nights_of

from .build import meal_options, night_slots, prepare, pull_early, schedule_trip, slot_days, slot_of, slot_options, slot_pins, with_home
from .lodging import candidates as lodging_candidates
from .lodging import booked, live_cards, price_cap, rank, refresh_prices, search_area, with_booked_base
from .objectives import LABEL, add_lodging_cost, choose, metrics, score
from .repair import repair_day
from .robustness import robustness as robustness_of
from .backup import backups as backups_of
from .conditions import crowd_tips, describe
from .agent import AgentError
from .guard import TurnPlan, guard
from .preview import Resources, configuration_key, decision_dependencies, detached, fingerprint, incremental_schedule
from .proposal import PlanningProposal
from .policy import DONE, NONE as NO_PLAN_SAY, policy
from .scope import LODGING_HOME, NONE, RELAYOUT, VARIANT, act_scope, widest
from .validate import blockers
from .session import ActCtx, ActionError, Session, State, Store, plan_key
from .session import apply_act as _apply
from .settings import Settings
from .settings import load as load_settings


def _now() -> str:
    """When a log entry was made (UTC, seconds), for the journey timeline in Admin."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _http_post(url: str) -> str:
    req = urllib.request.Request(url, method="POST", data=b"{}", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8")


Agent = Callable[[dict, Callable[[str], None]], Awaitable[TurnPlan]]


class NoSession(Exception):
    pass


class NotConfirmable(Exception):
    pass


def _with_added(decision: dict, added, visits: dict) -> dict:
    """The Decision Output with the backup places the user added (add_from_backup, swap) among the confirmed ones,
    so the trip has their record, coordinates and travel times like any other place. visits: id -> the day visit
    Place Decision would have written for it (Engine.visit_fn), when known."""
    have = {c["id"] for c in decision["confirmed"]}
    extra = [{"id": i, "name": i, "role": "selected", "visit": visits.get(i), "flags": [], "relaxed": []}
             for i in sorted(added) if i not in have]
    return {**decision, "confirmed": decision["confirmed"] + extra} if extra else decision


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
        self.added: set[str] = set()      # backup places some version of the session added; in the trip from then on
        self.expires_at = trip.expires_at


class Engine:
    def __init__(self, records: list[dict], cfg: Settings | None = None, live_cfg=None, store: Store | None = None,
                geocode_fn=None, matrix_fn=None, sun_fn=None, lodging_fn=None, route_fn=None,
                decision_url: str | None = None, http_post=None, background: bool = True,
                agent: "Agent | None" = None, proposal_agent=None, conditions_fn=None, labels: dict | None = None,
                lodging_lookup=None, visit_fn=None):
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
        self.lodging_lookup = lodging_lookup    # text -> {"lat", "lng", "source", ...} | None (Logistics.resolve)
        self.visit_fn = visit_fn                # record -> Place Decision's day visit (decision.day_visit), for backups
        self._base: dict[str, _Base] = {}
        self._schedules: dict[str, list] = {}
        self._previews: dict[str, tuple[float, _Base]] = {}   # dependency hash -> (expires at, base)
        self._previews_lock = threading.Lock()
        self._preview_resources = Resources()
        self._preview_latest = {}
        self._preview_flights = {}

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

    def _prepare(self, decision: dict, extra_nodes: dict | None = None, added=()):
        visits = {i: self.visit_fn(self.by_id[i]) for i in added if self.visit_fn and i in self.by_id}
        decision = with_booked_base(_with_added(decision, added, visits))  # a booked lodging: every day starts there
        deadlines = [time.monotonic() + self.PREVIEW_TTL_S]
        ttls = getattr(self.live_cfg, "ttl_s", {})
        resource_ttl = lambda source: min(self.PREVIEW_TTL_S, ttls.get(source, self.PREVIEW_TTL_S))
        condition_key = ("conditions", self._decision_key(decision))
        weather, signals = self._preview_resources.get(condition_key, resource_ttl("weather"),
            lambda: self.conditions_fn(decision, self.by_id), deadlines,
            source_ttl=ttls.get("weather")) if self.conditions_fn else (None, None)
        geocode = self.geocode_fn or (lambda text: live.geocode(text, self.live_cfg))
        matrix = self.matrix_fn or live.travel_matrix
        def cached_geo(text):
            key = ("geocode", text, self.geocode_fn or live.geocode, configuration_key(self.live_cfg))
            return self._preview_resources.get(key, resource_ttl("geocode"), lambda: geocode(text), deadlines,
                                               source_ttl=ttls.get("geocode"))
        def cached_matrix(points, mode, cfg):
            return self._preview_resources.matrix(points, mode, cfg, matrix, resource_ttl("osrm"), deadlines)
        trip = prepare(decision, self.records, self.cfg, self.live_cfg, cached_geo, cached_matrix, self.sun_fn,
                       weather, extra_nodes=extra_nodes, signals=signals)
        trip.expires_at = min(deadlines)
        return trip

    def _variant(self, trip, obj, schedule):
        from .build import itinerary, travel_load
        m = metrics(schedule.ctxs, schedule.results)
        days = [cx.day for cx in schedule.ctxs]
        return {"objective": obj, "label": LABEL[obj], "score": list(score(obj, m)), "metrics": m,
                "itinerary": itinerary(days, schedule.results), "travel_load": travel_load(days, schedule.results),
                "robustness": robustness_of(schedule.ctxs, schedule.results, trip.travel.source),
                "backups": backups_of(schedule.ctxs, schedule.results, trip.decision, trip.by_id),
                "warnings": schedule.warnings, "lodging": {"id": None, "name": None, "price_vnd": None},
                "_results": schedule.results, "_home": trip.days[0].start_node if trip.days else None}

    def _context_key(self, decision: dict, namespace: str | None = None) -> str:
        return fingerprint([namespace, decision["trip_context"], configuration_key(self.cfg),
                            configuration_key(self.live_cfg)])

    def _build_base(self, decision: dict, namespace: str | None = None) -> _Base:
        trip = self._prepare(decision)
        context = self._context_key(decision, namespace)
        with self._previews_lock:
            hit = self._preview_latest.get(context)
        previous = hit[1] if hit and time.monotonic() < hit[0] else None
        if previous:
            trip.routes.update(previous.trip.routes)
        objectives = choose(decision["trip_context"], [cx.wet for cx in trip.ctxs], trip.ctxs[0].prefs, self.cfg)
        variants, seen, failures, per_day = [], set(), [], []
        for obj in objectives:
            old = next((v for v in previous.variants if v["objective"] == obj), None) if previous else None
            schedule = incremental_schedule(trip, old["_results"], self.cfg.objective_weights[obj]) if old else None
            schedule = schedule or schedule_trip(trip, self.cfg.objective_weights[obj])
            if schedule.violations:
                failures.extend(schedule.violations)
                per_day = per_day or schedule.per_day
                continue
            orders = tuple(r.order for r in schedule.results)
            if orders in seen:
                continue
            seen.add(orders)
            variants.append({"id": f"v{len(variants) + 1}", **self._variant(trip, obj, schedule)})
        ok = bool(variants)
        back = None if ok else blockers(failures, per_day)
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
            traceback.print_exc()   # unavailable shows in the app; the reason must stay findable in the server log
            cands = []
        with self.store.lock(sid):
            extra = {c["id"]: (c["lat"], c["lng"]) for c in cands}
            point = self.store.get(sid).state.lodging_point
            if point:
                extra[point["id"]] = (point["lat"], point["lng"])
            if extra:
                base.trip = self._prepare(decision, extra_nodes=extra, added=base.added)
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
                                                     price_cap(tc, nights_of(tc), self.cfg))

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

    def create(self, decision: dict | None = None, decision_session_id: str | None = None,
               *, namespace: str | None = None) -> dict:
        decision = self._resolve(decision, decision_session_id)
        s = self.store.new(decision, decision_session_id)
        if point := booked(decision):  # as if set_lodging had run: the user's own lodging, from the start
            s.states[0] = State(lodging_touched=True, lodging_id=point["id"], lodging_point=point)
        base = self._take_preview(decision, namespace)
        if base is None:
            base = self._build_base(decision) if namespace is None else self._build_base(decision, namespace)
        self._base[s.id] = base
        self.store.save(s)
        if self.background:
            threading.Thread(target=self._crawl_lodging, args=(s.id,), daemon=True).start()
        else:
            self._crawl_lodging(s.id)
        return {"id": s.id, "view": self._view(s)}

    # ---------- background preview (no session; reused by create) ----------

    PREVIEW_TTL_S = 900
    PREVIEW_KEEP = 16

    def _decision_key(self, decision: dict, namespace: str | None = None) -> str:
        return fingerprint([namespace, decision_dependencies(decision), configuration_key(self.cfg),
                            configuration_key(self.live_cfg)])

    def _take_preview(self, decision: dict, namespace: str | None = None) -> "_Base | None":
        with self._previews_lock:
            hit = self._previews.pop(self._decision_key(decision, namespace), None)
        return detached(hit[1], decision) if hit and time.monotonic() < hit[0] else None

    def preview(self, decision: dict, *, namespace: str | None = None) -> dict:
        """Coalesce equivalent previews and reuse valid days from the previous selection."""
        from concurrent.futures import Future
        key = self._decision_key(decision, namespace)
        with self._previews_lock:
            hit = self._previews.get(key)
            base = hit[1] if hit and time.monotonic() < hit[0] else None
            future = self._preview_flights.get(key)
            owner = base is None and future is None
            if owner:
                future = self._preview_flights[key] = Future()
        if base is None:
            if not owner:
                base = future.result()
            else:
                try:
                    base = self._build_base(decision) if namespace is None else self._build_base(decision, namespace)
                    with self._previews_lock:
                        at = base.expires_at
                        self._previews[key] = (at, base)
                        self._preview_latest[self._context_key(decision, namespace)] = (at, base)
                        for cache in (self._previews, self._preview_latest):
                            while len(cache) > self.PREVIEW_KEEP:
                                cache.pop(next(iter(cache)))
                    future.set_result(base)
                except BaseException as error:
                    future.set_exception(error)
                    raise
                finally:
                    with self._previews_lock:
                        self._preview_flights.pop(key, None)
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
        _, ctxs = self._ctxs_for(base.trip, by_place, home, s.state, results)
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
                           "candidates": [self._lodging_card(c) for c in self._offered_lodging(base, s.state)]},
               "itinerary": self._with_meals(s, active[0]) if active else None,
               "travel_load": active[1] if active else None,
               "day_conditions": [{"day": cx.day.index + 1, "date": cx.day.date.isoformat() if cx.day.date else None,
                                   **(describe(cx.cond) or {})} for cx in base.trip.ctxs if cx.cond],
               "crowd_tips": crowd_tips(list(base.trip.by_place.values()), [cx.cond for cx in base.trip.ctxs], self.cfg),
               "state": s.state.model_dump(mode="json"),
               # the time of day each stop with a choice is held to, and the choices (act set_slot)
               "slots": {pid: {"options": opts, "current": slot_of(self._active_place(s, base, pid), self.cfg)}
                         for pid, opts in self._slot_options(base).items()},
               # after a confirm: whether this version is still the confirmed plan (the trip keeps using that one)
               "confirmed": None if s.confirmed is None else {"edited": s.edited()}}

    def _with_meals(self, s: Session, itin: list[dict]) -> list[dict]:
        """Restaurants to pick from on each free meal block (build.meal_options), and the night block of every day
        followed by a night the trip really sleeps in (build.night_slots)."""
        hard = s.decision["trip_context"].get("hard_filters") or []
        return night_slots(meal_options(itin, self.by_id, hard, self.cfg), self.by_id, hard,
                           s.decision["trip_context"]["context"], self.cfg)

    def _lodging_card(self, c: dict) -> dict:
        """What the "Bạn ở đâu?" screen shows of a candidate (docs/WEB.md §6)."""
        names = self.labels.get("feature") or {}
        return {"id": c["id"], "name": c["name"], "price_vnd": c["price_vnd"], "source": c.get("source"),
                "price_at": c.get("price_at") if c.get("price_source") else None,
                "rating": c.get("rating"), "reviews": c.get("reviews"), "avg_min": c.get("avg_min"),
                "fit": [{k: f[k] for k in ("text", "mentions", "quote")} for f in c.get("fit") or []],
                "unverified": [names.get(f, f.replace("_", " ")).lower() for f in c.get("unverified") or []]}

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
        if p and pid in s.state.slots:      # the user's time of day for this stop wins over the evidence default
            p = replace(p, pins=slot_pins(p, s.state.slots[pid], self.cfg))
        if p:
            timing = {"start": None, "duration_min": None,
                      **s.state.visit_overrides.get(pid, {}), **s.state.locked_visits.get(pid, {})}
            p = replace(p, requested_start=timing["start"], requested_duration=timing["duration_min"])
        return replace(p, relaxed=p.relaxed + tuple(relax_for)) if p and relax_for else p

    def _slot_options(self, base: _Base) -> dict:
        """place id -> the times of day the user may hold it to (build.slot_options); places with no choice left out."""
        out = {pid: slot_options(p, base.trip.ctxs, self.cfg) for pid, p in base.trip.by_place.items()}
        return {pid: o for pid, o in out.items() if o}

    def _dawn_day(self, base: _Base, s2: Session, pid: str, prev_results: list) -> int:
        """The day a stop the user holds to dawn goes on: its own day when that morning is free and can host it, else
        the first free morning that can. One dawn stop a morning; none free -> an ActionError that names who holds
        each morning."""
        by_place = self._places_for(s2, base)
        _, ctxs = self._ctxs_for(base.trip, by_place, self._home_for(s2, base), s2.state)
        day_of = {i: d for d, r in enumerate(prev_results) for i in r.order}
        day_of.update(s2.state.assignment)
        taken = {day_of[q]: p.name for q, p in by_place.items()
                 if q != pid and q in day_of and slot_of(p, self.cfg) == "dawn"}
        if pid not in by_place:
            raise ActionError(f"unknown place {pid!r}")
        mornings = slot_days(by_place[pid], ctxs)
        free = [d for d in mornings if d not in taken]
        if not free:
            held = ", ".join(f"sáng ngày {d + 1} đã có {taken[d]}" for d in mornings if d in taken)
            raise ActionError("no free dawn morning", say=f"Không còn buổi sáng sớm nào trống: {held}. "
                                                          "Bạn đổi một nơi đó sang giờ khác trước nhé.")
        own = day_of.get(pid)
        if own not in free and pid in s2.state.locked:
            raise ActionError("no free dawn morning", say=f"Sáng ngày {own + 1} không còn trống mà nơi này đang khóa vào "
                                                          f"ngày đó. Sáng ngày {free[0] + 1} còn trống: mở khóa để chuyển.")
        return own if own in free else free[0]

    def _places_for(self, s: Session, base: _Base) -> dict:
        """The places this version schedules: not dropped, and a backup only while this version has it added."""
        dropped = {d.place_id for d in s.state.dropped}
        gone = dropped | (base.added - set(s.state.assignment))
        return {pid: self._active_place(s, base, pid) for pid in base.trip.by_place if pid not in gone}

    def _lodging_nodes(self, base: _Base, s: Session) -> dict:
        """Every lodging node a version of the session routes to: the crawled candidates and any point set by hand."""
        return {**{c["id"]: (c["lat"], c["lng"]) for c in base.lodging_candidates},
                **{st.lodging_point["id"]: (st.lodging_point["lat"], st.lodging_point["lng"])
                   for st in s.states if st.lodging_point}}

    def _ensure_added(self, base: _Base, s: Session) -> None:
        """A backup place the user added (add_from_backup, swap) joins the trip before any day is laid out with it:
        its record, its pins and its row of the travel matrix. A no-op once the trip has it."""
        need = {pid for pid in s.state.assignment if pid not in base.trip.by_place} - base.added
        if not need:
            return
        base.added |= need
        base.trip = self._prepare(s.decision, extra_nodes=self._lodging_nodes(base, s), added=base.added)

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
        ctxs = [replace(cx, places=by_place) for cx in ctxs]
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
            # a dawn stop new to the day (moved, or held to dawn by set_slot) opens it early, as schedule_trip does
            ctxs[day] = pull_early(ctxs[day], members[day], ctxs[day].places, ctxs[day].travel)[0]
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
        ctxs = [replace(cx, places=by_place) for cx in ctxs]
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
            m = add_lodging_cost(m, cand["price_vnd"], nights_of(s.decision["trip_context"]["context"]))
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
        for pid in {*new.visit_overrides, *old.visit_overrides, *new.locked_visits, *old.locked_visits}:
            if (new.visit_overrides.get(pid) != old.visit_overrides.get(pid) or
                    new.locked_visits.get(pid) != old.locked_visits.get(pid)):
                days |= {i for i, r in enumerate(prev_results) if pid in r.order}
        for pid in {*new.slots, *old.slots}:
            if new.slots.get(pid) != old.slots.get(pid):
                days |= {i for i, r in enumerate(prev_results) if pid in r.order}
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

    def _locate_lodging(self, text: str, lat, lng) -> dict | None:
        """Where the user's lodging is: the point they picked from the suggestions; else our own lodging lists and
        places by name (lodging_lookup, no network); else geocoding the text. None when nothing knows it."""
        if lat is not None or lng is not None:
            ok = all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (lat, lng))
            if not ok or not (-90 <= lat <= 90 and -180 <= lng <= 180):
                raise ActionError("set_lodging lat / lng must be coordinates")
            return {"lat": float(lat), "lng": float(lng), "source": "user", "fetched_at": None}
        hit = self.lodging_lookup(text) if self.lodging_lookup else None
        if hit is None:
            try:
                hit = self.geocode_fn(text) if self.geocode_fn else live.geocode(text, self.live_cfg)
            except live.Unavailable:
                hit = None
        return hit

    def _ensure_lodging_node(self, base: _Base, decision: dict, point: dict) -> None:
        """set_lodging's manual point must be in the matrix before with_home() can route a day to / from it; a
        no-op once it already is (replay calls this once per logged set_lodging, live calls it once live)."""
        if point["id"] in base.trip.travel.index:
            return
        base.trip = self._prepare(decision, extra_nodes={
            **{c["id"]: (c["lat"], c["lng"]) for c in base.lodging_candidates}, point["id"]: (point["lat"], point["lng"])},
            added=base.added)

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
            base.trip = self._prepare(s.decision, extra_nodes=self._lodging_nodes(base, s), added=base.added)

    def _compute_results(self, base: _Base, s2: Session, old_state: State, prev_results: list, action: dict) -> list:
        """The scope dispatch a committing act lays its results out with -- used both by act() for the newest act
        and by _ensure_base()'s replay for every earlier one, so a rebuilt session lays out identically to how it
        did live. s2: a Session view whose .state is already the state right after `action`. Side effects
        structurally required for with_home() (joining a manual lodging point to the matrix) are replayed too;
        forward-looking validation (e.g. pick_lodging's still-offered check) is not -- the action already passed
        it once, when it was first performed."""
        t = action.get("type")
        self._ensure_added(base, s2)
        if t == "recommend":
            return self._proposal_trial(base, s2, old_state, prev_results, action["proposal"])[1]
        if t == "set_lodging" and action.get("_point"):
            self._ensure_lodging_node(base, s2.decision, action["_point"])
        if t == "pick_variant":
            # NONE scope (no relayout), but prev_results is meaningless here (it belongs to whatever was active
            # before this pick, if anything) -- the newly chosen variant's own pristine schedule is what's active.
            seed = next(v["_results"] for v in base.variants if v["id"] == s2.state.chosen_variant)
            if s2.state.visit_overrides or s2.state.locked_visits:
                return self._relayout(base, s2, seed, set(range(len(seed))))[0]
            return seed
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

    def _check_fixed_visits(self, base: _Base, session: Session, results: list) -> None:
        fixed = set(session.state.visit_overrides) | set(session.state.locked_visits)
        fixed -= {drop.place_id for drop in session.state.dropped}
        if not fixed:
            return
        from .validate import validate
        by_place = self._places_for(session, base)
        _, ctxs = self._ctxs_for(base.trip, by_place, self._home_for(session, base), session.state, results)
        violations = validate(ctxs, results, [], set(), None, None, required_visits=fixed)
        visited = {item.place_id for result in results for item in result.items if item.kind == "visit"}
        fixed_days = {d for d, result in enumerate(results) if fixed & set(result.order)}
        failures = [v for v in violations if v.place_id in fixed or v.day in fixed_days]
        if failures or fixed - visited:
            pid = next(iter(fixed - visited), None) or next((v.place_id for v in failures if v.place_id in fixed), None)
            name = by_place[pid].name if pid in by_place else "nơi đã chỉnh giờ"
            raise ActionError("fixed visit conflicts with schedule",
                              say=f"Không giữ được giờ hoặc thời lượng của {name}: giờ mở cửa, thời gian di chuyển "
                                  "hoặc khung ngày không đủ. Bạn đổi giờ, giảm thời lượng hoặc mở khóa trước nhé.")

    # ---------- act / undo / redo ----------

    def act(self, sid: str, action: dict) -> dict:
        s = self._get(sid)
        base = self._ensure_base(sid)
        with self.store.lock(sid):
            t = action.get("type")
            if t in ("undo", "redo"):
                if t == "undo" and s.position == 0:
                    raise ActionError("nothing to undo")
                if t == "redo" and s.position + 1 >= len(s.states):
                    raise ActionError("nothing to redo")
                previous = self._schedules[sid][s.position] or []
                s.position += -1 if t == "undo" else 1
                current = self._schedules[sid][s.position] or []
                changed_days = [day + 1 for day in range(max(len(previous), len(current)))
                                if day >= len(previous) or day >= len(current) or previous[day] != current[day]]
                self.store.save(s)
                return {"view": self._view(s), "diff": {"scope": "none", "changed_days": changed_days}}

            if s.state.chosen_variant is None and t != "pick_variant":
                raise ActionError("pick a variant before editing the plan")
            prev_results = self._schedules.get(sid, [None])[s.position] or \
                (next(v["_results"] for v in base.variants if v["id"] == s.state.chosen_variant)
                if s.state.chosen_variant else [])
            ctx = ActCtx(by_place=base.trip.by_place, n_days=len(base.trip.days),
                        variant_ids={v["id"] for v in base.variants},
                        backup_ids={b["id"]: b for b in s.decision.get("backup_pool") or []},
                        day_members=[list(r.order) for r in prev_results] if prev_results else [],
                        objective_names=set(LABEL), valid_paces=set(self.cfg.per_day),
                        slot_options=self._slot_options(base),
                        actual_visits={i.place_id: {"start": i.start, "duration_min": i.end - i.start}
                                       for r in prev_results for i in r.items if i.kind == "visit"})
            if t == "pick_lodging":
                if action.get("id") not in {c["id"] for c in self._offered_lodging(base, s.state)}:
                    raise ActionError(f"unknown or no-longer-offered lodging {action.get('id')!r}")
            elif t == "set_lodging":
                text = (action.get("text") or "").strip()
                if not text:
                    raise ActionError("set_lodging needs non-empty text")
                hit = self._locate_lodging(text, action.get("lat"), action.get("lng"))
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
            if t == "set_slot" and new_state.slots[action["place_id"]] == "dawn":
                day = self._dawn_day(base, s2, action["place_id"], prev_results)
                if day != next((d for d, r in enumerate(prev_results) if action["place_id"] in r.order), None):
                    new_state.assignment[action["place_id"]] = day
            if t in ("add_from_backup", "swap"):
                self._ensure_added(base, s2)
                if not set(new_state.assignment) <= set(base.trip.by_place):
                    raise ActionError("the backup place has no record, point or visit time to schedule")
            results = self._compute_results(base, s2, s.state, prev_results, action)
            # Clock locks capture an existing timeline without changing it; confirm still checks its validity.
            if t not in ("lock_slot", "unlock"):
                self._check_fixed_visits(base, s2, results)

            s.states = s.states[: s.position + 1] + [new_state]
            s.position += 1
            self._schedules.setdefault(sid, [None] * len(s.states))
            while len(self._schedules[sid]) < len(s.states):
                self._schedules[sid].append(None)
            self._schedules[sid] = self._schedules[sid][: len(s.states)]
            self._schedules[sid][s.position] = results
            s.log = s.log[: s.position - 1] + [{"action": action, "at": _now()}]
            self.store.save(s)
            changed_days = [d + 1 for d, r in enumerate(results)
                            if d >= len(prev_results) or r != prev_results[d]]
            return {"view": self._view(s), "diff": {"scope": act_scope(action), "changed_days": changed_days}}

    # ---------- internal recommendation ----------

    def _proposal_trial(self, base, session, state, previous, proposal):
        trial = session.model_copy(deep=True)
        trial.states = [state.model_copy(deep=True)]
        trial.position = 0
        ctx = ActCtx(base.trip.by_place, len(base.trip.days), {v['id'] for v in base.variants},
                     {}, [list(r.order) for r in previous], set(LABEL), set(self.cfg.per_day))
        trial.states[0] = _apply(trial.state, {'type': 'pick_variant', 'id': proposal['variant_id']}, ctx)
        # Rebuild for the chosen objective with the user's pace, day windows, home and edits.
        results, _ = self._rebuild_variant(base, trial)
        for action in proposal.get('acts', []):
            ctx = replace(ctx, day_members=[list(r.order) for r in results],
                          actual_visits={i.place_id: {"start": i.start, "duration_min": i.end - i.start}
                                         for r in results for i in r.items if i.kind == "visit"})
            old = trial.state
            trial.states[0] = _apply(old, action, ctx)
            results = self._compute_results(base, trial, old, results, action)
        self._check_fixed_visits(base, trial, results)
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
            snapshot = {'session': session.model_dump(mode='json'), 'view': view}
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
                current = {'session': session.model_dump(mode='json'), 'view': self._view(session)}
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
                self.store.save(committed)
                session.states, session.log, session.position = committed.states, committed.log, committed.position
                self._schedules[sid] = self._schedules.get(sid, [None] * session.position)[:session.position] + [results]
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
                                  (tc.get("pace") or {}).get("max_leg_min"),
                                  required_visits={pid for pid, p in by_place.items()
                                                   if p.requested_start is not None or p.requested_duration is not None})
            if violations:
                raise NotConfirmable("plan has unresolved violations")
            variant = self._variant_dict(base, s, results, ctxs)
            variant["itinerary"] = self._with_meals(s, variant["itinerary"])
            coords = {**{p.id: (p.lat, p.lng) for p in trip.by_place.values()},
                     **{n: (pt.lat, pt.lng) for n, pt in trip.points.items() if pt},
                     **{c["id"]: (c["lat"], c["lng"]) for c in base.lodging_candidates}}
            from .output import build as build_output
            out = build_output(trip, base.variants, variant, results, s.decision, coords, self.live_cfg,
                               route_fn=self.route_fn)
            s.output, s.confirmed = out, plan_key(s.state)
            self.store.save(s)
            return out

    def baseline_travel_min(self, sid: str) -> int:
        """Total travel minutes of the chosen variant's own day membership, laid out by plain nearest-neighbour
        from base/entry (docs/P4_PLANNING.md §Đo: "baseline = nearest-neighbour + anchor base, không chọn
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

    # ---------- turn (docs/P4_PLANNING.md §Vòng người dùng sửa và góp ý) ----------

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
