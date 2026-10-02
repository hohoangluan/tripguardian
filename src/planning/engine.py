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
                geocode_fn=None, matrix_fn=None, sun_fn=None, lodging_fn=None, decision_url: str | None = None,
                http_post=None, background: bool = True):
        self.by_id = {r["id"]: r for r in records}
        self.records = records
        self.cfg = cfg or load_settings()
        self.live_cfg = live_cfg or live.load_settings()
        self.store = store or Store(None)
        self.geocode_fn = geocode_fn
        self.matrix_fn = matrix_fn
        self.sun_fn = sun_fn
        self.lodging_fn = lodging_fn or live.lodging_near
        self.decision_url = decision_url or self.cfg.decision_url
        self.http_post = http_post or _http_post
        self.background = background
        self._base: dict[str, _Base] = {}

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

    def _view(self, s: Session) -> dict:
        base = self._base[s.id]
        return {"ok": base.ok, "variants": [{k: v for k, v in v.items() if not k.startswith("_")} for v in base.variants],
               "comparison": base.comparison, "warnings": base.warnings, "back_to_decision": base.back_to_decision,
               "lodging": {"status": base.lodging_status,
                           "candidates": [{"id": c["id"], "name": c["name"], "price_vnd": c["price_vnd"]}
                                         for c in base.lodging_candidates]},
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
