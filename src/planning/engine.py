"""Planning sessions for the web (docs/PLANNING.md §API và web): create (fast, anchor = base), act (chips,
no model), variants, lodging (crawled in the background), confirm. One lock per session; each committing act is one
version that undo / redo moves between.
"""

import asyncio
import copy
import hashlib
import json
import secrets
import threading
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import asdict, replace
from datetime import datetime, timezone
from itertools import combinations
from json import loads
from typing import Awaitable, Callable

import live
from corpus.ontology import load as load_ontology
from corpus.retrieval import RetrievalEngine
from corpus.releases import Binding
from corpus.serving import feature
from trip import nights

from .build import chunk_view, prepare, pull_early, schedule_trip, window_override, with_home
from .lodging import candidates as lodging_candidates
from .lodging import anywhere as lodging_anywhere
from .lodging import booked, from_record, phrase, rank, sieve, with_booked_base
from .places import build_places
from .ghosts import fill as fill_ghosts
from .ghosts import pool as ghost_pool
from .model import Point
from .objectives import LABEL, add_lodging_cost, metrics, score
from .overload import LABEL as CARD_LABEL, render_variant
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
from .travel import km
from .settings import load as load_settings
from .cache import day_key, fingerprint, put, travel_key
from .variants import plan_cards

def _referenced(value, out: set) -> set:
    """Every "id" / "place_id" string anywhere in a Decision Output: the records a session built from it reads."""
    if isinstance(value, dict):
        for k, v in value.items():
            if k in ("id", "place_id") and isinstance(v, str):
                out.add(v)
            else:
                _referenced(v, out)
    elif isinstance(value, list):
        for v in value:
            _referenced(v, out)
    return out


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


class TripIncomplete(Exception):
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(", ".join(missing))


def _nights(ctx: dict) -> int:
    return nights(ctx)  # the user's own number ("3 ngày 3 đêm" sleeps 3), else days - 1


# Spec §8: edits that insert where it costs least (or drop) and retime the days they touch, no reordering search.
QUICK_EDITS = frozenset({"move_place", "add_from_backup", "drop_place"})


class _Base:
    """What create() computes once (no lodging yet) and the lodging crawl later fills in -- held in RAM, keyed by
    session id. Never persisted: a restart rebuilds it from Session.decision + states + log (Engine._ensure_base)."""

    def __init__(self, trip, variants: list[dict], comparison: list[dict], ok: bool, warnings: list,
                back_to_decision: dict | None):
        self.trip = trip
        self.variants = variants          # one main card, or the overload direction cards
        self.comparison = comparison
        self.ok = ok
        self.warnings = warnings
        self.back_to_decision = back_to_decision
        self.overload: dict | None = None  # overload.py's card (spec section 7), None when every pick fits
        self.leftover: tuple = ()         # selected places no day had room for (Schedule.leftover)
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
        self.offers: dict = {}
        self.manual_points: dict = {}
        self.pool = None                  # ghosts.Pool: where faded suggestions come from (spec §6), per lodging
        self.pool_home: str | None = None  # the lodging node base.pool was built around
        self.ghost_nodes: dict = {}       # accepted suggestion id -> (lat, lng), joined to the travel matrix
        self.ghosts: dict = {}            # (day layout, lodging, dismissed) -> view["ghosts"]
        self.better: dict = {}            # (day context, user order) -> better_order entry or None (spec §8)
        self.generation = time.monotonic_ns()

# Lodging cards: a stay feature that is never shown as a plus, and the values that read as one.
NOT_A_STRENGTH = frozenset({"steep_or_stairs", "cold"})
STRONG_VALUES = ("present", "suitable", "good", "included")


class Engine:
    def __init__(self, records: list[dict], cfg: Settings | None = None, live_cfg=None, store: Store | None = None,
                geocode_fn=None, matrix_fn=None, sun_fn=None, route_fn=None,
                decision_url: str | None = None, http_post=None, background: bool = True,
                agent: "Agent | None" = None, proposal_agent=None, conditions_fn=None, labels: dict | None = None,
                card_cfg: dict | None = None, live_dependency_version=None,
                immutable_records_version: str | None = None, retrieval: RetrievalEngine | None = None):
        self.by_id = {r["id"]: r for r in records}
        self.records = records
        self.cfg = cfg or load_settings()
        self.live_cfg = live_cfg or live.load_settings()
        self.store = store or Store(None)
        self.geocode_fn = geocode_fn
        self.matrix_fn = matrix_fn
        self.sun_fn = sun_fn
        self.route_fn = route_fn or live.route_shape
        self.decision_url = decision_url or self.cfg.decision_url
        self.http_post = http_post or _http_post
        self.background = background
        self.agent = agent
        self.proposal_agent = proposal_agent
        self.retrieval = retrieval
        self.conditions_fn = conditions_fn      # (decision, by_id) -> (weather, signals); None = no live conditions
        self.labels = labels or {}              # Place Decision's feature / value words, for "hợp vì" (tools.py)
        self._ont = None
        self.card_cfg = card_cfg or {}          # Place Decision's polarity, center, near_min, speed_kmh, road_factor: lodging cards
        # Callers can advance this token when callback data changes; otherwise live reuse is TTL bounded.
        self.live_dependency_version = live_dependency_version
        # Only verified immutable release factories may supply a records version.
        self.immutable_records_version = immutable_records_version
        self._base: dict[str, _Base] = {}
        self._schedules: dict[str, list] = {}
        self._previews: dict[str, tuple[float, _Base]] = {}   # Decision Output hash -> (built at, base)
        self._previews_lock = threading.Lock()
        self._epochs: dict[str, int] = {}
        self._preview_tokens: dict[str, tuple[dict, float]] = {}
        self._lodging_options: dict[str, tuple[float, dict]] = {}   # places + trip context hash -> (built at, list)
        self.timings: dict[str, dict] = {}
        self._key_cfg = self.cfg
        self._cfg_fingerprint = fingerprint(self.cfg)
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

    def _check_lodging(self, decision: dict, point: dict | None = None) -> None:
        if point is None:
            own = decision.get("lodging") or (decision["trip_context"]["context"].get("lodging")
                  if decision["trip_context"]["context"].get("lodging_booked") == "yes" else None)
            if own and own.get("kind") == "corpus" and not (own.get("id") or own.get("place_id")):
                raise ActionError("corpus lodging identity is missing")
            point = booked(decision)
        if not point or not point.get("place_id"):
            return
        record = self.by_id.get(point["place_id"])
        if record is None or record["identity"].get("category_group") != "stay":
            raise ActionError("corpus lodging is unavailable")
        if not sieve([from_record(record)], decision["trip_context"].get("hard_filters") or [], min_reviews=0):
            raise ActionError("lodging fails hard requirements")

    def _prepare(self, decision: dict, extra_nodes: dict | None = None):
        self._check_lodging(decision)
        decision = with_booked_base(decision)  # a booked lodging is where every day starts and ends
        weather, signals = self.conditions_fn(decision, self.by_id) if self.conditions_fn else (None, None)
        return prepare(decision, self.records, self.cfg, self.live_cfg, self.geocode_fn, self.matrix_fn, self.sun_fn,
                       weather, extra_nodes=extra_nodes, signals=signals)

    def _build_base(self, decision: dict) -> _Base:
        """One main plan, or the overload directions (overload.py via variants.plan_cards); never a variant per
        objective. base.leftover is the main plan's own leftover: what no day had room for before any direction."""
        trip = self._prepare(decision)
        out = plan_cards(trip)
        base = _Base(trip, out["variants"], out["comparison"], out["ok"], list(trip.warnings) + out["warnings"],
                     out["back_to_decision"])
        base.overload, base.leftover = out["overload"], tuple(out["leftover"])
        return base

    def _crawl_lodging(self, sid: str) -> None:
        """Runs on a background thread (create()'s background=True) or synchronously (background=False, tests, and
        _ensure_base's lazy rebuild). The candidates are the served stays (lodging.candidates); any failure degrades
        to "unavailable" rather than leaving the session stuck at "pending". The write-back happens under the
        session's own lock and merges in whatever lodging point the user may have set meanwhile, so a concurrent
        set_lodging is never lost. The pool is ranked once the travel matrix reaches it (taste first, location
        after: lodging.rank)."""
        base = self._base[sid]
        decision = self.store.get(sid).decision
        if booked(decision):
            base.lodging_status = "booked"  # the user has a lodging: nothing to suggest
            return
        try:
            cands = lodging_candidates(base.trip.by_place, decision, self.cfg, self.records)
        except Exception:
            cands = []
        with self.store.lock(sid):
            extra = {**{c["id"]: (c["lat"], c["lng"]) for c in cands},
                     **{pid: (p['lat'], p['lng']) for pid, p in base.manual_points.items()}, **base.ghost_nodes}
            point = self.store.get(sid).state.lodging_point
            if point:
                extra[point["id"]] = (point["lat"], point["lng"])
            if extra:
                base.trip = self._prepare(decision, extra_nodes=extra)
            cands = rank(cands, decision, self._avg_min(base.trip, cands), self.cfg, self.labels)
            base.lodging_candidates = cands
            base.lodging_status = "ready" if cands else "unavailable"

    @staticmethod
    def _avg_min(trip, cands: list[dict]) -> dict:
        """Candidate id -> mean minutes to the trip's places on the travel matrix (None off the matrix)."""
        ids = [p for p in trip.by_place if p in trip.travel.index]
        return {c["id"]: sum(trip.travel.leg(c["id"], p)[0] for p in ids) / len(ids)
                if ids and c["id"] in trip.travel.index else None for c in cands}

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
                prev_results = self._card_results(base, old_state.chosen_variant)
            action = s.log[k - 1]["action"]
            s_view = s.model_copy(update={"states": s.states[: k + 1], "position": k})
            results[k] = self._compute_results(base, s_view, old_state, prev_results, action)
        self._schedules[sid] = results
        return base

    # ---------- API ----------

    def create(self, decision: dict | None = None, decision_session_id: str | None = None, *, require_lodging: bool = False) -> dict:
        decision = self._resolve(decision, decision_session_id)
        readiness = (decision.get("trip_context") or {}).get("readiness")
        if readiness is not None:
            missing = list(readiness.get("missing") or ())
            if readiness.get("readback_ok") is not True:
                missing.append("readback")
            if missing:
                raise TripIncomplete(missing)
        self._check_lodging(decision)
        s = self.store.new(decision, decision_session_id)
        s.require_lodging = require_lodging
        if point := booked(decision):  # as if set_lodging had run: the user's own lodging, from the start
            s.states[0] = State(lodging_touched=True, lodging_id=point["id"], lodging_point=point)
        base = self._take_preview(decision) or self._build_base(decision)
        self._base[s.id] = base
        if base.overload is None and base.variants:
            # Spec section 7: a trip whose days hold every pick opens on its one main plan, nothing to choose.
            s.states[0] = s.states[0].model_copy(update={"chosen_variant": base.variants[0]["id"]})
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

    def _decision_key(self, decision: dict, all_records: bool = False) -> str:
        """The preview cache key: the decision's meaning and everything a base built from it depends on. Mutable
        records count by the ones the decision names (its places, pool, lodging, base / entry / exit): hashing the
        whole corpus cost ~0.8 s a create; all_records: the caller reads every record (the lodging list)."""
        semantic = {k: v for k, v in decision.items() if k not in {"decision_log", "wishlist", "feasibility"}}
        feasibility = decision.get("feasibility") or {}
        totals = feasibility.get("totals") or {}
        semantic["composition_inputs"] = {
            "available": totals.get("available"), "needed": totals.get("needed"),
            "binding": sorted({c["check"] for c in feasibility.get("conflicts") or []
                               if c.get("check") in {"time", "per_day", "far_areas", "time_windows", "budget"}})}
        live_settings = {name: getattr(self.live_cfg, name) for name in dir(self.live_cfg)
                         if not name.startswith("_") and not callable(getattr(self.live_cfg, name))}
        record_dependency = ("immutable", self.immutable_records_version) if self.immutable_records_version is not None \
            else ("mutable", self.records) if all_records \
            else ("mutable", [self.by_id.get(pid) for pid in sorted(_referenced(decision, set()))])
        if self.cfg is not self._key_cfg:
            self._key_cfg, self._cfg_fingerprint = self.cfg, fingerprint(self.cfg)
        return fingerprint((semantic, self._cfg_fingerprint, live_settings, record_dependency, self.labels, self.card_cfg,
                            self.live_dependency_version,
                            tuple(id(fn) for fn in (self.geocode_fn, self.matrix_fn, self.sun_fn, self.conditions_fn))))

    def _take_preview(self, decision: dict) -> "_Base | None":
        """A base an earlier preview() built for exactly this Decision Output; create() owns it from here on."""
        with self._previews_lock:
            hit = self._previews.pop(self._decision_key(decision), None)
        if hit and time.monotonic() - hit[0] < self.PREVIEW_TTL_S:
            hit[1].trip.decision = with_booked_base(decision)
            return hit[1]
        return None

    def preview(self, decision: dict) -> dict:
        """Variants for a Decision Output not confirmed yet: what the schedule would look like now. Creates no
        session and writes nothing; the base is cached by the output's hash so create() for it skips the build."""
        self._check_lodging(decision)
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

    def lodging_options(self, decision: dict, offset: int = 0, limit: int | None = None) -> dict:
        """The lodging list Lựa chọn shows for a Decision Output not confirmed yet: every served stay that passes the
        hard filters and the price cap, one page at a time. First the stays around the chosen places, ranked as a
        session would rank them (taste first, location after, with avg_min); then all the others by taste and rating.
        With no place chosen yet the whole list is taste and rating (no avg_min). Creates no session.
        {"status": "ready" | "unavailable", "candidates": [card], "total": int}; limit: page size (lodging_list_k).
        A trip that already has its lodging gets the list too: it may change it."""
        key = self._decision_key({"places": sorted(c["id"] for c in decision["confirmed"]),
                                  "trip": decision["trip_context"]}, all_records=True)
        with self._previews_lock:
            hit = self._lodging_options.get(key)
        if hit and time.monotonic() - hit[0] < self.PREVIEW_TTL_S:
            ranked = hit[1]
        else:
            placed, _ = build_places(decision, self.by_id, self.cfg)
            near = lodging_candidates({p.id: p for p in placed}, decision, self.cfg, self.records) if placed else []
            if near:
                # Replacement browsing must not depend on the current lodging passing new requirements.
                context = {**decision["trip_context"]["context"], "lodging": None, "lodging_booked": "no"}
                browsing = {**decision, "lodging": None,
                            "trip_context": {**decision["trip_context"], "context": context}}
                trip = self._prepare(browsing, extra_nodes={c["id"]: (c["lat"], c["lng"]) for c in near})
                near = rank(near, decision, self._avg_min(trip, near), self.cfg, self.labels, self.cfg.lodging_list_k)
            taken = {c["id"] for c in near}
            rest = [c for c in lodging_anywhere(decision, self.cfg, self.records, limit=None) if c["id"] not in taken]
            rest = rank(rest, decision, {}, self.cfg, self.labels, len(rest)) if rest else []
            ranked = near + rest  # the cards are built per page below: ~1500 stays, the user sees 18 at a time
            with self._previews_lock:
                self._lodging_options[key] = (time.monotonic(), ranked)
                while len(self._lodging_options) > self.PREVIEW_KEEP:
                    self._lodging_options.pop(next(iter(self._lodging_options)))
        size = limit or self.cfg.lodging_list_k
        return {"status": "ready" if ranked else "unavailable",
                "candidates": [self._lodging_card(c, decision) for c in ranked[offset:offset + size]],
                "total": len(ranked)}

    def _get(self, sid: str) -> Session:
        try:
            return self.store.get(sid)
        except KeyError:
            raise NoSession(sid) from None

    def _offered_lodging(self, base: _Base, state: State) -> list[dict]:
        """Every candidate still within the session's current price cap -- state.budget_override narrows what is
        *offered*, it never discards what was actually found (undo must be able to bring a candidate back, and the
        chosen one must stay resolvable even if it falls outside a later-lowered cap)."""
        cap = state.budget_override
        if cap is None:
            return list(base.lodging_candidates)
        return [c for c in base.lodging_candidates if c["price_vnd"] is None or c["price_vnd"] <= cap]

    def _active_itinerary(self, s: Session, base: _Base, results=None) -> dict | None:
        """The itinerary / travel_load of the session's currently chosen variant, with every committed act applied
        -- None before a variant is chosen, since there is nothing laid out yet to show."""
        if s.state.chosen_variant is None:
            return None
        if results is None:
            results = self._schedules.get(s.id, [None] * len(s.states))[s.position]
        if results is None:
            results = self._card_results(base, s.state.chosen_variant)
        by_place = self._places_for(s, base)
        home = self._home_for(s, base)
        _, ctxs = self._ctxs_for(base.trip, by_place, home, s.state, results)
        from .build import itinerary as render_itinerary
        from .build import travel_load as render_travel_load
        from .validate import validate
        tc = s.decision["trip_context"]
        keys = [fingerprint((day_key(cx, result.order), result)) for cx, result in zip(ctxs, results)]
        cand = next((c for c in base.lodging_candidates if c["id"] == home), None)
        if cand is None and home and s.state.lodging_point:
            cand = {"id": home, "name": s.state.lodging_point.get("text"),
                    "price_vnd": s.state.lodging_point.get("price_vnd")}
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
        """Background work after a layout (spec §8 "Tính nền"): the suggestions and the better_order hints of the
        days the user reordered. Both are ready when the suggestions token turns ready."""
        base = self._ensure_base(s.id)
        active = active if active is not None else self._active_itinerary(s, base)
        if not active:
            return
        key = active["context_key"]
        jobs = [job for job in self._better_jobs(s, active) if job[0] not in base.better]
        if key in base.pending or (key in base.suggestions and not jobs):
            return
        if self.background and not self._suggestion_slots.acquire(blocking=False):
            return
        background = self.background
        suggest = key not in base.suggestions
        base.pending.add(key)
        pool_records = {p["id"]: self.by_id[p["id"]] for p in s.decision.get("backup_pool") or [] if p["id"] in self.by_id}
        try:
            # recommend() only reads the days (it lays trials out on replaced copies); copying the days' contexts
            # (places, travel matrix) cost ~0.2 s a call, so only the session's own decision is copied.
            ctxs, results = list(active["ctxs"]), list(active["results"])
            decision, by_id = copy.deepcopy(s.decision), dict(pool_records)
        except Exception:
            base.pending.discard(key)
            if background:
                self._suggestion_slots.release()
            put(base.suggestions, key, {"status": "unavailable", "items": []}, self.cfg.cache_entries)
            return
        def work():
            started = time.perf_counter()
            hints = {}
            try:
                for job_key, order, cx, mine, _ in jobs:
                    try:
                        hints[job_key] = self._best_order(order, cx, mine)
                    except Exception:
                        hints[job_key] = None       # no hint is the safe answer: the user's order stays either way
                result = {"status": "ready", "items": recommend(ctxs, results, decision, by_id)} if suggest else None
            except Exception:
                result = {"status": "unavailable", "items": []}
            finally:
                if background:
                    self._suggestion_slots.release()
            with self.store.lock(s.id):
                base.pending.discard(key)
                if self._base.get(s.id) is base:
                    for job_key, hint in hints.items():
                        put(base.better, job_key, hint, self.cfg.cache_entries)
                    if result is not None:
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
            active = self._active_itinerary(s, base)
            # the better_order hints are worked out with the suggestions (spec §8): the poll carries them too
            return {**self._suggestions(s, base, active), "better_order": self._better_order(s, base, active)}

    def routes(self, sid: str) -> dict:
        """The drawn path of each day of the active itinerary (OSRM /route), read on its own so the view stays fast.
        A day with fewer than two known points or no routing source has route None: the map then draws no line."""
        from .output import route_of_day
        with self.store.lock(sid):
            s = self._get(sid)
            base = self._ensure_base(sid)
            active = self._active_itinerary(s, base)
            if not active:
                return {"days": []}
            by_place = self._places_for(s, base)
            home = self._home_for(s, base)
            trip, _ = self._ctxs_for(base.trip, by_place, home, s.state, active["results"])
            coords = {**{p.id: (p.lat, p.lng) for p in by_place.values()},
                      **{n: (pt.lat, pt.lng) for n, pt in trip.points.items() if pt},
                      **{c["id"]: (c["lat"], c["lng"]) for c in base.lodging_candidates}}
            if s.state.lodging_point and home:
                coords[home] = (s.state.lodging_point["lat"], s.state.lodging_point["lng"])
            mobility = s.decision["trip_context"]["context"].get("mobility")
            names = {**{p.id: p.name for p in by_place.values()}, **{c["id"]: c["name"] for c in base.lodging_candidates}}
            if s.state.lodging_point and home:
                names[home] = s.state.lodging_point.get("text") or names.get(home)

            def end(node):
                return {"id": node, "name": names.get(node) if node else None, "home": bool(node) and node == home}

            days = [{"day": cx.day.index + 1, "start": end(cx.day.start_node), "end": end(cx.day.end_node),
                     "route": route_of_day(cx.day, result, coords, self.live_cfg, mobility, self.route_fn)}
                    for cx, result in zip(active["ctxs"], active["results"])]
        return {"days": days}

    def _view(self, s: Session, results=None, active=None) -> dict:
        base = self._ensure_base(s.id)
        active = active if active is not None else self._active_itinerary(s, base, results)
        suggestions = self._suggestions(s, base, active)
        active_variant = None
        if active and s.state.chosen_variant:
            active_variant = {k: v for k, v in self._variant_dict(base, s, active["results"], active["ctxs"]).items()
                              if not k.startswith("_")}
        offered = self._offered_variants(s, base, active)
        choice = self._choice_metadata(s, base)
        best_travel = min((v['metrics']['travel_min'] for v in offered), default=0)
        comparison = [{'variant': v['id'], 'objective': v['objective'], 'label': v['label'], **v['metrics'],
                       'travel_vs_best': v['metrics']['travel_min'] - best_travel,
                       'robustness': v['robustness']['level']} for v in offered]
        needs_hotel = s.require_lodging and not (s.state.lodging_touched and s.state.lodging_id)
        if active_variant:
            active_variant['recommendations'] = suggestions['items']
        ghosts = self._ghosts(s, base, active) if active else []
        from .build import pin_warnings
        warnings = [w for w in base.warnings if w.get("code") != "pin_dropped"]
        if active:
            warnings.extend(pin_warnings(active["ctxs"], active["results"]))
        return {"ok": choice["ok"], "variants": [{k: v for k, v in v.items() if not k.startswith("_")} for v in offered],
               "needs_hotel": needs_hotel,
               "overload": choice["overload"],
               "keep_all": None,
               "unplaced": self._unplaced(s, base, active, choice),
               "ghosts": ghosts,
               "better_order": self._better_order(s, base, active),
               "active_variant": active_variant,
               **chunk_view(active["itinerary"] if active else [], base.trip.cfg.chunk_days),
               "comparison": comparison, "warnings": warnings, "back_to_decision": choice["back_to_decision"],
               "lodging": {"status": base.lodging_status,
                           "candidates": [self._lodging_card(c, s.decision) for c in self._offered_lodging(base, s.state)]},
               "itinerary": active["itinerary"] if active else None, "travel_load": active["travel_load"] if active else None,
               "metrics": active_variant["metrics"] if active_variant else None, "violations": active["violations"] if active else [],
               "backups": active["backups"] if active else None, "robustness": active["robustness"] if active else None,
               "time_suitability": active["time_suitability"] if active else None,
               "recommendations": suggestions["items"], "suggestions": suggestions,
               "day_conditions": [{"day": cx.day.index + 1, "date": cx.day.date.isoformat() if cx.day.date else None,
                                   **(describe(cx.cond) or {})} for cx in base.trip.ctxs if cx.cond],
               "crowd_tips": crowd_tips(list(self._places_for(s, base).values()), [cx.cond for cx in base.trip.ctxs], self.cfg),
               "duration_range": [self.cfg.duration_profiles["manual_min"], self.cfg.duration_profiles["manual_max"]],
               "state": s.state.model_dump(mode="json")}

    def _better_jobs(self, s: Session, active: dict) -> list[tuple]:
        """(cache key, user order, day context, user's day result, day) of each day that still holds the user's own order
        and has not been told keep_my_order."""
        out = []
        results, ctxs = active["results"], active["ctxs"]
        for day in sorted(s.state.order_override):
            order = list(s.state.order_override[day])
            if day in s.state.keep_order_days or day >= len(results) or len(order) < 2:
                continue
            mine = results[day]
            if list(mine.order) != order:
                continue                    # the day no longer holds the user's order (membership changed since)
            out.append((fingerprint((day_key(ctxs[day], order), order, mine)), order, ctxs[day], mine, day))
        return out

    def _better_order(self, s: Session, base: _Base, active: dict | None) -> list[dict]:
        """Spec §8 "Sau reorder": for each day the user put in their own order, the best order of the same places,
        offered only when it saves at least realistic.better_order_min minutes on the road or clears a problem the
        user's order has (closed, missed meal, late for the end of the day, a time of day given up). Never applied:
        the user's order stays and its problems stay flagged on their rows (view["violations"], items); keep_my_order
        (day) hides the hint. Worked out in the background with the suggestions (_queue_suggestions); a session
        without background work (tests, CLI) works it out here."""
        if not active:
            return []
        out = []
        for key, order, cx, mine, day in self._better_jobs(s, active):
            if key not in base.better and not self.background:
                put(base.better, key, self._best_order(order, cx, mine), self.cfg.cache_entries)
            hint = base.better.get(key)
            if hint:
                out.append({"day": day, **hint})
        return out

    def _best_order(self, order: list, cx, mine) -> dict | None:
        """The hint for one day, or None. The search holds every time of day it can: first all of them, then giving up
        one the user's order gave up, then all those; the first order that brings no problem the user's order does
        not have is the candidate. A time of day the candidate keeps and the user's order gave up is a fix
        ("time_of_day", kept_times)."""
        from .route import order_day
        from .validate import release
        given_up = tuple(mine.unpinned)
        trials = [()] + [(p,) for p in given_up if len(given_up) > 1] + ([given_up] if given_up else [])
        had = {v.kind for v in mine.violations}
        for ids in trials:
            best = order_day(list(order), release(cx, ids), seed=list(order))
            has = {v.kind for v in best.violations}
            if not has <= had or len(best.violations) > len(mine.violations):
                continue
            if list(best.order) == list(order):
                return None             # the user's order is already the best one that holds this much
            kept = [p for p in given_up if p not in ids]
            fixes = sorted(had - has) + (["time_of_day"] if kept else [])
            saved = mine.travel_min - best.travel_min
            if saved >= self.cfg.realistic["better_order_min"] or fixes:
                return {"order": list(best.order), "saved_min": int(saved), "fixes": fixes, "kept_times": kept}
            return None
        return None

    @staticmethod
    def _card_results(base: _Base, vid: str | None) -> list:
        return next((v["_results"] for v in base.variants if v["id"] == vid), [])

    def _unplaced(self, s: Session, base: _Base, active, choice=None) -> list[dict]:
        """The chosen direction's drops, or the original leftover for an unavailable/unpicked card, plus data gaps.
        After edits, include newly unplaced picks and exclude both visits and explicit user drops."""
        choice = choice or {}
        cards = (choice.get("overload") or {}).get("directions", base.variants)
        chosen = next((v for v in cards if v["id"] == s.state.chosen_variant), None)
        dropped = chosen["dropped"] if chosen and chosen["available"] else [
            {"place_id": pid, "name": base.trip.by_place[pid].name, "reason": "no_room"} for pid in choice.get("leftover", base.leftover)]
        tray = {d["place_id"]: {"place_id": d["place_id"], "name": d["name"],
                                "reason": chosen["id"] if chosen and chosen["available"] else "no_room",
                                **({"reason_text": d["reason"]} if chosen and chosen["available"] else {})}
                for d in dropped}
        if active:
            shown = {pid for r in active["results"] for pid in r.order}
            missing = (set(self._places_for(s, base)) | set(s.state.plan_dropped)) - shown
            for pid in missing:
                tray.setdefault(pid, {"place_id": pid, "name": base.trip.by_place[pid].name
                                      if pid in base.trip.by_place else pid, "reason": "no_room"})
            for pid in shown | {d.place_id for d in s.state.dropped}:
                tray.pop(pid, None)
        return list(tray.values()) + [
            {"place_id": p.id, "name": p.name, "reason": p.reason} for p in base.trip.unplaced]

    def _offer_key(self, s: Session, base: _Base) -> str:
        return fingerprint((s.state.model_dump(mode="json"), self._home_for(s, base), base.generation))

    def _choice_metadata(self, s: Session, base: _Base) -> dict:
        """The explanation offered before the initial choice; later edits never reopen drop selection."""
        first = next((k for k, state in enumerate(s.states[:s.position + 1]) if state.chosen_variant), None)
        source = None
        if first is None:
            source = s
        elif first:
            source = s.model_copy(update={"states": s.states[:first], "position": first - 1})
        if source is not None:
            key = self._offer_key(source, base)
            if key not in base.offers:
                self._offered_variants(source, base)
            if key in base.offers and "ok" in base.offers[key]:
                return base.offers[key]
        return {"ok": base.ok, "overload": base.overload, "back_to_decision": base.back_to_decision,
                "leftover": base.leftover}

    def _offered_variants(self, s: Session, base: _Base, active=None) -> list[dict]:
        """Before a choice, rebuild directions for a new lodging. After a choice, edits retain its subset:
        only lay out the other cards against the edits, never run drop selection again implicitly."""
        home = self._home_for(s, base)
        initial = base.trip.ctxs[0].home if base.trip.ctxs else None
        state = s.state
        key = self._offer_key(s, base)
        if key in base.offers:
            return base.offers[key]["variants"]
        unchanged = not any(getattr(state, k) for k in (
            "restored", "assignment", "activity_override", "visit_duration_override", "order_override", "dropped",
            "locked", "pace_override", "objective_override", "day_window_override", "relaxed"))
        if unchanged and home == initial:
            cards = [dict(card) for card in base.variants]
            for card in cards:
                self._attach_lodging(card, s, base)
            return put(base.offers, key, {"variants": cards}, self.cfg.cache_entries)["variants"]
        if state.chosen_variant is None:
            trip, ctxs = self._ctxs_for(base.trip, self._places_for(s, base), home, state)
            trip = replace(trip, ctxs=ctxs, days=[cx.day for cx in ctxs])
            cards = plan_cards(trip, protected=set(state.locked) | set(state.assignment) | set(state.restored))
            for card in cards["variants"]:
                self._attach_lodging(card, s, base)
            return put(base.offers, key, cards, self.cfg.cache_entries)["variants"]
        cards = []
        originals = list(self._choice_metadata(s, base).get("variants", base.variants))
        if state.chosen_variant not in {v["id"] for v in originals}:
            originals.append({"id": state.chosen_variant, "kept": list(self._places_for(s, base)), "_results": []})
        for card in originals:
            if card["id"] == state.chosen_variant and active:
                rendered = self._variant_dict(base, s, active["results"], active["ctxs"])
            else:
                neutral = state.model_copy(deep=True)
                neutral.chosen_variant = card["id"]
                if card["id"] != state.chosen_variant:
                    neutral.order_override = {}
                    protected = set(state.locked) | set(state.assignment) | set(state.restored)
                    neutral.plan_dropped = sorted(set(base.trip.by_place) - set(card["kept"]) - protected)
                trial = s.model_copy(update={"states": s.states[:s.position] + [neutral]})
                results, ctxs = self._card_layout(base, trial, card["_results"])
                rendered = self._variant_dict(base, trial, results, ctxs)
            cards.append(rendered)
        return put(base.offers, key, {"variants": cards}, self.cfg.cache_entries)["variants"]

    def _preview_fingerprint(self, s: Session, base: _Base) -> str:
        lodging = [(c.get("id"), c.get("price_vnd")) for c in base.lodging_candidates]
        return fingerprint((s.id, s.state.model_dump(mode="json"), s.decision, base.generation,
                            self._home_for(s, base), lodging, base.trip.travel.source, base.trip.travel.index))

    def _act_ctx(self, s: Session, base: _Base, previous: list) -> ActCtx:
        from .composer import must_places
        selected = {c["id"] for c in s.decision.get("confirmed") or []}
        protected = must_places(base.trip) | set(s.state.locked) | set(s.state.restored) | set(s.state.assignment)
        active = self._active_itinerary(s, base, previous) if s.state.chosen_variant else None
        offered = self._offered_variants(s, base, active)
        variant_ids = {v["id"] for v in offered
                       if v.get("status", "available") == "available"}
        variant_kept = {v["id"]: set(v.get("kept") or []) for v in offered
                        if v.get("status", "available") == "available" and "kept" in v}
        # Extend the edited normal window; a dawn pull is reapplied by layout, never stacked into session overrides.
        _, ctxs = self._ctxs_for(base.trip, self._places_for(s, base), self._home_for(s, base), s.state)
        fixed = set()
        for k, cx in enumerate(ctxs):
            day = cx.day
            if day.intensity == "free" or day.start_by_user or (k == 0 and day.start_node == "@entry"):
                fixed.add((k, "start"))
            if day.intensity == "free" or day.depart_by is not None or (k == len(ctxs) - 1 and day.end_node == "@exit"):
                fixed.add((k, "end"))
        return ActCtx(by_place={**base.trip.by_place, **self._places_for(s, base)},
                      n_days=len(base.trip.days),
                      variant_ids=variant_ids,
                      backup_ids={**{p.id: {"id": p.id, "for": None, "reason": "suggestion"}
                                     for p in self._ghost_pool(s, base)},
                                  **{b["id"]: b for b in s.decision.get("backup_pool") or []}},
                      day_members=[list(r.order) for r in previous] if previous else [],
                      objective_names=set(LABEL), valid_paces=set(self.cfg.per_day),
                      activities=s.decision["trip_context"].get("activities") or {},
                      variant_kept=variant_kept,
                      selection_ids=selected, protected_ids=protected,
                      day_windows=[(cx.day.start, cx.day.end) for cx in ctxs], fixed_edges=frozenset(fixed),
                      extend_max=self.cfg.realistic["extend_max_min"],
                      duration_range=(self.cfg.duration_profiles['manual_min'], self.cfg.duration_profiles['manual_max']))

    def _resolve_reoptimize(self, base: _Base, s: Session, action: dict) -> dict:
        if action.get("type") != "reoptimize":
            return action
        if set(action) != {"type"}:
            raise ActionError("reoptimize does not accept optimizer internals")
        cards = self._choice_metadata(s, base).get("variants", base.variants)
        selected = next((v for v in cards if v["id"] == s.state.chosen_variant), None)
        if not selected or selected["id"] == "main":
            raise ActionError("reoptimize is available only for overload directions")
        banned = {drop.place_id for drop in s.state.dropped}
        by_place = {pid: self._active_place(s, base, pid) for pid in base.trip.by_place if pid not in banned}
        trip, ctxs = self._ctxs_for(base.trip, by_place, self._home_for(s, base), s.state)
        trip = replace(trip, by_place=by_place, ctxs=ctxs, days=[cx.day for cx in ctxs],
                       pace=s.state.pace_override or trip.pace)
        protected = set(s.state.locked) | set(s.state.restored) | set(s.state.assignment)
        out = plan_cards(trip, protected=protected)
        card = next((v for v in out["variants"] if selected["id"] in [v["id"], *v.get("merged", [])]), None)
        if card is None and len(out["variants"]) == 1 and out["variants"][0]["id"] == "main":
            card = out["variants"][0]
        if card is None or not card["available"]:
            raise ActionError("cannot reoptimize: no direction satisfies the protected choices")
        return {"type": "reoptimize", "_plan_dropped": sorted(set(by_place) - set(card["kept"]))}

    @staticmethod
    def _view_confirmable(view: dict) -> bool:
        profile = view.get("active_variant") or {}
        return not bool(view.get("violations")) and profile.get("confirmable", True) is not False

    def _make_room_actions(self, s: Session, base: _Base, action: dict, previous: list,
                           ctx: ActCtx, candidates: list[str]) -> list[dict]:
        if action.get("type") not in {"move_place", "add_from_backup", "swap"}:
            return []
        protected = set(ctx.protected_ids) | {action.get("place"), action.get("with")}
        optional = sorted(set(candidates) - protected)
        limit = int(self.cfg.composer.get("make_room_trials", 18))
        attempts, found = 0, []
        for size in range(1, min(3, len(optional)) + 1):
            for dropped in combinations(optional, size):
                if attempts >= limit:
                    return found
                attempts += 1
                composite = {"type": "make_room", "edit": copy.deepcopy(action),
                             "drop_places": list(dropped)}
                try:
                    new_state = _apply(s.state, composite, ctx)
                    trial = s.model_copy(deep=True)
                    trial.states = s.states[:s.position + 1] + [new_state]
                    trial.position = s.position + 1
                    trial_base = copy.deepcopy(base)
                    prior_base = self._base.get(s.id)
                    self._base[s.id] = trial_base
                    try:
                        results = self._compute_results(trial_base, trial, s.state, previous, composite)
                        active = self._active_itinerary(trial, trial_base, results)
                        view = self._view(trial, results, active)
                    finally:
                        if prior_base is not None:
                            self._base[s.id] = prior_base
                        else:
                            self._base.pop(s.id, None)
                except (ActionError, StopIteration):
                    continue
                if self._view_confirmable(view):
                    found.append(composite)
                    if len(found) >= 3:
                        return found
            if found:
                return found
        return found

    def preview_act(self, sid: str, action: dict) -> dict:
        """Build an isolated edit preview; it never commits State, history, output, or live lookups."""
        if action.get("type") in {"set_lodging", "set_lodging_budget"}:
            raise ActionError("this action needs a fresh lodging lookup and cannot be previewed")
        with self.store.lock(sid):
            client_action = copy.deepcopy(action)
            s = self._get(sid)
            base = self._ensure_base(sid)
            if s.state.chosen_variant is None and action.get("type") != "pick_variant":
                raise ActionError("pick a variant before previewing an edit")
            previous = self._schedules.get(sid, [None] * len(s.states))[s.position]
            if previous is None:
                previous = self._card_results(base, s.state.chosen_variant)
            trial_base = copy.deepcopy(base)
            ctx = self._act_ctx(s, trial_base, previous)
            if action.get("type") == "pick_lodging" and action.get("id") not in {
                    c["id"] for c in self._offered_lodging(trial_base, s.state)}:
                raise ActionError(f"unknown or no-longer-offered lodging {action.get('id')!r}")
            action = self._resolve_reoptimize(trial_base, s, action)
            new_state = _apply(s.state, action, ctx)
            s2 = s.model_copy(deep=True)
            s2.states = s.states[:s.position + 1] + [new_state]
            s2.position = s.position + 1
            prior_base = self._base.get(sid)
            self._base[sid] = trial_base
            try:
                results = self._compute_results(trial_base, s2, s.state, previous, action)
                active = self._active_itinerary(s2, trial_base, results)
                view = self._view(s2, results, active)
                before_active = self._active_itinerary(s, base, previous) if s.state.chosen_variant else None
            finally:
                if prior_base is not None:
                    self._base[sid] = prior_base
                else:
                    self._base.pop(sid, None)
            token = secrets.token_urlsafe(24)
            state_key = self._preview_fingerprint(s, base)
            self._preview_tokens[sid] = ({"token": token, "action": client_action,
                                          "fingerprint": state_key}, time.monotonic())
            before_metrics = before_active["metrics"] if before_active else None
            after_metrics = active["metrics"] if active else None
            fields = ("travel_min", "visit_min", "cost_vnd", "places", "wish_coverage", "robustness")
            delta = {key: (after_metrics or {}).get(key) - (before_metrics or {}).get(key)
                     if isinstance((after_metrics or {}).get(key), (int, float))
                     and isinstance((before_metrics or {}).get(key), (int, float)) else None for key in fields}
            confirmable = self._view_confirmable(view)
            make_room = [] if confirmable else self._make_room_actions(
                s, base, client_action, previous, ctx, [pid for r in active["results"] for pid in r.order])
            return {"token": token, "action": client_action, "view": view, "delta": delta,
                    "violations": view.get("violations") or [],
                    "confirmable": confirmable, "make_room": make_room}

    def _lodging_card(self, c: dict, decision: dict) -> dict:
        """What the lodging list shows of a candidate (docs/Role_Web_Functional_Design.md §6), in the shape of a Place
        Decision card (decision/cards.py) so the web draws it with the same PlaceCard; price_at: the day Maps showed
        that price a night (a reference, not the trip's dates). Strengths and bad sides are only what the reviewers
        of that lodging confirmed (VERIFIED, at least 2 of them); nothing is said without evidence."""
        names = self.labels.get("feature") or {}
        rec = c["rec"]
        ctx = decision["trip_context"]["context"]
        loc = self._lodging_location(c, ctx.get("mobility"))
        fit = [{k: f[k] for k in ("text", "mentions", "quote")} for f in c.get("fit") or []]
        strengths, weaknesses = self._lodging_traits(rec)
        why = [{"text": f"{f['text']}, {f['mentions']} người nhắc" if f.get("mentions") else f["text"], "sid": f["feature"]}
               for f in c.get("fit") or []]
        why += [w for w in strengths if w["sid"] not in {x["sid"] for x in why}]
        if loc["minutes"] is not None and loc["minutes"] <= self.card_cfg.get("near_min", 0):
            why.append({"text": f"Gần {loc['center']}, ≈{loc['minutes']} phút (ước tính)", "sid": None})
        tradeoffs = list(weaknesses)
        if c.get("price_vnd") and ctx.get("budget_vnd") is None:
            tradeoffs.append({"text": f"Chưa biết ngân sách; giá khoảng {c['price_vnd'] // 1000}k/đêm", "sid": None})
        voices = c.get("reviews") or 0
        return {"id": c["id"], "name": c["name"], "price_vnd": c["price_vnd"], "source": c.get("source"),
                "price_at": c.get("price_at"), "address": c.get("address"),
                "category": rec["identity"].get("category"), "area": rec["identity"].get("area"),
                "rating": c.get("rating"), "reviews": c.get("reviews"), "avg_min": c.get("avg_min"),
                "fit": fit, "why": why[:3], "tradeoffs": tradeoffs[:3], "location": loc,
                "confidence": {"level": "high" if voices >= 40 else "medium" if voices >= 10 else "low",
                               "reason": f"{voices} người đã viết về nơi này."},
                "unverified": [names.get(f, f.replace("_", " ")).lower() for f in c.get("unverified") or []]}

    def _lodging_location(self, c: dict, mobility: str | None) -> dict:
        """{center, km, minutes}: the straight line to the city centre x road factor at a city speed, the same
        estimate Place Decision's cards give (decision/geo.py); none when the settings are not given."""
        centre = self.card_cfg.get("center")
        if not centre or not self.card_cfg.get("speed_kmh"):
            return {"center": None, "km": None, "minutes": None}
        d = km((c["lat"], c["lng"]), (centre["lat"], centre["lng"]))
        minutes = max(1, round(d * self.card_cfg["road_factor"] / self.card_cfg["speed_kmh"][mobility or "motorbike"] * 60))
        return {"center": centre["name"], "km": round(d, 1), "minutes": minutes}

    def _ontology(self):
        """The feature ontology, parsed once per engine: parsing config/ontology.yaml takes ~0.1 s, and every lodging
        card needs it (1500 cards were minutes)."""
        if self._ont is None:
            self._ont = load_ontology()
        return self._ont

    def _lodging_traits(self, rec: dict) -> tuple[list[dict], list[dict]]:
        """(strengths, bad sides) of a stay record from what its reviewers confirmed: for each feature a lodging
        carries (config/ontology.yaml stay_features), the best value of its polarity or a present / suitable / good /
        included one is a strength, the worst value of its polarity a bad side; most reviewers first."""
        polarity = self.card_cfg.get("polarity") or {}
        ont = self._ontology()
        good, bad = [], []
        for fid in sorted({s.partition("=")[0] for s in ont.stay}):
            f = feature(rec, fid)
            if not f or f["status"] != "VERIFIED" or (f.get("n") or 0) < 2 or not ont.applies(fid, f["value"], "stay"):
                continue
            order = polarity.get(fid)
            item = {"text": f"{phrase(fid, f['value'], self.labels)}, {f['n']} người nhắc", "sid": fid, "n": f["n"]}
            if fid not in NOT_A_STRENGTH and (f["value"] in (order[:1] if order else ()) or f["value"] in STRONG_VALUES):
                good.append(item)
            elif order and f["value"] == order[-1]:
                bad.append({**item, "text": f"{phrase(fid, f['value'], self.labels)}, theo {f['n']} người"})
        by_n = lambda xs: [{"text": x["text"], "sid": x["sid"]} for x in sorted(xs, key=lambda x: -x["n"])]
        return by_n(good), by_n(bad)

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
        if p is None and (pid in {b["id"] for b in s.decision.get("backup_pool") or []}
                          or (pid in s.state.assignment and pid in self.by_id)):   # an accepted faded suggestion
            from .places import build_places
            tc = {**s.decision["trip_context"], "activities": {
                **(s.decision["trip_context"].get("activities") or {}), **s.state.activity_override}}
            built, _ = build_places({"confirmed": [{"id": pid}], "trip_context": tc}, self.by_id, self.cfg)
            p = built[0] if built else None
        elif p and pid in s.state.activity_override:
            activity = s.state.activity_override[pid]
            p = replace(p, activity=activity, activity_explicit=True, kind="meal" if activity == "eating" else "experience")
        if p and pid in s.state.visit_duration_override:
            minutes = s.state.visit_duration_override[pid]
            p = replace(p, visit={**p.visit, 'short': minutes, 'typical': minutes, 'long': minutes, 'source': 'user'})
        return replace(p, relaxed=p.relaxed + tuple(relax_for)) if p and relax_for else p

    def _places_for(self, s: Session, base: _Base) -> dict:
        dropped = {d.place_id for d in s.state.dropped} | \
            (set(s.state.plan_dropped) - set(s.state.restored))
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
            return base.trip.ctxs[0].home if base.trip.ctxs else None
        if state.lodging_point:
            return state.lodging_point["id"]
        return state.lodging_id

    def _home_latlng(self, s: Session, base: _Base, home: str | None):
        """(lat, lng) of the node the trip sleeps at, or None when it is not known."""
        if home is None:
            return None
        pt = base.trip.points.get(home)
        if pt:
            return pt.lat, pt.lng
        if s.state.lodging_point and s.state.lodging_point.get("id") == home:
            return s.state.lodging_point["lat"], s.state.lodging_point["lng"]
        c = next((c for c in base.lodging_candidates if c["id"] == home), None)
        if c and c.get("lat") is not None:
            return c["lat"], c["lng"]
        ident = (self.by_id.get(home) or {}).get("identity") or {}
        return (ident["lat"], ident["lng"]) if ident.get("lat") is not None and ident.get("lng") is not None else None

    def _ghost_pool(self, s: Session, base: _Base):
        """The places faded suggestions come from (ghosts.pool): built once per base, rebuilt only when the lodging
        the days start from changes, never per edit."""
        home = self._home_for(s, base)
        if base.pool is None or base.pool_home != home:
            decision = s.decision
            at = self._home_latlng(s, base, home)
            if at:
                tc = decision["trip_context"]
                decision = {**decision, "trip_context": {**tc, "context": {
                    **tc["context"], "base": {**(tc["context"].get("base") or {}), "lat": at[0], "lng": at[1]}}}}
            base.pool, base.pool_home = ghost_pool(self.records, decision, self.cfg), home
        return base.pool

    def _ghosts(self, s: Session, base: _Base, active: dict) -> list[dict]:
        """view["ghosts"] (spec §6): one entry per empty meal slot and long free time of the shown days, `day` 0-based
        as add_from_backup takes it; accepting one is add_from_backup of its place id, dismissing it is
        dismiss_suggestion. Never on the timeline, in metrics or in the validator until the user taps it."""
        places = self._ghost_pool(s, base)
        home = base.pool_home
        key = fingerprint((active["context_key"], home, sorted(s.state.dismissed)))
        if key not in base.ghosts:
            points = base.trip.points
            at = self._home_latlng(s, base, home)
            if home is not None and home not in points and at:
                points = {**points, home: Point(at[0], at[1], "", "corpus", None)}
            taken = set(base.trip.by_place) | set(s.state.assignment) | {
                pid for r in active["results"] for pid in r.order}
            tc = s.decision["trip_context"]
            put(base.ghosts, key, fill_ghosts(active["ctxs"], active["results"], places, taken, set(s.state.dismissed),
                                       tc.get("soft_weights") or [], points, wanted=places.wanted),
                self.cfg.cache_entries)
        return base.ghosts[key]

    def _ensure_ghost_nodes(self, base: _Base, s: Session) -> None:
        """An accepted suggestion is laid out like any stop, so it must be on the travel matrix: join every placed id
        the matrix lacks (live act and replay alike); a no-op once it is there."""
        missing = {}
        for pid in s.state.assignment:
            ident = (self.by_id.get(pid) or {}).get("identity") or {}
            if pid not in base.trip.travel.index and ident.get("lat") is not None and ident.get("lng") is not None:
                missing[pid] = (ident["lat"], ident["lng"])
        if not missing:
            return
        base.ghost_nodes.update(missing)
        base.trip = self._prepare(s.decision, extra_nodes={
            **{c["id"]: (c["lat"], c["lng"]) for c in base.lodging_candidates},
            **{pid: (p['lat'], p['lng']) for pid, p in base.manual_points.items()}, **base.ghost_nodes})

    def _ctxs_for(self, trip, by_place: dict, home: str | None, state: State, results: list | None = None):
        """results: days already laid out; their windows get the scheduler's own early start for a sunrise place."""
        t2 = trip if home in (None, trip.ctxs[0].home if trip.ctxs else None) else with_home(trip, home)
        ctxs = list(t2.ctxs)                 # a fresh list: never mutate t2.ctxs (shared with base.trip) in place
        if state.pace_override and state.pace_override != t2.pace:
            ctxs = [replace(cx, pace=state.pace_override) for cx in ctxs]
        for day, (lo, hi) in state.day_window_override.items():
            if 0 <= day < len(ctxs):
                ctxs[day] = replace(ctxs[day], day=window_override(ctxs[day].day, lo, hi))   # never past departure
        ctxs = [replace(cx, places=by_place, travel=t2.travel, cfg=t2.cfg) for cx in ctxs]
        if results is not None:     # a time of day the layout gave up (unpinned) pulls no start, as in schedule_trip
            ctxs = [pull_early(cx, [i.place_id for i in r.items if i.kind == "visit"],
                               {**by_place, **{i: replace(by_place[i], pins=()) for i in r.unpinned if i in by_place}},
                               t2.travel)[0]
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
        dropped = {d.place_id for d in s.state.dropped} | \
            (set(s.state.plan_dropped) - set(s.state.restored))
        return [[i for i in ids if i not in dropped] for ids in per_day]

    def _repair_pass(self, s: Session, ctxs: list, baseline: list, touched_days: set, quick: bool = False) -> list:
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
            # A pin the layout already gave up to fit the day stays given up: repair_day and its validity check see the
            # released day, and the result carries `unpinned` so every later validate honours the same decision.
            from .validate import release, validate
            held = tuple(pid for pid in (baseline[day].unpinned if day < len(baseline) else ()) if pid in members[day])
            released = release(ctxs[day], held)
            tc = s.decision["trip_context"]
            hard, budget, max_leg = tc.get("hard_filters") or [], tc["context"].get("budget_vnd"), (tc.get("pace") or {}).get("max_leg_min")
            quick_order = self._quick_order(members[day], prev_order, released, locked_here) if quick else None
            if day in s.state.order_override:
                from .build import simulate_order
                results[day] = simulate_order(s.state.order_override[day], released, hard, budget, max_leg)
            elif quick_order is not None:
                # cached like repair_day: the other cards relay the same days again on every later edit
                base = self._base[s.id]
                key = fingerprint(("quick", day_key(released, members[day]), sorted(members[day]), prev_order,
                                   hard, budget, max_leg, held))
                if key not in base.repairs:
                    put(base.repairs, key, quick_order(hard, budget, max_leg), self.cfg.cache_entries)
                results[day] = base.repairs[key]
            else:
                base = self._base[s.id]
                key = fingerprint((day_key(ctxs[day], members[day]), members[day], prev_order,
                                   sorted(locked_here), hard, budget, max_leg, held))
                if key not in base.repairs:
                    result = repair_day(members[day], released, prev_order, locked_here, released.cfg,
                                        valid=lambda r: not validate([released], [r], hard, set(), budget, max_leg))
                    put(base.repairs, key, result, self.cfg.cache_entries)
                results[day] = base.repairs[key]
            carried = tuple(pid for pid in held if pid in results[day].order)
            if carried:
                results[day] = replace(results[day], unpinned=tuple(dict.fromkeys((*carried, *results[day].unpinned))),
                                       pin_conflicts=tuple((p, reasons) for p, reasons in baseline[day].pin_conflicts
                                                           if p in carried) + results[day].pin_conflicts)
        return results

    @staticmethod
    def _quick_order(members: list, prev_order, cx, locked: set):
        """Spec §8 for move_place / add_from_backup / drop_place: the day keeps the order it had; a place that left
        is taken out and the day retimed, a place that arrived goes where it costs least (every slot of the kept
        order tried, the best day result wins: fewest problems, then meals, then the earliest end). No search over
        other orders: what the new order breaks stays flagged on its row (validate), never hidden. None: not a single
        arrival or departures on a known order -- the full repair runs."""
        if prev_order is None:
            return None
        kept = [pid for pid in prev_order if pid in members]
        added = [pid for pid in members if pid not in prev_order]
        if len(added) > 1 or (set(prev_order) & locked) - set(members):
            return None
        orders = [kept[:i] + added + kept[i:] for i in range(len(kept) + 1)] if added else [kept]

        def lay(hard, budget, max_leg):
            from .build import simulate_order
            from .schedule import simulate
            best = min((simulate(list(o), cx) for o in orders), key=lambda r: r.key) if len(orders) > 1 else None
            return replace(simulate_order(list(best.order if best else orders[0]), cx, hard, budget, max_leg),
                           method="insert" if added else "retime")
        return lay

    def _card_layout(self, base: _Base, s: Session, baseline: list) -> tuple:
        """A card's days with the session's edits on top, as the card is shown among the others (picking it takes
        exactly these days: its _results). A day keeps the card's own layout unless its places changed (a move, a drop, a place
        added: the quick insertion / retime of spec §8) or something every day's frame reads changed (the lodging,
        the pace, a day window, a visit length, an activity, a relaxed filter): then every day is laid out again."""
        st = s.state
        initial = base.trip.ctxs[0].home if base.trip.ctxs else None
        frame_changed = self._home_for(s, base) != initial or any(getattr(st, k) for k in (
            "pace_override", "day_window_override", "visit_duration_override", "activity_override", "relaxed"))
        return self._relayout(base, s, baseline, set(range(len(baseline))) if frame_changed else set(), quick=True)

    def _relayout(self, base: _Base, s: Session, prev_results: list, touched_days: set, quick: bool = False) -> tuple:
        by_place = self._places_for(s, base)
        home = self._home_for(s, base)
        trip, ctxs = self._ctxs_for(base.trip, by_place, home, s.state, prev_results)
        return self._repair_pass(s, ctxs, prev_results, touched_days, quick), ctxs

    def _rebuild_variant(self, base: _Base, s: Session) -> tuple:
        """VARIANT scope: a trip-wide parameter changed (pace, objective, or a day window), so the chosen
        objective's whole day split reruns from scratch (schedule_trip) against a trip that already excludes
        dropped places and carries the pace / day-window overrides -- this is the one path allowed to reshuffle a
        day the act did not literally touch, because the parameter it changed legitimately affects every day.
        schedule_trip's own automatic layout knows nothing about State.assignment / order_override / locked, so a
        repair pass (the same one a RELAYOUT uses) re-applies them on top, seeded from this fresh layout -- a
        place the user moved or locked lands back on its pinned day regardless of where the automatic clustering
        would have put it, and repair_day still refuses to let a locked place leave its day."""
        selected = next((v for v in base.variants if v["id"] == s.state.chosen_variant), None)
        obj = s.state.objective_override or (selected["objective"] if selected else "least_travel")
        by_place = self._places_for(s, base)
        home = self._home_for(s, base)
        trip = replace(base.trip, by_place=by_place)
        t2 = trip if home in (None, trip.ctxs[0].home if trip.ctxs else None) else with_home(trip, home)
        if s.state.pace_override:
            t2 = replace(t2, pace=s.state.pace_override)
        ctxs = list(t2.ctxs)
        if s.state.pace_override:
            ctxs = [replace(cx, pace=s.state.pace_override) for cx in ctxs]
        for day, (lo, hi) in s.state.day_window_override.items():
            if 0 <= day < len(ctxs):
                ctxs[day] = replace(ctxs[day], day=window_override(ctxs[day].day, lo, hi))   # never past departure
        t2 = replace(t2, ctxs=ctxs)
        weights = dict(self.cfg.objective_weights.get(obj, self.cfg.objective_weights["least_travel"]))
        sched = schedule_trip(t2, weights)
        results = self._repair_pass(s, sched.ctxs, sched.results, set(range(len(sched.ctxs))))
        return results, sched.ctxs

    def _attach_lodging(self, card: dict, s: Session, base: _Base) -> None:
        home = self._home_for(s, base)
        cand = next((c for c in base.lodging_candidates if c["id"] == home), None)
        if cand is None and s.state.lodging_point:
            cand = {"id": home, "name": s.state.lodging_point.get("text"),
                    "price_vnd": s.state.lodging_point.get("price_vnd")}
        if cand:
            card["lodging"] = {k: cand[k] for k in ("id", "name", "price_vnd")}
            slept = _nights(s.decision["trip_context"]["context"])
            card["metrics"] = add_lodging_cost(card["metrics"], cand["price_vnd"], slept)
            lodging_cost = cand["price_vnd"] * slept if cand["price_vnd"] is not None else None
            card["metrics"]["lodging_cost_vnd"] = lodging_cost
            if lodging_cost is None:
                card["metrics"]["cost_basis"] = "partial"
            else:
                card["metrics"]["estimated_cost_vnd"] += lodging_cost

    def _variant_dict(self, base: _Base, s: Session, results: list, ctxs: list) -> dict:
        from .build import Schedule
        from .model import Violation
        active = self._active_itinerary(s, base, results)
        cache_key = fingerprint(s.state.model_dump(mode="json"))
        rendered = active.setdefault("variants", {})
        if cache_key in rendered:
            return rendered[cache_key]
        cards = self._choice_metadata(s, base).get("variants", base.variants)
        selected = next((v for v in cards if v["id"] == s.state.chosen_variant), {})
        by_place = self._places_for(s, base)
        trip = replace(base.trip, by_place=by_place, ctxs=ctxs, days=[cx.day for cx in ctxs])
        shown = {pid for r in results for pid in r.order}
        leftover = tuple(sorted(set(by_place) - shown))
        sched = Schedule([list(r.order) for r in results], results, ctxs,
                         [Violation(**v) for v in active["violations"]], [], leftover)
        old_drops = {d["place_id"]: d for d in selected.get("dropped", [])}
        drops = [old_drops.get(pid) or {"place_id": pid, "name": base.trip.by_place[pid].name,
                                       "reason": None, "value": None}
                 for pid in s.state.plan_dropped if pid not in s.state.restored]
        card = render_variant(trip, sched, s.state.chosen_variant, drops, available=not leftover, day_parts=False)
        # Reuse the active day's cached artifacts; measure retained value against the original selection.
        card["robustness"], card["backups"] = active["robustness"], active["backups"]
        from .variants import drop_metadata
        card["dropped_by_plan"] = drop_metadata(replace(base.trip, pace=s.state.pace_override or base.trip.pace),
                                                s.state.chosen_variant, drops)
        card["recommendations"] = self._suggestions(s, base, active)["items"]
        card["label"] = selected.get("label", CARD_LABEL[s.state.chosen_variant])
        card["merged"] = selected.get("merged", [])
        card["objective"] = s.state.objective_override or card["objective"]
        home = self._home_for(s, base)
        self._attach_lodging(card, s, base)
        card["_ctxs"], card["_home"] = ctxs, home
        return put(rendered, cache_key, card, self.cfg.cache_entries)

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
        changed_duration = {pid for pid in set(old.visit_duration_override) | set(new.visit_duration_override)
                            if old.visit_duration_override.get(pid) != new.visit_duration_override.get(pid)}
        days |= {day for day, result in enumerate(prev_results) if changed_duration & set(result.order)}
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
            **{c["id"]: (c["lat"], c["lng"]) for c in base.lodging_candidates},
            **{pid: (p['lat'], p['lng']) for pid, p in base.manual_points.items()}, **base.ghost_nodes,
            point["id"]: (point["lat"], point["lng"])})
        base.manual_points[point['id']] = point

    def _refetch_lodging(self, base: _Base, s: Session) -> None:
        """set_lodging_budget: a higher cap may surface stays the original search's price cap left out -- search
        again and merge anything new into the full candidate list (never replace it: a lower cap must only narrow
        what _offered_lodging shows, not discard what was actually found)."""
        decision = dict(s.decision)
        tc = dict(decision["trip_context"])
        tc["context"] = {**tc["context"], "budget_vnd": tc["context"].get("budget_vnd")}
        decision["trip_context"] = tc
        try:
            cands = lodging_candidates(base.trip.by_place, decision, self.cfg, self.records)
        except Exception:
            cands = []
        seen = {c["id"] for c in base.lodging_candidates}
        new = [c for c in cands if c["id"] not in seen]
        if new:
            base.lodging_candidates = base.lodging_candidates + new
            nodes = {c['id']: (c['lat'], c['lng']) for c in base.lodging_candidates}
            nodes.update({pid: (p['lat'], p['lng']) for pid, p in base.manual_points.items()})
            nodes.update(base.ghost_nodes)
            base.trip = self._prepare(s.decision, extra_nodes=nodes)

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
        if t == "reoptimize" and "_plan_dropped" not in action:
            action = self._resolve_reoptimize(base, s2, action)
        if t == "set_lodging" and action.get("_point"):
            self._ensure_lodging_node(base, s2.decision, action["_point"])
        self._ensure_ghost_nodes(base, s2)
        if s2.state.chosen_variant is None:
            if t == 'set_lodging_budget':
                self._refetch_lodging(base, s2)
            return []
        if t == "pick_variant":
            before = s2.model_copy(update={"states": [old_state], "position": 0})
            active = self._active_itinerary(before, base, prev_results) if old_state.chosen_variant else None
            offered = self._offered_variants(before, base, active)
            card = next(v for v in offered if v["id"] == s2.state.chosen_variant)
            results, _ = self._relayout(base, s2, card["_results"], set())
            return results
        scope = act_scope(action)
        if scope == NONE:
            return prev_results
        if scope == RELAYOUT:
            touched = self._touched_days(old_state, s2.state, prev_results)
            results, _ = self._relayout(base, s2, prev_results, touched, quick=t in QUICK_EDITS)
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
            preview_token = action.get("_preview_token")
            if preview_token is not None:
                entry = self._preview_tokens.get(sid)
                if (entry is None or entry[0].get("token") != preview_token or
                        entry[1] < time.monotonic() - 600 or entry[0].get("action") !=
                        {k: v for k, v in action.items() if k != "_preview_token"} or
                        entry[0].get("fingerprint") != self._preview_fingerprint(s, base)):
                    raise ActionError("preview token is stale or does not match this action; preview again")
                action = {k: v for k, v in action.items() if k != "_preview_token"}
            requested_action = copy.deepcopy(action)
            t = action.get("type")
            if s.require_lodging and t == 'pick_variant' and not (s.state.lodging_touched and s.state.lodging_id):
                raise ActionError('choose a hotel before choosing a plan')
            if s.require_lodging and t == 'clear_lodging':
                raise ActionError('a hotel is required; choose another hotel instead')
            if t in {'make_room', 'set_visit_duration'} and preview_token is None:
                raise ActionError(f'{t} requires a preview token; preview the action first')
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

            if s.state.chosen_variant is None and t not in {"pick_variant", "pick_lodging", "set_lodging", "set_lodging_budget", "extend_days"}:
                raise ActionError("pick a variant before editing the plan")
            prev_results = self._schedules.get(sid, [None])[s.position] or \
                (next(v["_results"] for v in base.variants if v["id"] == s.state.chosen_variant)
                if s.state.chosen_variant else [])
            ctx = self._act_ctx(s, base, prev_results)
            if t == "pick_lodging":
                if action.get("id") not in {c["id"] for c in self._offered_lodging(base, s.state)}:
                    raise ActionError(f"unknown or no-longer-offered lodging {action.get('id')!r}")
            elif t == "set_lodging":
                text = (action.get("text") or "").strip()
                if not text:
                    raise ActionError("set_lodging needs non-empty text")
                if 'lat' in action or 'lng' in action:
                    lat, lng = action.get('lat'), action.get('lng')
                    if (type(lat) not in (int, float) or type(lng) not in (int, float)
                            or not -90 <= lat <= 90 or not -180 <= lng <= 180):
                        raise ActionError('invalid hotel coordinates')
                    hit = {'lat': lat, 'lng': lng, 'source': 'user', 'fetched_at': None}
                else:
                    try:
                        hit = self.geocode_fn(text) if self.geocode_fn else live.geocode(text, self.live_cfg)
                    except live.Unavailable:
                        hit = None
                point = {"id": f"manual:{text}:{fingerprint((hit['lat'], hit['lng']))[:12]}",
                        "lat": hit["lat"], "lng": hit["lng"], "text": text,
                        "source": hit["source"], "fetched_at": hit.get("fetched_at")} if hit else None
                if point:
                    self._ensure_lodging_node(base, s.decision, point)
                action = {**action, "_point": point}
            elif t == "relax" and action.get("scope") == "whole_trip" and "place_ids" not in action:
                feature = action.get("feature")
                affected = [pid for pid, p in base.trip.by_place.items()
                           if feature not in p.relaxed and self._has_hard_violation(base, s, pid, feature)]
                action = {**action, "place_ids": affected}

            action = self._resolve_reoptimize(base, s, action)

            new_state = _apply(s.state, action, ctx)
            s2 = s.model_copy(update={"states": s.states[: s.position + 1] + [new_state], "position": s.position + 1})
            layout_start = time.perf_counter()
            results = self._compute_results(base, s2, s.state, prev_results, action)
            self.timings.setdefault(sid, {})["layout_ms"] = (time.perf_counter() - layout_start) * 1000
            render_start = time.perf_counter()
            active = self._active_itinerary(s2, base, results)
            view = self._view(s2, results, active)
            self.timings[sid]["view_ms"] = (time.perf_counter() - render_start) * 1000
            # Persist the public action. The derived kept/drop set is a trial detail and
            # must be recomputed during replay, not accepted as client input.
            logged_action = requested_action if t == "reoptimize" else action
            s2.log = s.log[:s.position] + [{"action": logged_action, "at": _now()}]
            s2.output = None
            self.store.save(s2)
            if preview_token is not None:
                self._preview_tokens.pop(sid, None)
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
            changed = sorted({i // base.trip.cfg.chunk_days for i, r in enumerate(results)
                              if i >= len(prev_results) or r is not prev_results[i]})
            return {"view": view, "diff": {"scope": scope, "affected_chunks": changed}}

    # ---------- internal recommendation ----------

    def _proposal_trial(self, base, session, state, previous, proposal):
        trial = session.model_copy(deep=True)
        trial.states = [state.model_copy(deep=True)]
        trial.position = 0
        ctx = self._act_ctx(trial, base, previous)
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
            if session.require_lodging and not (session.state.lodging_touched and session.state.lodging_id):
                return {'id': sid, 'view': self._view(session),
                        'proposal': {'status': 'fallback', 'diagnostics': ['choose_hotel']}}
            if not base.variants:
                return {'id': sid, 'view': self._view(session),
                        'proposal': {'status': 'fallback', 'diagnostics': ['no_valid_baseline']}}
            if session.state.chosen_variant is None:
                if base.overload:
                    return {'id': sid, 'view': self._view(session),
                            'proposal': {'status': 'fallback', 'diagnostics': ['choose_overload_profile']}}
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
            binding_data = session.decision.get('corpus_binding')
            binding = Binding.model_validate(binding_data) if binding_data is not None else None
            aliases = {c['id']: {'id': c['id']} for c in session.decision.get('confirmed') or []
                       if c['id'] in self.by_id}
            fields['corpus_binding'] = binding.model_dump(mode='json') if binding is not None else None
            fields['corpus_context'] = self._grounded_context(aliases, '', binding)
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
                if objective in CARD_LABEL:
                    objective = "least_travel"
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
            try:
                self._check_lodging(s.decision, s.state.lodging_point or {})
                if s.state.lodging_id and s.state.lodging_id in self.by_id:
                    self._check_lodging(s.decision, {"place_id": s.state.lodging_id})
            except ActionError as error:
                raise NotConfirmable(str(error)) from None
            if s.require_lodging and not (s.state.lodging_touched and s.state.lodging_id):
                raise NotConfirmable('choose a hotel before confirming the plan')
            if s.state.chosen_variant is None:
                raise NotConfirmable("no variant chosen")
            results = self._schedules.get(sid, [None] * len(s.states))[s.position]
            if results is None:
                results = self._card_results(base, s.state.chosen_variant)
            by_place = self._places_for(s, base)
            home = self._home_for(s, base)
            trip, ctxs = self._ctxs_for(base.trip, by_place, home, s.state, results)
            trip = replace(trip, ctxs=ctxs, days=[cx.day for cx in ctxs], by_place=by_place)
            from .validate import validate
            tc = s.decision["trip_context"]
            anchors = {c["id"] for c in s.decision["confirmed"] if c.get("role") == "anchor"}
            violations = validate(ctxs, results, tc.get("hard_filters") or [], anchors, tc["context"].get("budget_vnd"),
                                  (tc.get("pace") or {}).get("max_leg_min"))
            if base.trip.unplaced and any(p.id in anchors for p in base.trip.unplaced):
                raise NotConfirmable("required places cannot be scheduled")
            if set(by_place) - {pid for r in results for pid in r.order}:
                raise NotConfirmable("selected places do not fit the days: choose which to leave out")
            if violations:
                raise NotConfirmable("plan has unresolved violations")
            variant = self._variant_dict(base, s, results, ctxs)
            coords = {**{p.id: (p.lat, p.lng) for p in by_place.values()},
                     **{n: (pt.lat, pt.lng) for n, pt in trip.points.items() if pt},
                     **{c["id"]: (c["lat"], c["lng"]) for c in base.lodging_candidates}}
            if s.state.lodging_point:
                coords[home] = (s.state.lodging_point['lat'], s.state.lodging_point['lng'])
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

    def _grounded_context(self, aliases: dict, text: str, binding) -> list[dict]:
        """Bounded current serving evidence; semantic resemblance never establishes facts."""
        reader = self.retrieval
        if binding is None or reader is None or reader.binding != binding:
            return []
        ordered = sorted(aliases, key=lambda key: not (key in text or aliases[key].get("name", "\0") in text))
        out = []
        for alias in ordered[:3]:
            pid = aliases[alias]["id"]
            record = self.by_id.get(pid)
            if record is None:
                continue
            features = []
            for fid, definition in load_ontology().features.items():
                if fid not in (record.get(definition.group) or {}):
                    continue
                served = feature(record, fid) or {}
                value, status = served.get("value"), served.get("status")
                if value is None or status not in {"VERIFIED", "OUTDATED"}:
                    continue
                item = {"feature": fid, "value": value, "status": status, "quote": None, "source": None,
                        "observation_id": None, "source_id": None, "observed_at": None}
                try:
                    hits = reader.evidence(pid, fid, limit=1)
                except (FileNotFoundError, OSError):
                    hits = []
                for hit in hits[:1]:
                    if (hit.place_id == pid and hit.release_id == binding.release_id
                        and hit.feature == fid and hit.value == str(value) and hit.status == status):
                        item.update(quote=hit.quote[:500], source=hit.source, observation_id=hit.observation_id,
                                    source_id=hit.source_id, observed_at=hit.observed_at)
                features.append(item)
                if len(features) == 1:
                    break
            out.append({"alias": alias, "place_id": pid, "release_id": binding.release_id,
                        "features": features, "evidence_status": "available" if any(f["quote"] for f in features) else "unknown"})
        return out

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
