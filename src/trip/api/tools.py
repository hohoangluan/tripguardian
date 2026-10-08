"""Public Trip adapter; schema and session restoration remain owned by Trip."""

import os
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from agents import AgentError, load_skill, permit_tool

from ..agent import run_agent
from ..domain.questions import Question
from ..domain.state import TripState
from ..infrastructure.catalog import Catalog
from ..infrastructure.profile import USER_ID, ProfileStore
from ..infrastructure.sessions import Session, SessionStore
from ..infrastructure.settings import ROOT, load
from .engine import Engine, TurnInput


class StartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    experience: Literal["first", "returning"] | None = None
    start_with: Literal["nothing", "saved", "must", "itinerary"] | None = None
    user_id: str | None = Field(None, pattern=USER_ID.pattern)
    remember: bool = False


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[0-9a-f]{12}$")
    state: TripState
    card: Question | None
    transcript: list[dict]


class Tools:
    def __init__(self, engine: Engine):
        if engine.store.root is not None:
            raise ValueError("harness tools require a memory store")
        self.engine = engine
        self.skill = load_skill(Path(__file__).parent.parent / "skills.yaml")

    def create(self, payload: dict) -> dict:
        inp = StartInput.model_validate(payload)
        return self.engine.create(inp.experience, inp.start_with, inp.user_id, inp.remember)

    def load(self, sid: str) -> dict:
        return self.engine.load(sid)

    def apply(self, sid: str, operation: str, payload: dict, emit) -> dict:
        if operation == "refine":
            permit_tool(self.skill, "trip.refine")
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > 1000 or set(payload) != {"text"}:
                raise ValueError("text must be 1-1000 characters")
            self.engine.refine(sid, text.strip(), emit)
            return self.load(sid)
        if operation != "turn":
            raise ValueError(f"trip does not accept {operation}")
        permit_tool(self.skill, "trip.turn")
        self.engine.turn(sid, TurnInput.model_validate(payload), emit)
        return self.load(sid)

    def places(self, query: str) -> list[dict]:
        return self.engine.places(query)

    def forget(self, user_id: str) -> bool:
        return self.engine.forget(user_id)

    def snapshot(self, sid: str) -> dict:
        s = self.engine.store.get(sid)
        with s.lock:
            return Snapshot(id=s.id, state=s.state, card=s.card, transcript=s.transcript).model_dump(mode="json")

    def restore(self, snapshot: dict) -> None:
        data = Snapshot.model_validate(snapshot)
        self.engine.store.restore(Session(data.id, data.state, data.card, data.transcript))


def create_engine(data_root: Path) -> Engine:
    """Harness owns persistence; the engine keeps its normal typed state in memory."""
    load_dotenv(ROOT / ".env")
    cfg = load()
    catalog = Catalog.load(data_root, cfg.n_min)
    async def agent(fields, on_say):
        if not all(os.environ.get(k) for k in ("AGENT_API_KEY", "AGENT_BASE_URL", "AGENT_MODEL")):
            raise AgentError("agent role is not configured")
        return await run_agent(fields, on_say, cfg)
    profiles = ProfileStore(ROOT / cfg.patterns.dir, cfg.patterns) if cfg.patterns.enabled else None
    return Engine(catalog, cfg, SessionStore(None), agent,
                  today=lambda: datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date(),
                  profiles=profiles)
