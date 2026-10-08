"""Public Decision tools and opaque typed snapshots for the journey harness."""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from agents import ToolError, load_skill, permit_tool
from trip import SearchInput

from .agent import run_agent
from .engine import Engine, NoSession, NotConfirmable, diff
from .contracts import DecisionOutput
from .pipeline import Data
from .session import Session, Store
from .settings import ROOT, default


class StartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search_input: SearchInput
    trip_session: str | None = Field(default=None, pattern=r"^[0-9a-f]{12}$")


class Tools:
    def __init__(self, engine: Engine):
        if engine.store.root is not None:
            raise ValueError("harness tools require a memory store")
        self.engine = engine
        self.skill = load_skill(Path(__file__).with_name("skills.yaml"))

    def create(self, payload: dict) -> dict:
        inp = StartInput.model_validate(payload)
        return self.engine.create(inp.search_input.model_dump(mode="json"), inp.trip_session)

    def load(self, sid: str) -> dict:
        try:
            return self.engine.load(sid)
        except NoSession:
            raise ToolError(404, "no such Decision session") from None

    def apply(self, sid: str, operation: str, payload: dict, emit) -> dict:
        if operation == "act":
            permit_tool(self.skill, "decision.act")
            if payload.get("type") == "confirm":
                raise ValueError("use the journey advance operation to confirm Decision")
            return self.engine.act(sid, payload)
        if operation == "turn":
            permit_tool(self.skill, "decision.turn")
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > 1000 or set(payload) != {"text"}:
                raise ValueError("text must be 1-1000 characters")
            self.engine.turn(sid, text, emit)
            return self.load(sid)
        if operation == "confirm":
            permit_tool(self.skill, "decision.confirm")
            try:
                output = self.engine.confirm(sid)
            except NotConfirmable as exc:
                raise ToolError(409, str(exc)) from None
            return DecisionOutput.model_validate(output).model_dump(mode="json", by_alias=True)
        raise ValueError(f"decision does not accept {operation}")

    def read(self, sid: str, operation: str, payload: dict) -> dict:
        if operation == "compare":
            permit_tool(self.skill, "decision.compare")
            return self.engine.compare(sid, payload.get("a", ""), payload.get("b", ""), record=False)
        if operation == "why-not":
            return self.engine.why_not(sid, payload.get("place", ""))
        if operation == "page":
            return self.engine.page(sid, str(payload.get("group", "")))
        if operation == "draft":
            out = self.engine.draft(sid)
            return {"output": None if out is None else
                    DecisionOutput.model_validate(out).model_dump(mode="json", by_alias=True)}
        raise ValueError(f"unknown Decision read {operation}")

    def report(self, payload: dict) -> dict:
        """A traveller's free-text report on a place; stored for review, never applied to the corpus directly."""
        if set(payload) - {"place_id", "text", "reporter"}:
            raise ValueError("unknown report field")
        return self.engine.report(payload.get("place_id"), payload.get("text"), payload.get("reporter"))

    def snapshot(self, sid: str) -> dict:
        with self.engine.store.lock(sid):
            return self.engine.store.get(sid).model_dump(mode="json")

    def restore(self, snapshot: dict) -> None:
        data = Session.model_validate(snapshot)
        self.engine.store.restore(data)
        self.engine._results.pop(data.id, None)

    def rebase(self, sid: str, payload: dict) -> dict:
        inp = StartInput.model_validate(payload)
        before = self.load(sid)["view"]
        with self.engine.store.lock(sid):
            s = self.engine.store.get(sid)
            s.search_input, s.trip_session, s.output = inp.search_input, inp.trip_session, None
            for anchor in inp.search_input.anchors:
                if anchor.place_id not in s.state.selected:
                    s.state.selected.append(anchor.place_id)
                if anchor.priority == "must" and anchor.place_id not in s.state.locked:
                    s.state.locked.append(anchor.place_id)
            self.engine._results.pop(sid, None)
            self.engine.store.save(s)
        out = self.load(sid)
        return {**out, "diff": diff(before, out["view"], None, rebuilt=True)}


def create_engine(data_root: Path) -> Engine:
    load_dotenv(ROOT / ".env")
    cfg = default()
    agent = None
    if all(os.environ.get(k) for k in ("AGENT_API_KEY", "AGENT_BASE_URL", "AGENT_MODEL")):
        agent = lambda fields, on_say: run_agent(fields, on_say, cfg)
    return Engine(Data.load(), cfg, Store(None), agent)
