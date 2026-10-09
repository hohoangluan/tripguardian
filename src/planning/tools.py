"""Public action-only Planning adapter; the model is used for internal proposals."""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

import live
from agents import ToolError, load_skill, permit_tool
from corpus.serving import load as load_records
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

    def create(self, payload: dict) -> dict:
        inp = StartInput.model_validate(payload)
        return self.engine.create(decision=inp.decision_output.model_dump(mode="json", by_alias=True))

    def preview(self, payload: dict) -> dict:
        inp = StartInput.model_validate(payload)
        return self.engine.preview(inp.decision_output.model_dump(mode="json", by_alias=True))

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
        if operation == "lodging":
            return self.engine.lodging(sid)
        if operation == "variants":
            return {"variants": self.engine.variants(sid)}
        raise ValueError(f"unknown Planning read {operation}")

    def geo(self, q: str) -> list[dict]:
        return self.logistics.geo(q)

    def lodging_suggest(self, q: str) -> list[dict]:
        return self.logistics.lodging_suggest(q)

    def transit(self, params: dict) -> dict:
        return self.logistics.transit(params)

    def snapshot(self, sid: str) -> dict:
        with self.engine.store.lock(sid):
            return self.engine.store.get(sid).model_dump(mode="json")

    def restore(self, snapshot: dict) -> None:
        data = Session.model_validate(snapshot)
        self.engine.store.restore(data)
        self.engine._base.pop(data.id, None)
        self.engine._schedules.pop(data.id, None)


def create_engine(data_root: Path) -> Engine:
    load_dotenv(ROOT / ".env")
    cfg = load()
    from .proposal import run_proposal
    async def agent(fields):
        return await run_proposal(fields, cfg)
    configured = all(os.environ.get(k) for k in ("AGENT_API_KEY", "AGENT_BASE_URL", "AGENT_MODEL"))
    return Engine(load_records(), cfg=cfg, store=Store(None), proposal_agent=agent if configured else None,
                  conditions_fn=fetch_live(live.load_settings()), labels=decision_settings().labels)
