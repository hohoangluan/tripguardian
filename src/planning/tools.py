"""Public action-only Planning adapter; the model is used for internal proposals."""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

import live
from agents import ToolError, load_skill, permit_tool
from corpus.serving import SERVED
from corpus.retrieval import RetrievalEngine
from corpus.snapshot import shared
from corpus.releases import Binding, bind, resolve_binding
from decision import DecisionOutput
from decision import load_settings as decision_settings

from .conditions import fetch_live
from .engine import Engine, NoSession, NotConfirmable
from .logistics import Logistics
from .session import Session, Store
from .settings import ROOT, load


class StartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision_output: DecisionOutput


class Tools:
    def __init__(self, engine: Engine):
        if engine.store.root is not None:
            raise ValueError("harness tools require a memory store")
        self.engine = engine
        self.skill = load_skill(Path(__file__).with_name("skills.yaml"))
        self.logistics = Logistics(engine.records, engine.live_cfg)

    def _input(self, payload: dict) -> StartInput:
        inp = StartInput.model_validate(payload)
        if inp.decision_output.corpus_binding != getattr(self.engine, "corpus_binding", None):
            raise ValueError("Planning corpus binding mismatch; use the pinned release")
        return inp

    def create(self, payload: dict) -> dict:
        inp = self._input(payload)
        # Lodging is picked at Lựa chọn and never required: a plan without one says so (view.lodging), it is not refused.
        return self.engine.create(decision=inp.decision_output.model_dump(mode="json", by_alias=True))

    def preview(self, payload: dict) -> dict:
        inp = self._input(payload)
        return self.engine.preview(inp.decision_output.model_dump(mode="json", by_alias=True))

    def lodging_options(self, payload: dict, offset: int = 0, limit: int | None = None) -> dict:
        inp = self._input(payload)
        return self.engine.lodging_options(inp.decision_output.model_dump(mode="json", by_alias=True), offset, limit)

    def load(self, sid: str) -> dict:
        try:
            return self.engine.load(sid)
        except NoSession:
            raise ToolError(404, "no such Planning session") from None

    def apply(self, sid: str, operation: str, payload: dict, emit) -> dict:
        if operation == "act":
            if payload.get("type") == "confirm":
                raise ValueError("use the journey confirm operation")
            return self.engine.act(sid, payload)
        if operation == "confirm":
            try:
                return self.engine.confirm(sid)
            except NotConfirmable as exc:
                raise ToolError(409, str(exc)) from None
        if operation == "recommend":
            permit_tool(self.skill, "planning.propose")
            if payload:
                raise ValueError("Planning recommend does not accept user text or arbitrary tools")
            return self.engine.recommend(sid)
        raise ValueError(f"planning does not accept {operation}")

    def read(self, sid: str, operation: str, payload: dict) -> dict:
        if operation == "suggestions":
            return self.engine.suggestions(sid)
        if operation == "lodging":
            return self.engine.lodging(sid)
        if operation == "routes":
            return self.engine.routes(sid)
        if operation == "variants":
            return {"variants": self.engine.variants(sid)}
        if operation == "preview-act":
            import json
            raw = payload.get("action")
            if not isinstance(raw, str) or not 0 < len(raw) <= 8192:
                raise ValueError("action must be a JSON object of at most 8192 characters")
            try:
                action = json.loads(raw)
            except json.JSONDecodeError:
                raise ValueError("action must be valid JSON") from None
            if not isinstance(action, dict):
                raise ValueError("action must be a JSON object")
            return self.engine.preview_act(sid, action)
        raise ValueError(f"unknown Planning read {operation}")

    def geo(self, q: str) -> list[dict]:
        return self.logistics.geo(q)

    def lodging_suggest(self, q: str, top: int = 0) -> list[dict]:
        return self.logistics.lodging_suggest(q, top)

    def snapshot(self, sid: str) -> dict:
        with self.engine.store.lock(sid):
            return self.engine.store.get(sid).model_dump(mode="json")

    def restore(self, snapshot: dict) -> None:
        data = Session.model_validate(snapshot)
        self._input({"decision_output": data.decision})
        self.engine.store.restore(data)
        self.engine._base.pop(data.id, None)
        self.engine._schedules.pop(data.id, None)
        self.engine._epochs[data.id] = self.engine._epochs.get(data.id, 0) + 1


def create_engine(data_root: Path, *, binding: Binding | None = None,
                  retrieval: RetrievalEngine | None = None) -> Engine:
    load_dotenv(ROOT / ".env")
    cfg = load()
    decision = decision_settings()
    from .proposal import run_proposal
    async def agent(fields):
        return await run_proposal(fields, cfg)
    configured = all(os.environ.get(k) for k in ("AGENT_API_KEY", "AGENT_BASE_URL", "AGENT_MODEL"))
    binding = binding or bind(data_root)
    if retrieval is not None and retrieval.binding != binding:
        raise ValueError("retrieval corpus binding mismatch")
    root = resolve_binding(data_root, binding)
    snapshot = shared(root / "snapshot", version=binding.snapshot_version or "")
    retrieval = retrieval if retrieval is not None else RetrievalEngine.from_snapshot(snapshot, binding.region, binding=binding)
    records = [r for r in snapshot.region(binding.region).records()
               if r["status"] in SERVED]
    engine = Engine(records, retrieval=retrieval, cfg=cfg, store=Store(None), proposal_agent=agent if configured else None,
                  immutable_records_version=binding.manifest_sha256,
                  conditions_fn=fetch_live(live.load_settings()), labels=decision.labels,
                  card_cfg={"polarity": decision.polarity, "center": decision.center, "near_min": decision.near_min,
                            "speed_kmh": decision.speed_kmh, "road_factor": decision.road_factor})
    engine.corpus_binding = binding
    return engine
